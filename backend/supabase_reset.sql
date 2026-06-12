-- ============================================================
-- LexAgent — Full Supabase Reset
-- DROPS EVERYTHING then recreates all tables + RPC + RLS.
-- Run this in the Supabase SQL Editor.
-- WARNING: This DELETES all data in the database.
-- ============================================================

-- ═══════════════════════════════════════════════════════════════
-- 0. Drop existing RLS policies (must be dropped before tables)
-- ═══════════════════════════════════════════════════════════════
DROP POLICY IF EXISTS "users_own" ON users;
DROP POLICY IF EXISTS "cases_own" ON cases;
DROP POLICY IF EXISTS "documents_own" ON case_documents;
DROP POLICY IF EXISTS "messages_own" ON case_messages;
DROP POLICY IF EXISTS "law_chunks_read" ON law_chunks;

-- ═══════════════════════════════════════════════════════════════
-- 1. Drop tables in reverse-dependency order
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS case_documents CASCADE;
DROP TABLE IF EXISTS case_messages  CASCADE;
DROP TABLE IF EXISTS law_chunks     CASCADE;
DROP TABLE IF EXISTS cases          CASCADE;
DROP TABLE IF EXISTS users          CASCADE;

-- ═══════════════════════════════════════════════════════════════
-- 2. Drop pgvector RPC function
-- ═══════════════════════════════════════════════════════════════
DROP FUNCTION IF EXISTS match_law_chunks;

-- ═══════════════════════════════════════════════════════════════
-- 3. Enable pgvector extension
-- ═══════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS vector;

-- ═══════════════════════════════════════════════════════════════
-- 4. users
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE users (
    id                 UUID PRIMARY KEY,
    email              VARCHAR NOT NULL UNIQUE,
    hashed_password    VARCHAR NOT NULL,
    full_name          VARCHAR NOT NULL,
    preferred_language VARCHAR NOT NULL DEFAULT 'en',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users (email);

-- ═══════════════════════════════════════════════════════════════
-- 5. cases
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE cases (
    id                   UUID PRIMARY KEY,
    user_id              UUID NOT NULL REFERENCES users(id),
    description          TEXT NOT NULL,
    language             VARCHAR DEFAULT 'en',
    case_type            VARCHAR,
    severity             VARCHAR,
    status               VARCHAR DEFAULT 'processing',
    relevant_sections    JSON DEFAULT '[]'::json,
    summary              TEXT,
    next_steps           JSON DEFAULT '[]'::json,
    agent_reasoning      TEXT,
    legal_notice_draft   TEXT,
    pdf_url              VARCHAR,
    pdf_id               VARCHAR,
    clarifying_questions JSON DEFAULT '[]'::json,
    action_buttons       JSON DEFAULT '[]'::json,
    ai_message           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ
);

CREATE INDEX idx_cases_user_id ON cases (user_id);

-- ═══════════════════════════════════════════════════════════════
-- 6. case_messages
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE case_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    extra_data  JSON DEFAULT '{}'::json,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_case_messages_case_id
    ON case_messages (case_id);

CREATE INDEX idx_case_messages_created_at
    ON case_messages (case_id, created_at ASC);

-- ═══════════════════════════════════════════════════════════════
-- 7. law_chunks
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE law_chunks (
    id              UUID PRIMARY KEY,
    act_name        VARCHAR NOT NULL,
    section_number  VARCHAR,
    section_title   VARCHAR,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    chunk_index     VARCHAR,
    metadata        JSON DEFAULT '{}'::json,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_law_chunks_act_name ON law_chunks (act_name);

-- ═══════════════════════════════════════════════════════════════
-- 8. case_documents
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE case_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    doc_type    VARCHAR NOT NULL,
    title       VARCHAR NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    status      VARCHAR DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ
);

CREATE INDEX idx_case_documents_case_id
    ON case_documents (case_id);

-- ═══════════════════════════════════════════════════════════════
-- 9. Row Level Security
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases          ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE law_chunks     ENABLE ROW LEVEL SECURITY;

-- Users: only see your own record
CREATE POLICY "users_own"
    ON users FOR ALL
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

-- Cases: only see your own cases
CREATE POLICY "cases_own"
    ON cases FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Documents: only see documents for your own cases
CREATE POLICY "documents_own"
    ON case_documents FOR ALL
    USING (
        case_id IN (SELECT id FROM cases WHERE user_id = auth.uid())
    )
    WITH CHECK (
        case_id IN (SELECT id FROM cases WHERE user_id = auth.uid())
    );

-- Messages: only see messages for your own cases
CREATE POLICY "messages_own"
    ON case_messages FOR ALL
    USING (
        case_id IN (SELECT id FROM cases WHERE user_id = auth.uid())
    )
    WITH CHECK (
        case_id IN (SELECT id FROM cases WHERE user_id = auth.uid())
    );

-- Law chunks: everyone can read
CREATE POLICY "law_chunks_read"
    ON law_chunks FOR SELECT
    USING (true);

-- ═══════════════════════════════════════════════════════════════
-- 10. pgvector RPC
-- ═══════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION match_law_chunks(
    query_embedding vector(1536),
    match_count    int DEFAULT 10
) RETURNS TABLE(
    id          UUID,
    act_name    VARCHAR,
    chunk_text  TEXT,
    similarity  float
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        lc.id::UUID,
        lc.act_name::VARCHAR,
        lc.chunk_text::TEXT,
        (1 - (lc.embedding <=> query_embedding))::float AS similarity
    FROM law_chunks lc
    ORDER BY lc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ═══════════════════════════════════════════════════════════════
SELECT '✓ Full reset complete — all tables created' AS result;
