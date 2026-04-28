"""
memory.py
=========
FounderFlow — Production Memory Management
------------------------------------------
Handles all five memory layers:
  1. Conversational + Working State  →  LangGraph AsyncPostgresSaver (checkpointer)
  2. Session Memory                  →  `sessions` table
  3. User / Long-Term Memory         →  `user_profiles` table
  4. Episodic Memory                 →  `episodes` table  +  pgvector embeddings

Usage (from client.py):
    from memory import MemoryManager
    memory = MemoryManager()
    await memory.init()                        # call once at startup
    checkpointer = memory.get_checkpointer()   # pass to graph.compile()
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

import asyncpg
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_openai import OpenAIEmbeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Config — read from .env
# ──────────────────────────────────────────────────────────────

POSTGRES_USER     = os.getenv("POSTGRES_USER",     "founderflow")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "founderflow_secret")
POSTGRES_HOST     = os.getenv("POSTGRES_HOST",     "localhost")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT",     "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB",       "founderflow_db")

# asyncpg connection string
DB_URL = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# psycopg connection string  (LangGraph AsyncPostgresSaver uses psycopg3)
DB_URL_PSYCOPG = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def make_thread_id(user_id: str) -> str:
    """Generate a unique thread ID scoped to a user."""
    return f"{user_id}:{uuid.uuid4().hex}"


def _serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to plain dicts for storage."""
    result = []
    for m in messages:
        result.append({
            "type":    m.__class__.__name__,
            "content": m.content if isinstance(m.content, str) else json.dumps(m.content),
        })
    return result


def _detect_task_type(messages: list[BaseMessage]) -> str:
    """Infer the task type from the conversation messages."""
    text = " ".join(
        m.content if isinstance(m.content, str) else ""
        for m in messages
    ).lower()

    if any(k in text for k in ["sendemail", "composeemail", "send email", "compose email"]):
        return "email"
    if any(k in text for k in ["linkedin", "generatelinkedinpost"]):
        return "linkedin_post"
    if any(k in text for k in ["hiring", "generatehiringpost", "createhiringform"]):
        return "hiring_post"
    if any(k in text for k in ["searchleads", "lead", "prospect"]):
        return "lead_search"
    if any(k in text for k in ["createimage", "postimage", "instagram"]):
        return "image_post"
    if any(k in text for k in ["schedulemeet", "meet", "calendar"]):
        return "meet_schedule"
    return "general"


