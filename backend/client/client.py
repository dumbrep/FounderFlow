"""
client.py
=========
FounderFlow — Agent graph definition for backend integration.

This module defines the LangGraph agent used by app.py (or other callers).
Memory/persistence is currently DISABLED — see commented sections for
re-enabling later.
"""

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage, SystemMessage
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
    "postHiringJob":         "hiring_draft",
    "searchLeads":           "lead_report",
}

TOOL_OUTPUT_TYPE = {
    "composeEmail":               "json",
    "createImage":                "json",
    "scheduleMeet":               "json",
    "sendEmail":                  "text",
    "postHiringJob":              "json",
    "getAvailableRoles":          "json",
    "getTopCandidates":           "json",
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
You are FounderFlow, an AI-powered business assistant. You MUST use tools to fulfil requests — never respond with plain text when a tool can handle it.

IMPORTANT — Conversation context:
- You receive the FULL conversation history in every turn. Use it to avoid asking for information the user has ALREADY provided in earlier messages.
- Before asking the user for any detail (email address, subject, job role, etc.), scan the conversation history first. If the information is already present, use it directly.
- Be proactive: infer intent and fill in obvious details from context rather than asking redundant questions.

Email flow:
- If the user's message (or conversation history) already contains enough info to compose the email (recipient, topic/context, and rough intent), call composeEmail IMMEDIATELY with original_request containing all gathered context. Do NOT ask for subject, body, or email separately — the composeEmail tool's internal LLM will infer subject, body, and destination_address from the original_request.
- Only ask the user for missing info if the recipient email OR the core purpose of the email is truly unclear from context.
- After composing, present the draft and wait for human approval.
- If human needs modification, send previous_draft with human feedback to composeEmail again. Always include previous_draft.
- After approval, call sendEmail.

Meet Scheduling flow:
- Call scheduleMeet tool to schedule a meeting according to user's request.

Image posting workflow:
- Call createImage tool to create the image.
- Wait for human approval.
- If human needs changes, send human feedback again to createImage tool.
- After confirmation, call postImage tool. postImage requires the image_url parameter.

LinkedIn workflow:
- Call generateLinkedInPost first.
- Wait for human approval.
- If human needs modification, send previous_draft with human feedback to generateLinkedInPost again. Always include previous_draft.
- After approval, call postLinkedIn.

Hiring workflow (for posting job openings):
- When user says they want to hire candidates, ask for job_role and description if not clearly provided.
- Call postHiringJob with job_role, description, and original_request.
- This tool generates a LinkedIn post (including the application link), posts it to LinkedIn, and saves the job to the database.
- Wait for human approval of the generated post draft.
- If human needs modification, send previous_draft with human feedback to postHiringJob again. Always include previous_draft.
- The application link https://founderflow-hiring-frontend-main.vercel.app/ is always included automatically.

Retrieving hiring candidates/results:
- When user asks for hiring results, candidates, or applicants for a role.
- If the user has NOT specified a job_role, call getAvailableRoles FIRST to fetch the list of posted roles from the database.
- Show the available roles to the user and ask them to pick one.
- Once the user picks a role, call getTopCandidates with that job_role (and optionally limit, default 5).
- This returns the top candidates sorted by ATS score with their name, email, job_role, resume_url, and ats_score.

Lead Generation workflow:
- Call searchLeads with appropriate parameters: keywords, industry, persona, company, location.
- Display the results to the user.

Score single lead:
- Call scoreLeadProfile with person details and target criteria.

Get previous lead report:
- Call getLeadReport to retrieve the most recent report.
"""


def build_system_prompt(memory_context: str = "") -> str:
    """Inject the user's memory context into the system prompt."""
    # ──────────────────────────────────────────────────────────
    # MEMORY DISABLED — temporarily commented out. Re-enable later.
    # ──────────────────────────────────────────────────────────
    # if not memory_context:
    #     return BASE_SYSTEM_PROMPT
    #
    # return BASE_SYSTEM_PROMPT + f"""
    #
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MEMORY CONTEXT (use this to personalise your responses)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # {memory_context}
    # """
    return BASE_SYSTEM_PROMPT


# ──────────────────────────────────────────────────────────────
# Graph factory
# ──────────────────────────────────────────────────────────────

async def create_agent_app(checkpointer=None):
    """
    Build and compile the LangGraph agent.

    Parameters
    ----------
    checkpointer : AsyncPostgresSaver | None
        MEMORY DISABLED — checkpointer is currently ignored. The graph is
        compiled without persistence. Re-enable later by restoring the
        `checkpointer=checkpointer` argument on graph.compile(...).
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
    llm   = ChatOpenAI(model="gpt-5", temperature=0)
    model = llm.bind_tools(tools)

    async def agent_node(state: AgentState):
        messages = state["messages"]
        # Inject system prompt if not already present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=build_system_prompt())] + list(messages)
        response = await model.ainvoke(messages)
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

    # MEMORY DISABLED — compile without checkpointer for now.
    # return graph.compile(checkpointer=checkpointer), llm
    return graph.compile(), llm