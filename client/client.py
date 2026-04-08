"""
client.py
=========
FounderFlow — Agent graph definition for backend integration.

Memory lifecycle is owned by the caller (backend.py):
  • checkpointer  → from MemoryManager.get_checkpointer()
  • system_prompt → from build_system_prompt(memory_context)
"""

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated
from dotenv import load_dotenv

import os
import json

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


# ──────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages:       Annotated[list, add_messages]
    previous_draft: dict | None
    image_url:      str | None
    linkedin_draft: dict | None
    hiring_draft:   dict | None
    lead_report:    dict | None


# ──────────────────────────────────────────────────────────────
# Tool → state field mapping
# ──────────────────────────────────────────────────────────────

TOOL_STATE_MAP = {
    "composeEmail":          "previous_draft",
    "createImage":           "image_url",
    "scheduleMeet":          "meet_result",
    "generateLinkedInPost":  "linkedin_draft",
    "generateHiringPost":    "hiring_draft",
    "searchLeads":           "lead_report",
}

TOOL_OUTPUT_TYPE = {
    "composeEmail":               "json",
    "createImage":                "json",
    "scheduleMeet":               "json",
    "sendEmail":                  "text",
    "createHiringForm":           "json",
    "generateHiringPost":         "json",
    "getHiringFormResponses":     "json",
    "getDetailedHiringResponses": "json",
    "getRecentFormDetails":       "json",
    "searchLeads":                "json",
    "scoreLeadProfile":           "json",
    "getLeadReport":              "json",
}


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def get_tool_name(messages: list, tool_message: ToolMessage) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                if call["id"] == tool_message.tool_call_id:
                    return call["name"]
    return None


def extract_tool_payload(tool_name: str, content):
    if not isinstance(content, list) or not content:
        return None

    text = content[0].get("text", "").strip()
    if not text:
        return None

    if TOOL_OUTPUT_TYPE.get(tool_name) == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"[WARN] Invalid JSON from tool {tool_name}")
            return None

    return text


# ──────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = """
You are an agent that MUST use tools.

Email flow:
    - Check whether email and content regarding email is given to the user or not, if given, proceed else ask for these things. 
    - Call composeEmail first
    - Wait for human approval
    - If human needs some modification, send previous_draft with human feedback to composeEmail again. Do not forget to send previous draft
    - Then call sendEmail

Meet Scheduling flow
    - Call scheduleMeet tool to schedule meet according to user

Image posting workflow
    - use createImage tool to create image
    - Wait for human approval
    - If human needs some changes, send human feedback again to createImage tool
    - After confirmation, call postImage tool. postImage requires the image_url parameter

LinkedIn workflow:
- Call generateLinkedInPost first
- Wait for human approval
- If human needs some modification, send previous_draft with human feedback to generateLinkedInPost again. Do not forget to send previous draft
- Then call postLinkedIn

Hiring workflow (for posting job openings):
- First call createHiringForm to create a Google Form for job applications
- Extract the form_url from the result
- Then call generateHiringPost with form_url, job_title, and original_request to create a LinkedIn post draft
- Wait for human approval
- If human needs some modification, send previous_draft with human feedback to generateHiringPost again. Do not forget to send previous draft and form_url
- Then call postHiringToLinkedIn to post the hiring announcement

Posting existing hiring form to LinkedIn:
- When user asks to "post the form" or "post the last form" or "post existing form to LinkedIn"
- Call getRecentFormDetails to get the most recently created form's details
- Extract form_url and form_title (use form_title as job_title) from the result
- Call generateHiringPost with the form_url, job_title (from form_title), and original_request
- Wait for human approval
- Then call postHiringToLinkedIn to post the hiring announcement

Testing/Simple Form Creation workflow:
- When user asks to "create a hiring form" or "create a job application form" WITHOUT mentioning LinkedIn
- Just call createHiringForm and return the form URL and form_id

Retrieving hiring form responses:
- Use getDetailedHiringResponses (preferred) for human-readable format with question titles
- form_id parameter is OPTIONAL — if not provided, it will use the most recently created form

Lead Generation workflow:
- Call searchLeads with appropriate parameters: keywords, industry, persona, company, location
- Display the results to the user

Score single lead:
- Call scoreLeadProfile with person details and target criteria

Get previous lead report:
- Call getLeadReport to retrieve the most recent report

Never respond with plain text if a tool can be used.
"""


def build_system_prompt(memory_context: str = "") -> str:
    """Inject the user's memory context into the system prompt."""
    if not memory_context:
        return BASE_SYSTEM_PROMPT

    return BASE_SYSTEM_PROMPT + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MEMORY CONTEXT (use this to personalise your responses)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{memory_context}
"""


# ──────────────────────────────────────────────────────────────
# Graph factory
# ──────────────────────────────────────────────────────────────

async def create_agent_app(checkpointer):
    """
    Build and compile the LangGraph agent.

    Parameters
    ----------
    checkpointer : AsyncPostgresSaver
        Must be provided by the caller (MemoryManager.get_checkpointer()).
        Keeping the checkpointer external means a single DB pool is shared
        across the entire process lifetime — no duplicate connections.
    """
    client = MultiServerMCPClient(
        {
            "Instagram":     {"url": "http://localhost:8000/mcp", "transport": "streamable_http"},
            "Email":         {"url": "http://localhost:8001/mcp", "transport": "streamable_http"},
            "Meet_Schedule": {"url": "http://localhost:8002/mcp", "transport": "streamable_http"},
            "LinkedIn":      {"url": "http://localhost:8003/mcp", "transport": "streamable_http"},
            "Hiring":        {"url": "http://localhost:8004/mcp", "transport": "streamable_http"},
            "Lead_Gen":      {"url": "http://localhost:8006/mcp", "transport": "streamable_http"},
        }
    )

    tools = await client.get_tools()
    llm   = ChatOpenAI(model="gpt-4o", temperature=0)
    model = llm.bind_tools(tools)

    async def agent_node(state: AgentState):
        response = await model.ainvoke(state["messages"])
        state["messages"].append(response)
        return response

    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    
    # Tools feed straight back to agent; approval is handled by the HTTP layer
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer), llm