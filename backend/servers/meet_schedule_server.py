from __future__ import print_function
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

import json
import logging
import re
import uuid
import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime
from langchain_openai import ChatOpenAI

# Import from same directory
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from email_server import sendEmail, EmailDraft

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MeetSchedule] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("meet_schedule")

mcp = FastMCP(
    "Meet Schedule",
    port=8002)


model = ChatOpenAI(
        model="gpt-5.2",
        temperature=0
    )


# generate content for email scheduling


def generateContentMeeting(query:str):
    logger.info("[generateContentMeeting] START — query=%r", query)
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

    logger.info("[generateContentMeeting] Invoking LLM...")
    response = model.invoke([{"role": "system", "content": system_template + f"current date and time you can refer {datetime.now()}"},{"role": "user", "content": query}])
    logger.info("[generateContentMeeting] LLM response received (len=%d)", len(response.content or ""))

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
            logger.info("[generateContentMeeting] Parsed event data: summary=%r start=%r attendees=%d",
                        data.get("summary"), data.get("start", {}).get("dateTime"), len(data.get("attendees", [])))
            return data
        else:
            logger.warning("[generateContentMeeting] No JSON found in the LLM response")
            return None
    except json.JSONDecodeError as e:
        logger.error("[generateContentMeeting] Failed to parse JSON: %s", e)
        logger.error("[generateContentMeeting] Response content: %s", response.content)
        return None
    

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/forms.body',
    'https://www.googleapis.com/auth/forms.responses.readonly',
]


def create_meet_event(eventInput: dict):
    logger.info("[create_meet_event] START")
    creds = None
    # Resolve paths relative to this file so CWD changes don't break OAuth
    _here = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(_here, "token.json")
    credentials_path = os.path.join(_here, "credentials.json")
    logger.info("[create_meet_event] token_path=%s credentials_path=%s", token_path, credentials_path)

    #  Load existing token if available
    if os.path.exists(token_path):
        logger.info("[create_meet_event] Loading existing token")
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    else:
        logger.warning("[create_meet_event] No token.json found — will trigger OAuth flow")


    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("[create_meet_event] Refreshing expired token")
            creds.refresh(Request())
        else:
            logger.info("[create_meet_event] Running OAuth local server on port 8080")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        logger.info("[create_meet_event] Token saved")

    # Build Calendar service
    logger.info("[create_meet_event] Building Calendar service")
    service = build('calendar', 'v3', credentials=creds)

    # Create event
    logger.info("[create_meet_event] Inserting event into primary calendar")
    event = service.events().insert(
        calendarId='primary',
        body=eventInput,
        conferenceDataVersion=1,
    ).execute()
    logger.info("[create_meet_event] Event created id=%s", event.get("id"))

    meet_link = event.get("hangoutLink") or event["conferenceData"]["entryPoints"][0]["uri"]
    logger.info("[create_meet_event] Meet link=%s", meet_link)

    #  Send invitations to attendees
    attendees = eventInput.get("attendees", [])
    logger.info("[create_meet_event] Sending invites to %d attendee(s)", len(attendees))
    for attendee in attendees:
        sendEmail( EmailDraft(
        subject=f"Invitation: {event['summary']}",
        body=f"""Hi,

            You are invited to the following meeting:

            📅 {event['summary']}
            🕒 Starts: {event['start']['dateTime']}
            🔗 Google Meet link: {meet_link}

            See you there!
            """,
                    destination_address=attendee["email"]
                )
        )
        logger.info("[create_meet_event] Invite sent to %s", attendee.get("email"))

    logger.info("[create_meet_event] DONE — meeting scheduled")
    return {"success" : True, "message" : f"Meeting scheduled successfully: {meet_link}"}



# tool to schedule meets
@mcp.tool(name = "scheduleMeet")
def scheduleMeet(query : str):
    """
        This tool is use to schedule meets based on user query.
    """
    logger.info("[scheduleMeet] TOOL CALLED — query=%r", query)
    try:
        event = generateContentMeeting(query)
        if not event:
            logger.error("[scheduleMeet] Failed to generate event data")
            return {"success":False, "message":"Failed to generate event data"}

        create_meet_event(event)
        logger.info("[scheduleMeet] SUCCESS")
        return {"success":True, "message":"Meeting scheduled successfully!"}

    except Exception as e:
        error_msg = f"An error occurred: {e}"
        logger.exception("[scheduleMeet] FAILED — %s", error_msg)
        return {"success" :False, "message" : error_msg}


if __name__== "__main__":
    logger.info("Starting Meet Schedule MCP server on port 8002")
    mcp.run(
        transport="streamable-http"
    )

