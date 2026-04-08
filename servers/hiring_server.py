from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel
import requests
import uuid
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

mcp = FastMCP("Hiring", port=8004)

MCP_API_KEY = os.getenv("MCP_API_KEY")
MCP_SERVER_URL = "https://mcp.zapier.com/api/v1/connect"

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly"
]

# Path to store form history (in servers directory)
SERVER_DIR = os.path.dirname(__file__)
FORMS_HISTORY_FILE = os.path.join(SERVER_DIR, "forms_history.json")


def save_form_to_history(form_id: str, form_url: str, form_title: str):
    """Save created form details to JSON file with timestamp"""
    try:
        # Load existing history
        history = {"forms": []}
        if os.path.exists(FORMS_HISTORY_FILE):
            try:
                with open(FORMS_HISTORY_FILE, 'r') as f:
                    content = f.read().strip()
                    if content:  # Only parse if file has content
                        history = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                # If file is corrupted or empty, start fresh
                print("⚠️ Warning: forms_history.json was invalid, creating new history")
                history = {"forms": []}
        
        # Add new form
        form_entry = {
            "form_id": form_id,
            "form_url": form_url,
            "form_title": form_title,
            "created_at": datetime.now().isoformat(),
            "timestamp": datetime.now().timestamp()
        }
        history["forms"].append(form_entry)
        
        # Save back to file
        with open(FORMS_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        
        print(f"✅ Form saved to history: {form_title}")
    except Exception as e:
        print(f"⚠️ Warning: Could not save form to history: {e}")


def get_most_recent_form():
    """Get the most recently created form from history"""
    try:
        if not os.path.exists(FORMS_HISTORY_FILE):
            return None
        
        with open(FORMS_HISTORY_FILE, 'r') as f:
            content = f.read().strip()
            if not content:  # Empty file
                return None
            history = json.loads(content)
        
        forms = history.get("forms", [])
        if not forms:
            return None
        
        # Sort by timestamp and get the most recent
        most_recent = sorted(forms, key=lambda x: x.get("timestamp", 0), reverse=True)[0]
        return most_recent
    except Exception as e:
        print(f"⚠️ Error retrieving form history: {e}")
        return None


class HiringPostDraft(BaseModel):
    content: str
    form_url: str


class ComposeHiringPostArgs(BaseModel):
    previous_draft: dict | None
    feedback: str | None
    original_request: str
    form_url: str
    job_title: str


model = ChatOpenAI(
        model="gpt-5.2",
        temperature=0
    ).with_structured_output(HiringPostDraft)


@mcp.tool(name="getRecentFormDetails")
def getRecentFormDetails() -> dict:
    """
    This tool retrieves details of the most recently created hiring form.
    Use this when you need to post an existing form to LinkedIn.
    
    :return: Dictionary with form details (form_id, form_url, form_title, created_at)
    """
    try:
        recent_form = get_most_recent_form()
        
        if not recent_form:
            return {
                "success": False,
                "message": "No forms found in history. Please create a form first using createHiringForm."
            }
        
        print(f"📋 Most recent form found:")
        print(f"   Title: {recent_form['form_title']}")
        print(f"   ID: {recent_form['form_id']}")
        print(f"   URL: {recent_form['form_url']}")
        print(f"   Created: {recent_form['created_at']}")
        
        return {
            "success": True,
            "form_id": recent_form["form_id"],
            "form_url": recent_form["form_url"],
            "form_title": recent_form["form_title"],
            "created_at": recent_form["created_at"],
            "message": f"Found form: {recent_form['form_title']}"
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving recent form: {str(e)}"
        }


@mcp.tool(name="createHiringForm")
def createHiringForm(form_title: str = "Job Application Form") -> dict:
    """
    This tool creates a Google Form for hiring/job applications.
    
    :param form_title: Title of the hiring form
    :type form_title: str
    :return: Dictionary with form URL and form ID
    """
    try:
        creds = None
        token_path = os.path.join(SERVER_DIR, "token.json")
        credentials_path = os.path.join(SERVER_DIR, "credentials.json")

        # Load existing token if available
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=8080)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        # Build the Forms API service
        service = build("forms", "v1", credentials=creds)

        # Create a new form
        new_form = {
            "info": {
                "title": form_title,
                "documentTitle": form_title,
            }
        }

        # Create the form
        form = service.forms().create(body=new_form).execute()
        form_url = form['responderUri']
        form_id = form['formId']

        # Add hiring-related questions
        update = {
            "requests": [
                {
                    "createItem": {
                        "item": {
                            "title": "Full Name",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 0}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Email Address",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {"paragraph": False}
                                }
                            }
                        },
                        "location": {"index": 1}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Contact Number",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 2}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Applying for Job Role",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 3}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Years of Experience",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [
                                            {"value": "Fresher"},
                                            {"value": "1–2 years"},
                                            {"value": "3–5 years"},
                                            {"value": "5+ years"}
                                        ],
                                        "shuffle": False
                                    }
                                }
                            }
                        },
                        "location": {"index": 4}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Technical Skills / Tools Known",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {"paragraph": True}
                                }
                            }
                        },
                        "location": {"index": 5}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Educational Qualification",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 6}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Upload Resume (Drive/LinkedIn/GitHub link)",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 7}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Why do you want to join our company?",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {"paragraph": True}
                                }
                            }
                        },
                        "location": {"index": 8}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Notice Period",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [
                                            {"value": "Immediate Joiner"},
                                            {"value": "15 Days"},
                                            {"value": "30 Days"},
                                            {"value": "More than 30 Days"}
                                        ],
                                        "shuffle": False
                                    }
                                }
                            }
                        },
                        "location": {"index": 9}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Expected CTC (in LPA)",
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 10}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Current Location",
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 11}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Are you willing to relocate?",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [
                                            {"value": "Yes"},
                                            {"value": "No"}
                                        ],
                                        "shuffle": False
                                    }
                                }
                            }
                        },
                        "location": {"index": 12}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "LinkedIn / Portfolio URL (if any)",
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 13}
                    }
                }
            ]
        }

        # Update form with all questions
        service.forms().batchUpdate(formId=form_id, body=update).execute()

        print(f"✅ Form created successfully!")
        print(f"📝 Form URL: {form_url}")

        # Save form to history
        save_form_to_history(form_id, form_url, form_title)

        return {
            "success": True,
            "form_url": form_url,
            "form_id": form_id,
            "message": "Hiring form created successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error creating form: {str(e)}"
        }


