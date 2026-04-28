
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import os
import json
import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel
import requests
import uuid

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [LinkedIn] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("linkedin_server")

mcp = FastMCP("LinkedIn", port=8003)

MCP_API_KEY = os.getenv("MCP_API_KEY")
MCP_SERVER_URL = "https://mcp.zapier.com/api/v1/connect"


class LinkedInDraft(BaseModel):
    content: str


class ComposeLinkedInPostArgs(BaseModel):
    previous_draft: dict | None
    feedback: str | None
    original_request: str


model = ChatOpenAI(
        model="gpt-5.2",
        temperature=0
    ).with_structured_output(LinkedInDraft)


@mcp.tool(name="generateLinkedInPost")
def generateLinkedInPost(args: ComposeLinkedInPostArgs) -> LinkedInDraft:
    """
    This Tool is used to compose a LinkedIn post draft. It only creates the draft, does not post it.

    :param previous_draft: latest draft generated
     type dict | None

    :param feedback: user feedback on previous draft
     type str | None

    :param original_request: user's original request
     type str
    """
    logger.info("[generateLinkedInPost] TOOL CALLED — original_request=%r has_previous_draft=%s has_feedback=%s",
                args.original_request, args.previous_draft is not None, args.feedback is not None)
    template = """
    You are a professional LinkedIn content writer.

    Original request:
    {original_request}

    Previous post draft (if any):
    {previous_draft}

    Human feedback (if any):
    {feedback}

    TASK:
    - If previous_draft is provided, MODIFY it based on feedback.
    - Keep the purpose and tone of the post unchanged.
    - Only update the parts mentioned in feedback.
    - Return ONLY valid JSON.
    - Modify only where needed and keep rest of the data untouched.

    Output format:
    {{
    "content": "..."
    }}
    """

    prompt = PromptTemplate(
        input_variables=["original_request", "previous_draft", "feedback"],
        template=template
    )

    final_prompt = prompt.format(
        original_request=args.original_request,
        previous_draft=json.dumps(args.previous_draft, indent=2)
        if args.previous_draft else "None",
        feedback=args.feedback if args.feedback else "None"
    )

    logger.info("[generateLinkedInPost] Invoking LLM (prompt len=%d)", len(final_prompt))

    response = model.invoke(final_prompt)
    logger.info("[generateLinkedInPost] LLM returned draft (content len=%d)",
                len(getattr(response, "content", "") or ""))

    return response

@mcp.tool(name="postLinkedIn")
def postLinkedIn(data: LinkedInDraft, company_id: str = "111128288"):
    """
    This tool is used to post the finalized content to LinkedIn via Zapier MCP.
    """
    logger.info("[postLinkedIn] TOOL CALLED — company_id=%s content_len=%d",
                company_id, len(data.content or ""))

    if not MCP_API_KEY:
        logger.warning("[postLinkedIn] MCP_API_KEY missing — cannot post")
        return {
            "success": False,
            "message": "MCP_API_KEY not configured"
        }

    try:
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
                    "instructions": "Create a LinkedIn company page update",
                    "comment": data.content,
                    "company_id": company_id,
                    "visibility__code": "PUBLIC"
                }
            }
        }

        logger.info("[postLinkedIn] POSTing to Zapier MCP (content preview=%r)", (data.content or "")[:100])

        # ✅ IMPORTANT: enable streaming
        response = requests.post(
            MCP_SERVER_URL,
            headers=headers,
            json=payload,
            timeout=30,
            stream=True
        )

        logger.info("[postLinkedIn] Zapier HTTP status=%s", response.status_code)

        if response.status_code != 200:
            logger.error("[postLinkedIn] Zapier error body=%s", response.text)
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

        logger.info("[postLinkedIn] Raw MCP response received (len=%d)", len(full_response))

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

        # ✅ Step 2: Extract inner JSON
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

            # 🔥 CRITICAL: second JSON parsing
            inner_json = json.loads(inner_text)

            execution = inner_json.get("execution", {})
            status = execution.get("status")

            if status == "SUCCESS":
                results = inner_json.get("results", [])
                post_url = results[0].get("url") if results else None
                logger.info("[postLinkedIn] SUCCESS — post_url=%s", post_url)

                return {
                    "success": True,
                    "message": "✅ Successfully posted to LinkedIn!",
                    "post_url": post_url,
                    "details": inner_json
                }

            logger.error("[postLinkedIn] MCP execution failed status=%s", status)
            return {
                "success": False,
                "message": f"MCP execution failed: {status}",
                "details": inner_json
            }

        except Exception as e:
            logger.exception("[postLinkedIn] Inner parsing error — %s", e)
            return {
                "success": False,
                "message": f"Inner parsing error: {str(e)}",
                "raw_response": full_response
            }

    except Exception as e:
        logger.exception("[postLinkedIn] FAILED — %s", e)
        return {
            "success": False,
            "message": f"Error posting to LinkedIn: {str(e)}"
        }

if __name__ == "__main__":
    logger.info("Starting LinkedIn MCP server on port 8003")
    mcp.run(transport="streamable-http")
