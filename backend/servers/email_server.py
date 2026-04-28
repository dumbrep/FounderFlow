from __future__ import print_function
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
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
from pydantic import BaseModel


load_dotenv()

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Email] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("email_server")

# api_key = os.getenv("GEMINI_API_KEY")

mcp = FastMCP(
    "Email",
    port=8001)


class EmailDraft(BaseModel):
    subject : str
    body : str
    destination_address: str

class ComposeEmailArgs(BaseModel):
    previous_draft: dict | None
    feedback: str | None
    original_request: str

model = ChatOpenAI(
        model="gpt-5.2",
        temperature=0
    ).with_structured_output(EmailDraft)


os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
# Utilities 

# generate content for email
@mcp.tool(name="composeEmail")
def composeEmail(args: ComposeEmailArgs) -> EmailDraft:
    """
    This Tool is used to compose the email draft. It only creates email draft, does not send it.
    
    : pram previous_draft : latest draft generated 
     type dict | None

    : pram feedback : user feedback on previous draft
     type str | None

    : pram original_request: user's original request
     type str

    """
    logger.info("[composeEmail] TOOL CALLED — original_request=%r has_previous_draft=%s has_feedback=%s",
                args.original_request, args.previous_draft is not None, args.feedback is not None)
    template = """
    You are an expert email writer.

    Original request:
    {original_request}

    Previous email draft (if any):
    {previous_draft}

    Human feedback (if any):
    {feedback}

    TASK:
    - If previous_draft is provided, MODIFY it based on feedback.
    - Keep the purpose and tone of the email unchanged.
    - Only update the fields mentioned in feedback.
    - Return ONLY valid JSON.
    - Modify only where needed and keep rest of the data untuched. 

    Output format:
    {{
    "subject": "...",
    "body": "...",
    "destination_address": "..."
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

    logger.info("[composeEmail] Invoking LLM with final prompt (len=%d)", len(final_prompt))

    response = model.invoke(final_prompt)
    logger.info("[composeEmail] LLM returned draft — subject=%r to=%r",
                getattr(response, "subject", None), getattr(response, "destination_address", None))

    return response





# function to send an email
@mcp.tool(name="sendEmail")
def sendEmail(data : EmailDraft):
    """
    This tool is used to sent the email. 
    
    :param subject: subject of email
    :type subject: str

    :param body: body of email
    :type body: str

    :param destination_address: destination of email
    :type destination_address: str
    """
    logger.info("[sendEmail] TOOL CALLED — to=%r subject=%r", data.destination_address, data.subject)
    from_email = os.getenv('APP_EMAIL')
    from_password = os.getenv('APP_PASSCODE')

    if not from_email or not from_password:
        logger.error("[sendEmail] Missing APP_EMAIL / APP_PASSCODE env vars")
        return {"success": False, "message": "APP_EMAIL / APP_PASSCODE not configured"}

    msg = EmailMessage()

    msg['From'] = from_email
    msg['Subject'] = data.subject
    msg['To'] = data.destination_address
    msg.set_content(data.body)

    try:
        logger.info("[sendEmail] Connecting to smtp.gmail.com:587")
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login(from_email, from_password)
            logger.info("[sendEmail] Logged in, sending message")
            smtp.send_message(msg)
            logger.info("[sendEmail] SUCCESS — email sent to %s", data.destination_address)
            return { "success" : True, "message"  : "Email sent successfully!"}
    except Exception as e:
        error_msg = f"An error occurred: {e}"
        logger.exception("[sendEmail] FAILED — %s", error_msg)
        return { "success" : False, "message"  : error_msg}


# function to schedule the meet

if __name__== "__main__":
    logger.info("Starting Email MCP server on port 8001")
    mcp.run(
        transport="streamable-http"
    )