@mcp.tool(name="getHiringFormResponses")
def getHiringFormResponses(form_id: str = None) -> dict:
    """
    This tool retrieves all responses/submissions from a Google Form.
    If no form_id is provided, it retrieves responses from the most recently created form.
    
    :param form_id: The ID of the Google Form to retrieve responses from (optional - defaults to most recent)
    :type form_id: str | None
    :return: Dictionary containing all form responses
    """
    try:
        # If no form_id provided, get the most recent one
        if not form_id:
            recent_form = get_most_recent_form()
            if not recent_form:
                return {
                    "success": False,
                    "message": "No form_id provided and no forms found in history. Please create a form first or provide a form_id."
                }
            form_id = recent_form["form_id"]
            print(f"📋 Using most recent form: {recent_form['form_title']}")
            print(f"🆔 Form ID: {form_id}")
        
        creds = None
        token_path = os.path.join(SERVER_DIR, "token.json")
        credentials_path = os.path.join(SERVER_DIR, "credentials.json")

        # Load existing token if available
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=8080)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        # Build the Forms API service
        service = build("forms", "v1", credentials=creds)

        # Get form responses
        result = service.forms().responses().list(formId=form_id).execute()
        responses = result.get('responses', [])

        if not responses:
            return {
                "success": True,
                "total_responses": 0,
                "message": "No responses yet",
                "responses": []
            }

        # Format responses nicely
        formatted_responses = []
        for idx, response in enumerate(responses, 1):
            response_data = {
                "response_id": response.get('responseId'),
                "timestamp": response.get('lastSubmittedTime'),
                "answers": {}
            }
            
            # Extract answers from the response
            answers = response.get('answers', {})
            for question_id, answer_data in answers.items():
                text_answers = answer_data.get('textAnswers', {})
                if text_answers:
                    answer_values = [ans.get('value') for ans in text_answers.get('answers', [])]
                    response_data["answers"][question_id] = answer_values[0] if len(answer_values) == 1 else answer_values
            
            formatted_responses.append(response_data)

        print(f"📊 Retrieved {len(formatted_responses)} responses from form {form_id}")

        return {
            "success": True,
            "total_responses": len(formatted_responses),
            "form_id": form_id,
            "responses": formatted_responses,
            "message": f"Successfully retrieved {len(formatted_responses)} responses"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving form responses: {str(e)}"
        }