# ──────────────────────────────────────────────────────────────
# MemoryManager
# ──────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Central memory manager for FounderFlow.

    Lifecycle:
        memory = MemoryManager()
        await memory.init()          # open DB pool + setup LangGraph checkpointer
        ...
        await memory.close()         # on shutdown
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._checkpointer: AsyncPostgresSaver | None = None
        self._embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # ──────────────────────────────────────────
    # Init / teardown
    # ──────────────────────────────────────────

    async def init(self) -> None:
        """
        Open the asyncpg connection pool and set up the LangGraph checkpointer.
        Call once at application startup.
        """
        # 1. Raw asyncpg pool — used for sessions, profiles, episodes
        self._pool = await asyncpg.create_pool(
            dsn=DB_URL,
            min_size=2,
            max_size=10,
        )
        print("[Memory] asyncpg pool connected.")

        # 2. LangGraph checkpointer — manages conversational + working state memory
        #    AsyncPostgresSaver uses psycopg3 internally
        self._checkpointer = AsyncPostgresSaver.from_conn_string(DB_URL_PSYCOPG)
        await self._checkpointer.setup()   # creates checkpoint tables if they don't exist
        print("[Memory] LangGraph checkpointer ready.")

    async def close(self) -> None:
        """Close the connection pool on shutdown."""
        if self._pool:
            await self._pool.close()
            print("[Memory] Pool closed.")

    # ──────────────────────────────────────────
    # Layer 1 + 2 : Conversational & Working State Memory
    # ──────────────────────────────────────────

    def get_checkpointer(self) -> AsyncPostgresSaver:
        """
        Returns the LangGraph checkpointer.
        Pass this to graph.compile(checkpointer=...).

        LangGraph automatically:
          - Loads the checkpoint before every node execution
          - Saves the checkpoint (messages + all state fields) after every node execution
        """
        if self._checkpointer is None:
            raise RuntimeError("MemoryManager.init() has not been called.")
        return self._checkpointer

    # ──────────────────────────────────────────
    # Layer 3 : Session Memory
    # ──────────────────────────────────────────

    async def save_session(
        self,
        user_id: str,
        thread_id: str,
        messages: list[BaseMessage],
        final_state: dict,
    ) -> str:
        """
        Called at the END of a session (after app.ainvoke completes).
        Stores a structured record of what was accomplished.

        Returns the new session_id.
        """
        session_id  = uuid.uuid4().hex
        task_type   = _detect_task_type(messages)

        # Extract the final meaningful output from state based on task type
        output_key_map = {
            "email":        "previous_draft",
            "linkedin_post": "linkedin_draft",
            "hiring_post":  "hiring_draft",
            "lead_search":  "lead_report",
            "image_post":   "image_url",
        }
        output_key   = output_key_map.get(task_type)
        final_output = final_state.get(output_key) if output_key else None

        await self._pool.execute(
            """
            INSERT INTO sessions (session_id, user_id, thread_id, task_type, final_output, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'completed', NOW())
            """,
            session_id,
            user_id,
            thread_id,
            task_type,
            json.dumps(final_output) if final_output else None,
        )
        print(f"[Memory] Session saved: {session_id} | task={task_type}")
        return session_id

    async def get_recent_sessions(
        self,
        user_id: str,
        task_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Fetch recent sessions for a user.
        Optionally filter by task_type (e.g. "email", "lead_search").

        Used when user asks: "show me emails I sent this week"
        """
        if task_type:
            rows = await self._pool.fetch(
                """
                SELECT session_id, task_type, final_output, created_at
                FROM sessions
                WHERE user_id = $1 AND task_type = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                user_id, task_type, limit,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT session_id, task_type, final_output, created_at
                FROM sessions
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id, limit,
            )

        return [
            {
                "session_id":   r["session_id"],
                "task_type":    r["task_type"],
                "final_output": json.loads(r["final_output"]) if r["final_output"] else None,
                "created_at":   r["created_at"].isoformat(),
            }
            for r in rows
        ]

    # ──────────────────────────────────────────
    # Layer 4 : User / Long-Term Memory
    # ──────────────────────────────────────────

    async def get_user_profile(self, user_id: str) -> dict:
        """
        Fetch the user's persistent preference profile.
        Called at SESSION START — injected into the system prompt.

        Returns empty dict if no profile exists yet.
        """
        row = await self._pool.fetchrow(
            "SELECT preferences FROM user_profiles WHERE user_id = $1",
            user_id,
        )
        if row:
            return json.loads(row["preferences"])
        return {}

    async def update_user_profile(self, user_id: str, updates: dict) -> None:
        """
        Merge new preference observations into the existing profile.
        Called at SESSION END.

        Uses JSONB || operator to merge — never overwrites the whole profile.

        `updates` example:
            {
                "email_tone": "formal",
                "linkedin_audience": "B2B SaaS founders",
                "default_lead_persona": "CTO"
            }
        """
        await self._pool.execute(
            """
            INSERT INTO user_profiles (user_id, preferences, created_at, updated_at)
            VALUES ($1, $2::jsonb, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET preferences = user_profiles.preferences || $2::jsonb,
                    updated_at  = NOW()
            """,
            user_id,
            json.dumps(updates),
        )
        print(f"[Memory] User profile updated for {user_id}: {list(updates.keys())}")

    def build_profile_context(self, profile: dict) -> str:
        """
        Convert the user profile dict into a readable string
        to inject into the system prompt.
        """
        if not profile:
            return ""

        lines = ["User preferences (remembered from past sessions):"]
        for key, value in profile.items():
            readable_key = key.replace("_", " ").capitalize()
            lines.append(f"  - {readable_key}: {value}")
        return "\n".join(lines)

    async def extract_profile_updates(
        self,
        messages: list[BaseMessage],
        llm: Any,
    ) -> dict:
        """
        After a session, ask the LLM to extract any new user preferences
        revealed during the conversation.

        Returns a dict of preference key-value pairs to upsert.
        """
        conversation_text = "\n".join(
            f"{m.__class__.__name__}: {m.content if isinstance(m.content, str) else '[tool output]'}"
            for m in messages[-20:]  # last 20 messages to keep it focused
        )

        prompt = f"""
You are analyzing a conversation to extract user preferences.

Conversation:
{conversation_text}

Extract any preferences the user revealed. Return ONLY a JSON object.
If no new preferences were revealed, return {{}}.

Keys to look for (use these exact key names):
- email_tone (formal/casual)
- linkedin_audience
- default_lead_persona
- default_lead_industry
- default_lead_location
- email_signature
- brand_voice

Example output:
{{"email_tone": "formal", "default_lead_persona": "CTO"}}
"""
        try:
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            text = response.content.strip()
            # Strip markdown fences if present
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            print(f"[Memory] Profile extraction failed: {e}")
            return {}

    # ──────────────────────────────────────────
    # Layer 5 : Episodic Memory
    # ──────────────────────────────────────────

    async def save_episode(
        self,
        user_id: str,
        session_id: str,
        messages: list[BaseMessage],
        llm: Any,
    ) -> None:
        """
        Called at SESSION END.
        1. LLM summarizes the session into a 3-5 sentence narrative
        2. Summary is embedded using OpenAI embeddings
        3. Stored in the `episodes` table with the vector
        """
        conversation_text = "\n".join(
            f"{m.__class__.__name__}: {m.content if isinstance(m.content, str) else '[tool output]'}"
            for m in messages[-30:]
        )

        # Step 1 — Generate narrative summary
        summary_prompt = f"""
Summarize what happened in this AI agent session in 3-5 sentences.
Include: what the user wanted, what tools were used, what the final outcome was, and any notable decisions made.
Be specific — include names, job titles, topics where mentioned.

Conversation:
{conversation_text}

Summary:"""

        try:
            summary_response = await llm.ainvoke([{"role": "user", "content": summary_prompt}])
            summary = summary_response.content.strip()
        except Exception as e:
            print(f"[Memory] Episode summarization failed: {e}")
            return

        # Step 2 — Embed the summary
        try:
            embedding = await self._embeddings.aembed_query(summary)
        except Exception as e:
            print(f"[Memory] Embedding failed: {e}")
            return

        # Step 3 — Store in pgvector
        episode_id = uuid.uuid4().hex
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        await self._pool.execute(
            """
            INSERT INTO episodes (episode_id, user_id, session_id, summary, embedding, created_at)
            VALUES ($1, $2, $3, $4, $5::vector, NOW())
            """,
            episode_id,
            user_id,
            session_id,
            summary,
            embedding_str,
        )
        print(f"[Memory] Episode saved: {episode_id}")

    async def search_episodes(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """
        Called at SESSION START.
        Embeds the user's current request and searches for semantically
        similar past episodes using cosine similarity.

        Returns top_k most relevant past episodes.
        """
        try:
            query_embedding = await self._embeddings.aembed_query(query)
        except Exception as e:
            print(f"[Memory] Episode search embedding failed: {e}")
            return []

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        rows = await self._pool.fetch(
            """
            SELECT episode_id, summary, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM episodes
            WHERE user_id = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            embedding_str,
            user_id,
            top_k,
        )

        return [
            {
                "episode_id": r["episode_id"],
                "summary":    r["summary"],
                "similarity": round(float(r["similarity"]), 3),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    def build_episode_context(self, episodes: list[dict]) -> str:
        """
        Convert retrieved episodes into a readable string
        to inject into the system prompt.
        """
        if not episodes:
            return ""

        lines = ["Relevant past sessions (for context):"]
        for ep in episodes:
            date_str = ep["created_at"][:10]   # YYYY-MM-DD
            lines.append(f"  [{date_str}] {ep['summary']}")
        return "\n".join(lines)

    # ──────────────────────────────────────────
    # Convenience: build full context string
    # ──────────────────────────────────────────

    async def build_session_context(
        self,
        user_id: str,
        user_query: str,
    ) -> str:
        """
        Single call to build the full memory context for a new session.
        Combines user profile + relevant past episodes.

        Inject the returned string into the system prompt.
        """
        profile  = await self.get_user_profile(user_id)
        episodes = await self.search_episodes(user_id, user_query)

        parts = []

        profile_ctx = self.build_profile_context(profile)
        if profile_ctx:
            parts.append(profile_ctx)

        episode_ctx = self.build_episode_context(episodes)
        if episode_ctx:
            parts.append(episode_ctx)

        return "\n\n".join(parts)
