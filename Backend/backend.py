"""
backend.py
==========
FounderFlow — FastAPI HTTP Backend

Memory architecture
-------------------
A single MemoryManager instance is created at startup (lifespan) and
shared across ALL requests.  This means:

  • One asyncpg connection pool    → efficient, no per-request reconnects
  • One LangGraph checkpointer     → consistent checkpoint writes
  • Memory reads  happen at the START of every new user query
  • Memory writes happen at the END of every completed session

Per-session state is tracked in the `_sessions` dict:
  {
      session_id: {
          "user_id":          str,
          "thread_id":        str,          ← unique per HTTP session
          "app":              compiled graph,
          "llm":              ChatOpenAI,
          "pending_approval": bool,
          "approval_payload": dict | None,
          "final_state":      dict | None,  ← stored after each invoke
      }
  }
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

# ── project imports ───────────────────────────────────────────
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from Backend.memory import MemoryManager, make_thread_id
from client.client import (
    AgentState,
    TOOL_STATE_MAP,
    TOOL_OUTPUT_TYPE,
    build_system_prompt,
    create_agent_app,
    get_tool_name,
    extract_tool_payload,
)

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


# ──────────────────────────────────────────────────────────────
# Global memory manager  (one per process)
# ──────────────────────────────────────────────────────────────

_memory: MemoryManager | None = None


def get_memory() -> MemoryManager:
    if _memory is None:
        raise RuntimeError("MemoryManager not initialised — lifespan error.")
    return _memory


# ──────────────────────────────────────────────────────────────
# FastAPI lifespan  (startup / shutdown)
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _memory
    print("[Startup] Initialising MemoryManager...")
    _memory = MemoryManager()
    await _memory.init()
    print("[Startup] MemoryManager ready.")
    yield
    # ── shutdown ──
    print("[Shutdown] Closing MemoryManager...")
    await _memory.close()
    print("[Shutdown] Done.")


# ──────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="FounderFlow Backend", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────
# In-memory session store
# ──────────────────────────────────────────────────────────────

_sessions: Dict[str, Dict[str, Any]] = {}


def _new_session_record(user_id: str) -> dict:
    return {
        "user_id":          user_id,
        "thread_id":        make_thread_id(user_id),
        "app":              None,   # compiled graph — built lazily
        "llm":              None,   # ChatOpenAI — returned by create_agent_app
        "pending_approval": False,
        "approval_payload": None,
        "final_state":      None,
    }


async def _get_or_create_session(session_id: str | None, user_id: str) -> tuple[str, dict]:
    """
    Return (session_id, session_record).
    If session_id is None or unknown, a new session is created.
    """
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]

    new_id = str(uuid.uuid4())
    _sessions[new_id] = _new_session_record(user_id)
    return new_id, _sessions[new_id]


async def _ensure_app(session: dict) -> None:
    """Build the compiled graph + llm for a session if not yet done."""
    if session["app"] is None:
        memory = get_memory()
        checkpointer = memory.get_checkpointer()
        session["app"], session["llm"] = await create_agent_app(
            checkpointer=checkpointer
        )


# ──────────────────────────────────────────────────────────────
# Post-session memory persistence  (fire-and-forget helper)
# ──────────────────────────────────────────────────────────────

async def _persist_session_memory(session: dict, final_state: dict) -> None:
    """
    Runs after a session completes:
      1. Save session record
      2. Extract + update user profile preferences
      3. Save episode summary + embedding

    Errors are caught and logged — they must never crash the HTTP response.
    """
    memory  = get_memory()
    user_id = session["user_id"]
    thread_id = session["thread_id"]
    llm     = session["llm"]
    messages = final_state.get("messages", [])

    try:
        session_id = await memory.save_session(
            user_id=user_id,
            thread_id=thread_id,
            messages=messages,
            final_state=final_state,
        )
        print(f"[Memory] Session record saved: {session_id}")
    except Exception as exc:
        print(f"[Memory][ERROR] save_session failed: {exc}")
        return

    try:
        profile_updates = await memory.extract_profile_updates(messages, llm)
        if profile_updates:
            await memory.update_user_profile(user_id, profile_updates)
            print(f"[Memory] Profile updated: {list(profile_updates.keys())}")
    except Exception as exc:
        print(f"[Memory][ERROR] profile update failed: {exc}")

    try:
        await memory.save_episode(
            user_id=user_id,
            session_id=session_id,
            messages=messages,
            llm=llm,
        )
        print("[Memory] Episode saved.")
    except Exception as exc:
        print(f"[Memory][ERROR] save_episode failed: {exc}")


# ──────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:      str
    session_id: Optional[str] = None
    user_id:    str = "user_default"   # pass from auth layer in production


class ChatResponse(BaseModel):
    session_id:       str
    message:          str
    needs_approval:   bool = False
    approval_summary: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Approval summary formatter
# ──────────────────────────────────────────────────────────────

def _format_approval_summary(tool_name: str | None, payload: Any) -> str:
    if isinstance(payload, dict):
        parts = []
        if "subject" in payload:
            parts.append(f"**Subject:** {payload['subject']}")
        if "destination_address" in payload:
            parts.append(f"**To:** {payload['destination_address']}")
        if "body" in payload:
            parts.append(f"**Body:**\n```\n{payload['body'][:300]}...\n```")
        if "content" in payload:
            parts.append(f"**Content Preview:**\n```\n{payload['content'][:500]}...\n```")
        if "form_url" in payload:
            parts.append(f"**Form URL:** {payload['form_url']}")
        if parts:
            return "\n\n".join(parts)

    return f"```json\n{json.dumps(payload, indent=2)[:800]}\n```"


# ──────────────────────────────────────────────────────────────
# Main chat endpoint
# ──────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id, session = await _get_or_create_session(request.session_id, request.user_id)
    await _ensure_app(session)

    memory = get_memory()
    app_graph = session["app"]
    config    = {"configurable": {"thread_id": session["thread_id"]}}

    try:
        # ── Branch A: user is responding to a pending approval ──────────
        if session["pending_approval"]:
            user_input = request.query.strip().lower()
            session["pending_approval"]  = False
            session["approval_payload"]  = None

            if user_input == "yes":
                # Approved — let the agent proceed to the final action
                new_state = await app_graph.ainvoke(
                    {"messages": [HumanMessage(content="Human Response: yes")]},
                    config=config,
                )
            else:
                # Feedback for revision
                new_state = await app_graph.ainvoke(
                    {"messages": [HumanMessage(content=f"Human Response: {request.query}")]},
                    config=config,
                )

            session["final_state"] = new_state

            # Check if another approval round is needed
            last_msg = new_state["messages"][-1]
            if _needs_approval(last_msg):
                return _approval_response(session_id, session, last_msg, new_state)

            # Session complete — persist memory in background
            asyncio.create_task(_persist_session_memory(session, new_state))

            return ChatResponse(
                session_id=session_id,
                message=_extract_text(last_msg),
            )

        # ── Branch B: fresh query ────────────────────────────────────────
        print(f"[Memory] Loading context for user={session['user_id']}...")
        memory_context = await memory.build_session_context(
            session["user_id"], request.query
        )
        system_prompt = build_system_prompt(memory_context)

        initial_messages = [
            HumanMessage(content=system_prompt),
            HumanMessage(content=request.query),
            AIMessage(content="Executing"),
        ]

        new_state = await app_graph.ainvoke(
            {
                "messages":       initial_messages,
                "previous_draft": None,
                "image_url":      None,
                "linkedin_draft": None,
                "hiring_draft":   None,
                "lead_report":    None,
            },
            config=config,
        )

        session["final_state"] = new_state
        last_msg = new_state["messages"][-1]

        # Check if the agent paused for approval
        if _needs_approval(last_msg):
            return _approval_response(session_id, session, last_msg, new_state)

        # No approval needed — persist memory and return
        asyncio.create_task(_persist_session_memory(session, new_state))

        return ChatResponse(
            session_id=session_id,
            message=_extract_text(last_msg),
        )

    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# ──────────────────────────────────────────────────────────────
# Helpers for chat endpoint
# ──────────────────────────────────────────────────────────────

def _extract_text(msg) -> str:
    return msg.content if hasattr(msg, "content") and isinstance(msg.content, str) else str(msg)


def _needs_approval(last_msg) -> bool:
    """
    In backend (non-CLI) mode the graph no longer has a blocking human_review
    node. Instead we detect that the agent has produced a tool result that
    should be shown to the user before proceeding.

    Heuristic: the last message is an AIMessage whose content asks for
    confirmation, OR it is a ToolMessage whose tool is in TOOL_STATE_MAP.
    Adjust this logic to match your actual agent behaviour.
    """
    from langchain_core.messages import AIMessage as AI, ToolMessage as TM

    if isinstance(last_msg, TM):
        return True   # every tool result goes through approval in this workflow

    if isinstance(last_msg, AI) and last_msg.content:
        keywords = ["approve", "confirm", "review", "looks good?", "shall i proceed"]
        content_lower = last_msg.content.lower()
        return any(k in content_lower for k in keywords)

    return False


def _approval_response(
    session_id: str,
    session: dict,
    last_msg,
    state: dict,
) -> ChatResponse:
    """Store approval state and return the approval response to the frontend."""
    from langchain_core.messages import ToolMessage as TM

    tool_name = None
    payload   = None

    if isinstance(last_msg, TM):
        messages  = state.get("messages", [])
        tool_name = get_tool_name(messages, last_msg)
        payload   = extract_tool_payload(tool_name, last_msg.content)

    session["pending_approval"]  = True
    session["approval_payload"]  = {"tool_name": tool_name, "payload": payload}

    summary = _format_approval_summary(tool_name, payload)

    return ChatResponse(
        session_id=session_id,
        message="Here's what I've prepared. Please review and reply **yes** to proceed or send feedback to revise:",
        needs_approval=True,
        approval_summary=summary,
    )


# ──────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "active_sessions": len(_sessions)}


# ──────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("FounderFlow Backend Server Starting...")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")