@mcp.tool(name="getDetailedHiringResponses")
def getDetailedHiringResponses(form_id: str = None) -> dict:
    """
    This tool retrieves form responses with question titles for better readability.
    If no form_id is provided, it retrieves responses from the most recently created form.
    
    :param form_id: The ID of the Google Form (optional - defaults to most recent form)
    :type form_id: str | None
    :return: Dictionary with responses including question titles
    """
    try:
        # If no form_id provided, get the most recent one
        if not form_id:
            recent_form = get_most_recent_form()
            if not recent_form:
                return {
                    "success": False,
                    "message": "No form_id provided and no forms found in history. Please create a form first or provide a form_id."
                }
            form_id = recent_form["form_id"]
            print(f"📋 Using most recent form: {recent_form['form_title']}")
            print(f"🆔 Form ID: {form_id}")
            print(f"📅 Created: {recent_form['created_at']}")
        
        creds = None
        token_path = os.path.join(SERVER_DIR, "token.json")
        credentials_path = os.path.join(SERVER_DIR, "credentials.json")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=8080)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        service = build("forms", "v1", credentials=creds)

        # Get form structure
        form = service.forms().get(formId=form_id).execute()
        
        # Map question IDs to titles
        question_map = {}
        for item in form.get('items', []):
            question_id = item.get('questionItem', {}).get('question', {}).get('questionId')
            if question_id:
                question_map[question_id] = item.get('title', 'Untitled Question')

        # Get responses
        result = service.forms().responses().list(formId=form_id).execute()
        responses = result.get('responses', [])

        if not responses:
            return {
                "success": True,
                "total_responses": 0,
                "form_title": form.get('info', {}).get('title', 'Untitled Form'),
                "message": "No responses yet",
                "applications": []
            }

        # Format responses with question titles
        applications = []
        for idx, response in enumerate(responses, 1):
            application = {
                "application_number": idx,
                "response_id": response.get('responseId'),
                "submitted_at": response.get('lastSubmittedTime'),
                "answers": {}
            }
            
            answers = response.get('answers', {})
            for question_id, answer_data in answers.items():
                question_title = question_map.get(question_id, f"Question {question_id}")
                text_answers = answer_data.get('textAnswers', {})
                if text_answers:
                    answer_values = [ans.get('value') for ans in text_answers.get('answers', [])]
                    application["answers"][question_title] = answer_values[0] if len(answer_values) == 1 else answer_values
            
            applications.append(application)

        print(f"📊 Retrieved {len(applications)} applications")
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"Form: {form.get('info', {}).get('title', 'Untitled Form')}")
        print(f"Total Applications: {len(applications)}")
        print(f"{'='*60}\n")
        
        for app in applications:
            print(f"Application #{app['application_number']}")
            print(f"Submitted: {app['submitted_at']}")
            for question, answer in app['answers'].items():
                print(f"  {question}: {answer}")
            print()

        return {
            "success": True,
            "total_responses": len(applications),
            "form_title": form.get('info', {}).get('title', 'Untitled Form'),
            "form_id": form_id,
            "applications": applications,
            "message": f"Successfully retrieved {len(applications)} applications"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving detailed responses: {str(e)}"
        }


