"""
app.py
======
FounderFlow — Simplified FastAPI Backend (Memory-Free)

This is a lightweight chat API that uses the client module to generate
responses without persistent memory or database integration.
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel
from pymongo import MongoClient

from client.client import (
    create_agent_app,
    get_tool_name,
    extract_tool_payload,
    TOOL_STATE_MAP,
)

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Global agent state
# ──────────────────────────────────────────────────────────────

_agent_app = None
_agent_llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup."""
    global _agent_app, _agent_llm
    print("[Startup] Building agent graph...")
    _agent_app, _agent_llm = await create_agent_app(checkpointer=None)
    print("[Startup] Agent ready.")
    yield
    print("[Shutdown] Cleaning up...")


# ──────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="FounderFlow Chat API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── MongoDB (for resume downloads) ───────────────────────────
_mongo_client = MongoClient(os.getenv("MONGO_URI"))
_responses_col = _mongo_client["hiring_deployments"]["responses"]

MIME_MAP = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@app.get("/resume/{email}/{filename}")
async def download_resume(email: str, filename: str):
    """Serve the actual resume binary stored in MongoDB."""
    doc = _responses_col.find_one(
        {"email": email, "resume_filename": filename},
        {"resume_data": 1, "resume_filename": 1},
    )
    if not doc or "resume_data" not in doc:
        raise HTTPException(status_code=404, detail="Resume not found")

    ext = os.path.splitext(filename)[1].lower()
    content_type = MIME_MAP.get(ext, "application/octet-stream")

    return Response(
        content=bytes(doc["resume_data"]),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ──────────────────────────────────────────────────────────────
# In-memory session store (no persistence)
# ──────────────────────────────────────────────────────────────

_sessions: Dict[str, Dict[str, Any]] = {}


def _new_session(user_id: str) -> dict:
    """Create a new session record."""
    return {
        "user_id":          user_id,
        "thread_id":        f"thread_{uuid.uuid4().hex[:8]}",
        "pending_approval": False,
        "approval_payload": None,
        "final_state":      None,
        "message_history":  [],   # accumulated messages for context
    }


def _get_or_create_session(session_id: str | None, user_id: str) -> tuple[str, dict]:
    """Return (session_id, session_dict)."""
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    
    new_id = str(uuid.uuid4())
    _sessions[new_id] = _new_session(user_id)
    return new_id, _sessions[new_id]


# ──────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:      str
    session_id: Optional[str] = None
    user_id:    str = "user_default"


class ChatResponse(BaseModel):
    session_id:       str
    message:          str
    needs_approval:   bool = False
    approval_summary: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────

def _extract_text(msg) -> str:
    """Extract text content from message."""
    if hasattr(msg, "content") and isinstance(msg.content, str):
        return msg.content
    return str(msg)


def _needs_approval(last_msg) -> bool:
    """Check if the last message requires user approval."""
    # Tool messages always need approval
    if isinstance(last_msg, ToolMessage):
        return True
    
    # AI messages with approval keywords
    if isinstance(last_msg, AIMessage) and last_msg.content:
        keywords = ["approve", "confirm", "review", "looks good", "shall i proceed"]
        content_lower = last_msg.content.lower()
        return any(k in content_lower for k in keywords)
    
    return False


def _format_approval_summary(tool_name: str | None, payload: Any) -> str:
    """Format approval payload for display."""
    if isinstance(payload, dict):
        parts = []
        
        # Email-specific fields
        if "subject" in payload:
            parts.append(f"**Subject:** {payload['subject']}")
        if "destination_address" in payload:
            parts.append(f"**To:** {payload['destination_address']}")
        if "body" in payload:
            body_preview = payload['body'][:300]
            parts.append(f"**Body:**\n```\n{body_preview}...\n```")
        
        # LinkedIn/Hiring post fields
        if "content" in payload:
            content_preview = payload['content'][:500]
            parts.append(f"**Content Preview:**\n```\n{content_preview}...\n```")
        
        # Form URL
        if "form_url" in payload:
            parts.append(f"**Form URL:** {payload['form_url']}")
        
        # Image URL
        if "image_url" in payload:
            parts.append(f"**Image URL:** {payload['image_url']}")
        
        if parts:
            return "\n\n".join(parts)
    
    # Fallback: JSON dump
    return f"```json\n{json.dumps(payload, indent=2)[:800]}\n```"


# ──────────────────────────────────────────────────────────────
# Chat endpoint
# ──────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    
    Handles:
    - Fresh queries: processes user input through the agent
    - Approval responses: continues execution after user confirmation/feedback
    """
    session_id, session = _get_or_create_session(request.session_id, request.user_id)
    
    if _agent_app is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    config = {"configurable": {"thread_id": session["thread_id"]}}
    
    try:
        history = session["message_history"]

        # ── Handle pending approval response ──────────────────────────
        if session["pending_approval"]:
            user_input = request.query.strip().lower()
            session["pending_approval"] = False
            session["approval_payload"] = None

            if user_input == "yes":
                human_msg = HumanMessage(content="Human Response: yes")
            else:
                human_msg = HumanMessage(content=f"Human Response: {request.query}")

            history.append(human_msg)

            new_state = await _agent_app.ainvoke(
                {"messages": list(history)},
                config=config,
            )

            # Save returned messages as the new history
            session["message_history"] = list(new_state["messages"])
            session["final_state"] = new_state
            last_msg = new_state["messages"][-1]

            # Check if another approval is needed
            if _needs_approval(last_msg):
                return _create_approval_response(session_id, session, last_msg, new_state)

            # Task complete
            return ChatResponse(
                session_id=session_id,
                message=_extract_text(last_msg),
            )

        # ── Handle fresh / follow-up query ─────────────────────────────
        human_msg = HumanMessage(content=request.query)
        history.append(human_msg)

        new_state = await _agent_app.ainvoke(
            {
                "messages":       list(history),
                "previous_draft": None,
                "image_url":      None,
                "linkedin_draft": None,
                "hiring_draft":   None,
                "lead_report":    None,
            },
            config=config,
        )

        # Save returned messages as the new history
        session["message_history"] = list(new_state["messages"])
        session["final_state"] = new_state
        last_msg = new_state["messages"][-1]

        # Check if approval is needed
        if _needs_approval(last_msg):
            return _create_approval_response(session_id, session, last_msg, new_state)

        # Direct response
        return ChatResponse(
            session_id=session_id,
            message=_extract_text(last_msg),
        )
    
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


def _create_approval_response(
    session_id: str,
    session: dict,
    last_msg,
    state: dict,
) -> ChatResponse:
    """Create an approval response for the user."""
    tool_name = None
    payload = None
    messages = state.get("messages", [])

    if isinstance(last_msg, ToolMessage):
        tool_name = get_tool_name(messages, last_msg)
        payload = extract_tool_payload(tool_name, last_msg.content)
    else:
        # last_msg is an AIMessage asking for approval — look back for the
        # most recent ToolMessage to extract the draft/payload for preview.
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                tool_name = get_tool_name(messages, msg)
                payload = extract_tool_payload(tool_name, msg.content)
                break

    session["pending_approval"] = True
    session["approval_payload"] = {"tool_name": tool_name, "payload": payload}

    # Use the AI's own message as the review prompt, fall back to generic
    ai_text = ""
    if isinstance(last_msg, AIMessage) and last_msg.content:
        ai_text = last_msg.content

    summary = _format_approval_summary(tool_name, payload)

    return ChatResponse(
        session_id=session_id,
        message=ai_text or "Here's what I've prepared. Please review and reply **yes** to proceed or send feedback to revise:",
        needs_approval=True,
        approval_summary=summary,
    )


# ──────────────────────────────────────────────────────────────
# Additional endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_sessions": len(_sessions),
        "agent_ready": _agent_app is not None,
    }


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a specific session."""
    if session_id in _sessions:
        del _sessions[session_id]
        return {"message": f"Session {session_id} deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    return {
        "total": len(_sessions),
        "sessions": [
            {
                "session_id": sid,
                "user_id": data["user_id"],
                "thread_id": data["thread_id"],
                "pending_approval": data["pending_approval"],
            }
            for sid, data in _sessions.items()
        ],
    }


# ──────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("FounderFlow Chat API Starting...")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
