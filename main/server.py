from __future__ import print_function

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
import smtplib
from email.message import EmailMessage
import json
from langchain_ollama import ChatOllama 
import re
import uuid
import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

mcp = FastMCP("Email")

# model =  ChatGoogleGenerativeAI(model="gemini-2.5-flash",api_key = api_key);
model = ChatOllama(model="llama3")

from pydantic import BaseModel

class SendEmailArgs(BaseModel):
    user_query : str


class SendEmailResponse(BaseModel):
    success: bool
    message: str


class CreateMeetArgs(BaseModel):
    user_query : str


class CreateMeetResponse(BaseModel):
    success: bool
    message: str

# Utilities 

# generate content for email
def generateContentEmail(query:str):
    template = """You are an expert email generator. You are provided with the user's query.
        Your task is to compose an email based on that query.

        User query:
        {query}

        Return ONLY a valid JSON object in this exact format:
        {{
          "subject": "<email subject>",
          "body": "<email body>",
          "destination_address": "<recipient email>"
        }}

        Make sure:
        - The JSON is syntactically valid.
        - The JSON has a closing curly brace.
        - Do NOT include any explanations, extra text, or markdown.
        """

    prompt = PromptTemplate(
        input_variables=["query"],
        template=template
    )
    final_prompt = prompt.format(query = query)

    response = model.invoke([{"role": "system", "content": "Compose mail alinghed with subject and destination address should be accurate."},{"role": "user", "content": final_prompt}])
    print("Raw response:", response.content)

    try:
        # Extract JSON block from response
        match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if match:
            json_str = match.group(0).strip()
            if not json_str.endswith('}'):
                json_str += '}'
            try:
                data = json.loads(json_str)
                return data
            except json.JSONDecodeError:
                print("JSON incomplete or invalid, trying to repair...")
                fixed = re.sub(r'[^}]*$', '}', json_str)
                try:
                    data = json.loads(fixed)
                    return data
                except Exception as e:
                    print("Final JSON parse error:", e)
                    return None
        else:
            print("No JSON found in the response")
            return None

    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        print("Response content:", response.content)
        return None


# generate content for email scheduling
def generateContentMeeting(query:str):
    system_template = """You are an intelligent assistant that converts a user's meeting request into structured Google Calendar event data.

        generate a JSON object strictly in this format:

        {
         "summary": "<title of the meeting>",
         "description": "<short description of purpose>",
         "start": {
           "dateTime": "<ISO 8601 datetime with timezone offset, e.g. 2025-10-10T15:00:00+05:30>",
           "timeZone": "Asia/Kolkata"
         },
         "end": {
           "dateTime": "<ISO 8601 datetime with timezone offset, end time at least 30 minutes after start>",
           "timeZone": "Asia/Kolkata"
         },
         "conferenceData": {
           "createRequest": {
             
             "conferenceSolutionKey": { "type": "hangoutsMeet" }
           }
         },
         "attendees": [
           { "email": "<email1>" },
           { "email": "<email2>" }
         ]
        }

        Rules:
         Always produce valid JSON (no extra text, explanations, or markdown).
         Convert relative time expressions (e.g., "tomorrow 3 PM") into actual ISO datetimes.
         Default duration: 1 hour if not specified.
         If timezone is not mentioned, assume Asia/Kolkata.
         If description is not provided, infer it from the title.
         If no attendees are mentioned, return an empty list.
         Keep summary short (3-6 words).

    """ 

    response = model.invoke([{"role": "system", "content": system_template + f"current date and time you can refer {datetime.now()}"},{"role": "user", "content": query}])

    try:
        # Extract JSON block from response
        match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            
            if "conferenceData" not in data:
                data["conferenceData"] = {}
            if "createRequest" not in data["conferenceData"]:
                data["conferenceData"]["createRequest"] = {"conferenceSolutionKey": {"type": "hangoutsMeet"}}
            data["conferenceData"]["createRequest"]["requestId"] = str(uuid.uuid4())
            print("data")
            print(data)
            return data
        else:
            print("No JSON found in the response")
            return None
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        print("Response content:", response.content)
        return None


# function to send an email
def send_email(data:dict):
    print(data)
    from_email = os.getenv('APP_EMAIL')
    from_password = os.getenv('APP_PASSCODE')

    msg = EmailMessage()
    msg['Subject'] = data["subject"]
    msg['From'] = from_email
    msg['To'] = data["destination_address"]
    msg.set_content(data["body"])

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login(from_email, from_password)
            smtp.send_message(msg)
            return SendEmailResponse(success=True, message="Email sent successfully!")
    except Exception as e:
        error_msg = f"An error occurred: {e}"
        print(error_msg)
        return SendEmailResponse(success=False, message=error_msg)


# function to schedule the meet
SCOPES = ['https://www.googleapis.com/auth/calendar']
def create_meet_event(eventInput: dict):
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('D:\FounderFlow\SCHEDULE_MEETS\credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)

    event = eventInput

    event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1,
    ).execute()  
    meet_link = event.get("hangoutLink") or event["conferenceData"]["entryPoints"][0]["uri"]

    for attendee in eventInput.get("attendees", []):
        send_email({
            "subject": f"Invitation: {event['summary']}",
            "body": f"""Hi,

            You are invited to the following meeting:

            📅 {event['summary']}
            🕒 Starts: {event['start']['dateTime']}
            🔗 Google Meet link: {meet_link}

            See you there!
            """,
                    "destination_address": attendee["email"]
        })


# Tools 

# tool to send emails
@mcp.tool()
def sendEmail(args: SendEmailArgs) -> SendEmailResponse:
    """
    This tool will be used for sending the email.
    """

    try:
        email_body = generateContentEmail(args.user_query)
        if not email_body:
            return SendEmailResponse(success=False, message="Failed to generate email content")
        
        return send_email(email_body)

    except Exception as e:
        error_msg = f"An error occurred: {e}"
        print(error_msg)
        return SendEmailResponse(success=False, message=error_msg)

# tool to schedule meets
@mcp.tool()
def scheduleMeet(args : CreateMeetArgs)->CreateMeetResponse:
    """
        This tool is use to schedule meets based on user query.
    """
    try:
        event = generateContentMeeting(args.user_query)
        if not event:
             return CreateMeetResponse(success=False, message="Failed to generate event data")

        create_meet_event(event)
        return CreateMeetResponse(success=True, message="Meeting scheduled successfully!")

    except Exception as e:
        error_msg = f"An error occurred: {e}"
        print(error_msg)
        return CreateMeetResponse(success=False, message=error_msg)




if __name__== "__main__":
    print("Starting MCP server with tools:")
    mcp.run(transport="streamable-http")






