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
from pymongo import MongoClient

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Hiring] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hiring_server")

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

mcp = FastMCP("Hiring", port=8004)

MCP_API_KEY = os.getenv("MCP_API_KEY")
MCP_SERVER_URL = "https://mcp.zapier.com/api/v1/connect"

# ── MongoDB setup ─────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["hiring_deployments"]
job_descriptions_col = db["jobDescriptions"]
responses_col = db["responses"]


# ── Pydantic models ───────────────────────────────────────────
class HiringPostDraft(BaseModel):
    content: str


class ComposeHiringPostArgs(BaseModel):
    previous_draft: dict | None = None
    feedback: str | None = None
    original_request: str
    job_role: str
    description: str


model = ChatOpenAI(
    model="gpt-4o",
    temperature=0
).with_structured_output(HiringPostDraft)


# ── Tool 1: Post Hiring Job ──────────────────────────────────

@mcp.tool(name="postHiringJob")
def postHiringJob(args: ComposeHiringPostArgs) -> dict:
    """
    This tool creates a hiring job posting. It generates a LinkedIn post for the job,
    posts it via LinkedIn, and saves the job description to the database.
    Use this when the user wants to hire candidates or post a job opening.

    :param previous_draft: latest draft generated (for revisions)
    :type previous_draft: dict | None

    :param feedback: user feedback on previous draft
    :type feedback: str | None

    :param original_request: user's original request about the job posting
    :type original_request: str

    :param job_role: The job role/title to hire for
    :type job_role: str

    :param description: Job description with responsibilities, requirements, etc.
    :type description: str
    """
    logger.info("[postHiringJob] TOOL CALLED — job_role=%r", args.job_role)

    APPLICATION_LINK = "https://founderflow-hiring-frontend-main.vercel.app/"

    # ── Step 1: Generate LinkedIn post via LLM ────────────────
    template = """
    You are a professional HR content writer creating LinkedIn hiring announcements.

    Original request:
    {original_request}

    Job Role: {job_role}
    Job Description: {description}
    Application Link: {application_link}

    Previous post draft (if any):
    {previous_draft}

    Human feedback (if any):
    {feedback}

    TASK:
    - Create an engaging LinkedIn post announcing that we're hiring for {job_role}
    - Include key details about the role from the description
    - Make it professional yet welcoming
    - MUST include the application link: {application_link}
    - If previous_draft is provided, MODIFY it based on feedback
    - Keep the professional tone unless feedback says otherwise
    - Modify only where needed and keep rest of the data untouched

    Output format (MUST be valid JSON):
    {{
    "content": "...engaging LinkedIn post text with application link..."
    }}
    """

    prompt = PromptTemplate(
        input_variables=["original_request", "job_role", "description",
                         "application_link", "previous_draft", "feedback"],
        template=template
    )

    final_prompt = prompt.format(
        original_request=args.original_request,
        job_role=args.job_role,
        description=args.description,
        application_link=APPLICATION_LINK,
        previous_draft=json.dumps(args.previous_draft, indent=2)
        if args.previous_draft else "None",
        feedback=args.feedback if args.feedback else "None"
    )

    logger.info("[postHiringJob] Invoking LLM for post draft (prompt len=%d)", len(final_prompt))
    draft = model.invoke(final_prompt)
    logger.info("[postHiringJob] LLM returned draft (content len=%d)", len(draft.content or ""))

    # ── Step 2: Post to LinkedIn via Zapier MCP ───────────────
    linkedin_result = _post_to_linkedin(draft.content)

    # ── Step 3: Save job description to MongoDB ───────────────
    job_doc = {
        "id": str(uuid.uuid4())[:8],
        "job_role": args.job_role,
        "description": args.description,
    }

    try:
        job_descriptions_col.insert_one(job_doc)
        logger.info("[postHiringJob] Saved job to MongoDB — id=%s", job_doc["id"])
    except Exception as e:
        logger.exception("[postHiringJob] MongoDB insert failed — %s", e)
        return {
            "success": False,
            "message": f"LinkedIn post may have succeeded but failed to save job to database: {str(e)}",
            "linkedin_result": linkedin_result,
            "draft": draft.content,
        }

    return {
        "success": linkedin_result.get("success", False),
        "message": "Job posted to LinkedIn and saved to database!" if linkedin_result.get("success") else "LinkedIn post failed, but job saved to database.",
        "draft": draft.content,
        "job_id": job_doc["id"],
        "linkedin_result": linkedin_result,
    }


# ── Tool 2: Get Available Roles ───────────────────────────────

@mcp.tool(name="getAvailableRoles")
def getAvailableRoles() -> dict:
    """
    This tool fetches all job roles currently posted in the database.
    Use this when the user asks for applicants/candidates but hasn't specified a role,
    so you can show them the available roles to choose from.

    :return: Dictionary with list of available job roles
    """
    logger.info("[getAvailableRoles] TOOL CALLED")

    try:
        roles = job_descriptions_col.distinct("job_role")
        logger.info("[getAvailableRoles] Found %d roles", len(roles))

        if not roles:
            return {
                "success": True,
                "roles": [],
                "message": "No job roles found in database. Post a job first using postHiringJob."
            }

        return {
            "success": True,
            "roles": roles,
            "message": f"Available job roles: {', '.join(roles)}"
        }

    except Exception as e:
        logger.exception("[getAvailableRoles] FAILED — %s", e)
        return {
            "success": False,
            "message": f"Error fetching roles: {str(e)}"
        }