@mcp.tool(name="generateHiringPost")
def generateHiringPost(args: ComposeHiringPostArgs) -> HiringPostDraft:
    """
    This tool generates a LinkedIn post draft for hiring announcement with the Google Form link.
    
    :param previous_draft: latest draft generated
    :type previous_draft: dict | None
    
    :param feedback: user feedback on previous draft
    :type feedback: str | None
    
    :param original_request: user's original request about the job posting
    :type original_request: str
    
    :param form_url: Google Form URL for applications
    :type form_url: str
    
    :param job_title: Job position title
    :type job_title: str
    """
    template = """
    You are a professional HR content writer creating LinkedIn hiring announcements.

    Original request:
    {original_request}

    Job Title: {job_title}
    Application Form URL: {form_url}

    Previous post draft (if any):
    {previous_draft}

    Human feedback (if any):
    {feedback}

    TASK:
    - Create an engaging LinkedIn post announcing that we're hiring for {job_title}
    - Include key details about the role if mentioned in the original request
    - Make it professional yet welcoming
    - MUST include the form_url for applications
    - If previous_draft is provided, MODIFY it based on feedback
    - Keep the professional tone unless feedback says otherwise
    - Modify only where needed and keep rest of the data untouched

    Output format (MUST be valid JSON):
    {{
    "content": "...engaging LinkedIn post text with form link...",
    "form_url": "{form_url}"
    }}
    """

    prompt = PromptTemplate(
        input_variables=["original_request", "job_title", "form_url", "previous_draft", "feedback"],
        template=template
    )

    final_prompt = prompt.format(
        original_request=args.original_request,
        job_title=args.job_title,
        form_url=args.form_url,
        previous_draft=json.dumps(args.previous_draft, indent=2)
        if args.previous_draft else "None",
        feedback=args.feedback if args.feedback else "None"
    )

    print("Final prompt")
    print(final_prompt)

    response = model.invoke(final_prompt)

    return response


@mcp.tool(name="postHiringToLinkedIn")
def postHiringToLinkedIn(data: HiringPostDraft, company_id: str = "111128288"):
    """
    Post hiring announcement to LinkedIn via Zapier MCP
    """

    if not MCP_API_KEY:
        print("\n MCP API key missing")
        print(data.content)
        return {
            "success": False,
            "message": "MCP_API_KEY not configured"
        }

    try:
        import json

        headers = {
            "Authorization": f"Bearer {MCP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": "linkedin_create_company_update",
                "arguments": {
                    "instructions": "Create a LinkedIn company page update for hiring",
                    "comment": data.content,
                    "company_id": company_id,
                    "visibility__code": "PUBLIC"
                }
            }
        }

        print("\n📤 Posting to LinkedIn...")
        
        response = requests.post(
            MCP_SERVER_URL,
            headers=headers,
            json=payload,
            timeout=30,
            stream=True  # 🔥 CRITICAL
        )

        print("Status:", response.status_code)

        # ❌ Handle non-200
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"Zapier API error: {response.status_code}",
                "details": response.text
            }

        # ✅ Read streaming response
        full_response = ""
        for line in response.iter_lines(decode_unicode=True):
            if line:
                full_response += line + "\n"

        print("🔍 Raw MCP Response:\n", full_response)

        if not full_response.strip():
            return {
                "success": False,
                "message": "Empty response from MCP"
            }

        # ✅ Step 1: Extract outer JSON
        parsed_json = None
        for line in full_response.split("\n"):
            if "data:" in line:
                try:
                    json_str = line.split("data:")[-1].strip()
                    if json_str:
                        parsed_json = json.loads(json_str)
                except:
                    continue

        if not parsed_json:
            return {
                "success": False,
                "message": "Failed to parse outer MCP response",
                "raw_response": full_response
            }

        # ✅ Step 2: Extract inner JSON (CRITICAL FIX)
        try:
            content_list = parsed_json.get("result", {}).get("content", [])

            if not content_list:
                return {
                    "success": False,
                    "message": "No content in MCP response",
                    "parsed_json": parsed_json
                }

            inner_text = content_list[0].get("text")

            if not inner_text:
                return {
                    "success": False,
                    "message": "Missing inner text",
                    "parsed_json": parsed_json
                }

            # 🔥 SECOND JSON PARSE
            inner_json = json.loads(inner_text)

            execution = inner_json.get("execution", {})
            status = execution.get("status")

            if status == "SUCCESS":
                results = inner_json.get("results", [])
                post_url = results[0].get("url") if results else None

                return {
                    "success": True,
                    "message": "✅ Successfully posted to LinkedIn!",
                    "post_url": post_url,
                    "details": inner_json
                }

            return {
                "success": False,
                "message": f"MCP execution failed: {status}",
                "details": inner_json
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Inner parsing error: {str(e)}",
                "raw_response": full_response
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error posting to LinkedIn: {str(e)}"
        }
    

if __name__ == "__main__":
    print("Starting Hiring MCP server...")
    mcp.run(transport="streamable-http")
