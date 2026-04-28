-- ============================================================
-- FounderFlow DB Init
-- Runs automatically when the Postgres container first starts
-- ============================================================

-- Enable pgvector for episodic memory embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. USER PROFILES  (long-term memory)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         TEXT PRIMARY KEY,
    preferences     JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. SESSIONS  (session memory — one row per completed task)
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    thread_id       TEXT NOT NULL,
    task_type       TEXT,                   -- "email" | "lead_search" | "linkedin_post" | etc.
    final_output    JSONB,                  -- final approved output
    status          TEXT DEFAULT 'completed',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id   ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_task_type ON sessions(user_id, task_type);
CREATE INDEX IF NOT EXISTS idx_sessions_created   ON sessions(created_at DESC);

-- ============================================================
-- 3. EPISODES  (episodic memory — summarised + embedded)
-- ============================================================
CREATE TABLE IF NOT EXISTS episodes (
    episode_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    summary         TEXT NOT NULL,          -- LLM-generated narrative summary
    embedding       vector(1536),           -- OpenAI text-embedding-3-small dimension
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_episodes_user_id ON episodes(user_id);

-- Vector similarity index (cosine distance) — used for semantic search
CREATE INDEX IF NOT EXISTS idx_episodes_embedding
    ON episodes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================================
-- 4. CHECKPOINTS  (managed by LangGraph AsyncPostgresSaver)
--    LangGraph creates these tables itself — listed here for reference only
--    Tables: checkpoints, checkpoint_writes, checkpoint_blobs
-- ============================================================