# ── Tool 3: Get Top Candidates ───────────────────────────────

@mcp.tool(name="getTopCandidates")
def getTopCandidates(job_role: str, limit: int = 5) -> dict:
    """
    This tool fetches the top candidates for a given job role based on ATS score.
    Use this when the user asks for hiring results, candidate list, or top applicants.

    :param job_role: The job role to filter candidates for
    :type job_role: str
    :param limit: Number of top candidates to return (default 5)
    :type limit: int
    :return: Dictionary with top candidates sorted by ATS score
    """
    logger.info("[getTopCandidates] TOOL CALLED — job_role=%r limit=%d", job_role, limit)

    BACKEND_BASE = "http://localhost:8080"

    try:
        candidates = list(
            responses_col.find(
                {"job_role": {"$regex": job_role, "$options": "i"}},
                {"_id": 0, "user_name": 1, "email": 1, "job_role": 1,
                 "resume_filename": 1, "ats_score": 1}
            ).sort("ats_score", -1).limit(limit)
        )

        # Build actual resume download URLs
        for c in candidates:
            email = c.get("email", "")
            fname = c.get("resume_filename", "")
            if email and fname:
                c["resume_url"] = f"{BACKEND_BASE}/resume/{email}/{fname}"
            else:
                c["resume_url"] = None

        if not candidates:
            logger.info("[getTopCandidates] No candidates found for job_role=%r", job_role)
            return {
                "success": True,
                "total_candidates": 0,
                "job_role": job_role,
                "candidates": [],
                "message": f"No candidates found for '{job_role}'."
            }

        logger.info("[getTopCandidates] SUCCESS — found %d candidates", len(candidates))

        return {
            "success": True,
            "total_candidates": len(candidates),
            "job_role": job_role,
            "candidates": candidates,
            "message": f"Top {len(candidates)} candidates for '{job_role}' by ATS score."
        }

    except Exception as e:
        logger.exception("[getTopCandidates] FAILED — %s", e)
        return {
            "success": False,
            "message": f"Error fetching candidates: {str(e)}"
        }


# ── LinkedIn posting helper ──────────────────────────────────

def _post_to_linkedin(content: str, company_id: str = "111128288") -> dict:
    """Post content to LinkedIn via Zapier MCP."""
    logger.info("[_post_to_linkedin] Posting to LinkedIn (content_len=%d)", len(content or ""))

    if not MCP_API_KEY:
        logger.warning("[_post_to_linkedin] MCP_API_KEY missing — skipping post")
        return {"success": False, "message": "MCP_API_KEY not configured"}

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
                    "instructions": "Create a LinkedIn company page update for hiring",
                    "comment": content,
                    "company_id": company_id,
                    "visibility__code": "PUBLIC"
                }
            }
        }

        logger.info("[_post_to_linkedin] Sending POST to Zapier MCP")
        response = requests.post(
            MCP_SERVER_URL,
            headers=headers,
            json=payload,
            timeout=30,
            stream=True
        )

        logger.info("[_post_to_linkedin] Zapier HTTP status=%s", response.status_code)

        if response.status_code != 200:
            logger.error("[_post_to_linkedin] Zapier error body=%s", response.text)
            return {
                "success": False,
                "message": f"Zapier API error: {response.status_code}",
                "details": response.text
            }

        # Read streaming response
        full_response = ""
        for line in response.iter_lines(decode_unicode=True):
            if line:
                full_response += line + "\n"

        logger.info("[_post_to_linkedin] Raw MCP response received (len=%d)", len(full_response))

        if not full_response.strip():
            return {"success": False, "message": "Empty response from MCP"}

        # Extract outer JSON
        parsed_json = None
        for line in full_response.split("\n"):
            if "data:" in line:
                try:
                    json_str = line.split("data:")[-1].strip()
                    if json_str:
                        parsed_json = json.loads(json_str)
                except Exception:
                    continue

        if not parsed_json:
            return {
                "success": False,
                "message": "Failed to parse outer MCP response",
                "raw_response": full_response
            }

        # Extract inner JSON
        try:
            content_list = parsed_json.get("result", {}).get("content", [])
            if not content_list:
                return {"success": False, "message": "No content in MCP response", "parsed_json": parsed_json}

            inner_text = content_list[0].get("text")
            if not inner_text:
                return {"success": False, "message": "Missing inner text", "parsed_json": parsed_json}

            inner_json = json.loads(inner_text)
            execution = inner_json.get("execution", {})
            status = execution.get("status")

            if status == "SUCCESS":
                results = inner_json.get("results", [])
                post_url = results[0].get("url") if results else None
                logger.info("[_post_to_linkedin] SUCCESS — post_url=%s", post_url)
                return {
                    "success": True,
                    "message": "Successfully posted to LinkedIn!",
                    "post_url": post_url,
                    "details": inner_json
                }

            logger.error("[_post_to_linkedin] MCP execution failed status=%s", status)
            return {"success": False, "message": f"MCP execution failed: {status}", "details": inner_json}

        except Exception as e:
            logger.exception("[_post_to_linkedin] Inner parsing error — %s", e)
            return {"success": False, "message": f"Inner parsing error: {str(e)}", "raw_response": full_response}

    except Exception as e:
        logger.exception("[_post_to_linkedin] FAILED — %s", e)
        return {"success": False, "message": f"Error posting to LinkedIn: {str(e)}"}


if __name__ == "__main__":
    logger.info("Starting Hiring MCP server on port 8004")
    mcp.run(transport="streamable-http")
