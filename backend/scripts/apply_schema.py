"""Apply the pgvector RPC function to Supabase.

If SUPABASE_DB_URL is set in .env, this will execute the SQL directly.
Otherwise, prints the SQL to run manually in Supabase SQL Editor.

Usage:
    python scripts/apply_schema.py
"""

import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.config import settings

SQL = """
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
        lc.id,
        lc.act_name,
        lc.chunk_text,
        1 - (lc.embedding <=> query_embedding) AS similarity
    FROM law_chunks lc
    ORDER BY lc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
"""


def apply_via_psycopg2(db_url: str) -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.close()
        print("✓ RPC function created successfully")
        return True
    except Exception as e:
        print(f"✗ psycopg2 failed: {e}")
        return False


def main():
    db_url = os.getenv("SUPABASE_DB_URL") or getattr(settings, "SUPABASE_DB_URL", None)
    if db_url:
        if apply_via_psycopg2(db_url):
            return
        print("Trying direct connection via psycopg2 failed.")
        print()

    print("=" * 60)
    print("Run this SQL in your Supabase SQL Editor to create the RPC function:")
    print("=" * 60)
    print(SQL)
    print("=" * 60)


if __name__ == "__main__":
    main()
