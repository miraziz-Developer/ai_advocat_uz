"""PostgreSQL + pgvector storage: laws, users, chat history, payments."""
import re

import asyncpg

from app import config

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS laws (
    doc_id       BIGINT PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id        BIGSERIAL PRIMARY KEY,
    doc_id    BIGINT NOT NULL REFERENCES laws ON DELETE CASCADE,
    article   TEXT NOT NULL,
    heading   TEXT NOT NULL,
    anchor    BIGINT,
    body      TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    tsv       tsvector GENERATED ALWAYS AS (to_tsvector('simple', article || ' ' || body)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks (doc_id);

CREATE TABLE IF NOT EXISTS users (
    id          BIGINT PRIMARY KEY,
    credits     INT NOT NULL DEFAULT 0 CHECK (credits >= 0),
    pending_doc TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'model')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_user_idx ON messages (user_id, id DESC);

CREATE TABLE IF NOT EXISTS usage (
    user_id BIGINT NOT NULL,
    day     DATE NOT NULL,
    count   INT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS payments (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    amount     BIGINT,
    credits    INT NOT NULL DEFAULT 0,
    txn_id     TEXT UNIQUE,
    image_hash TEXT UNIQUE,
    status     TEXT NOT NULL,
    details    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # statement_cache_size=0 keeps it working behind PgBouncer (Supabase/Neon poolers).
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    return _pool


async def init() -> None:
    p = await pool()
    await p.execute(SCHEMA)


def vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


# ---------- laws ----------

async def law_hash(doc_id: int) -> str | None:
    return await (await pool()).fetchval("SELECT content_hash FROM laws WHERE doc_id=$1", doc_id)


async def replace_law(doc_id: int, title: str, url: str, content_hash: str, rows: list[tuple]) -> None:
    """rows: (article, heading, anchor, body, embedding). Atomic: old version stays until the new one is complete."""
    p = await pool()
    async with p.acquire() as con, con.transaction():
        await con.execute("DELETE FROM laws WHERE doc_id=$1", doc_id)
        await con.execute(
            "INSERT INTO laws (doc_id, title, url, content_hash) VALUES ($1,$2,$3,$4)",
            doc_id, title, url, content_hash,
        )
        await con.executemany(
            "INSERT INTO chunks (doc_id, article, heading, anchor, body, embedding) VALUES ($1,$2,$3,$4,$5,$6::vector)",
            [(doc_id, a, h, anc, b, vec(e)) for a, h, anc, b, e in rows],
        )


async def search(query_embedding: list[float] | None, query_text: str, limit: int = 8) -> list[asyncpg.Record]:
    """Hybrid search: vector similarity + keyword match, merged with reciprocal rank fusion.
    query_embedding=None -> keyword-only (embedding quota exhausted)."""
    sql = """
    WITH v AS (
        SELECT id, row_number() OVER (ORDER BY embedding <=> $1::vector) AS r
        FROM chunks WHERE $1::vector IS NOT NULL ORDER BY embedding <=> $1::vector LIMIT 30
    ), k AS (
        SELECT id, row_number() OVER (ORDER BY ts_rank(tsv, q) DESC) AS r
        FROM chunks, to_tsquery('simple', $2) q
        WHERE tsv @@ q ORDER BY ts_rank(tsv, q) DESC LIMIT 30
    ), fused AS (
        SELECT id, sum(1.0 / (60 + r)) AS score FROM (SELECT * FROM v UNION ALL SELECT * FROM k) x
        GROUP BY id ORDER BY score DESC LIMIT $3
    )
    SELECT c.article, c.heading, c.anchor, c.body, l.title, l.url
    FROM fused f JOIN chunks c ON c.id = f.id JOIN laws l ON l.doc_id = c.doc_id
    ORDER BY f.score DESC
    """
    embedding = vec(query_embedding) if query_embedding else None
    return await (await pool()).fetch(sql, embedding, or_query(query_text), limit)


def or_query(text: str) -> str:
    """Any-word match ('mehnat | shartnoma | ...'); AND of 15 words would almost never match."""
    words = dict.fromkeys(w for w in re.findall(r"\w+", text.lower()) if len(w) >= 3 or w.isdigit())
    return " | ".join(words)


# ---------- users / history / limits ----------

async def ensure_user(user_id: int) -> asyncpg.Record:
    return await (await pool()).fetchrow(
        "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO UPDATE SET id=EXCLUDED.id RETURNING *", user_id
    )


async def add_message(user_id: int, role: str, content: str) -> None:
    await (await pool()).execute(
        "INSERT INTO messages (user_id, role, content) VALUES ($1,$2,$3)", user_id, role, content
    )


async def history(user_id: int, limit: int = 10) -> list[asyncpg.Record]:
    rows = await (await pool()).fetch(
        "SELECT role, content FROM messages WHERE user_id=$1 ORDER BY id DESC LIMIT $2", user_id, limit
    )
    return list(reversed(rows))


async def clear_history(user_id: int) -> None:
    await (await pool()).execute("DELETE FROM messages WHERE user_id=$1", user_id)


async def take_daily_quota(user_id: int, limit: int) -> bool:
    """Counts one request; False when today's free limit is used up (Tashkent day)."""
    count = await (await pool()).fetchval(
        """INSERT INTO usage (user_id, day, count) VALUES ($1, (now() AT TIME ZONE 'Asia/Tashkent')::date, 1)
           ON CONFLICT (user_id, day) DO UPDATE SET count = usage.count + 1 RETURNING count""",
        user_id,
    )
    return count <= limit


async def set_pending_doc(user_id: int, description: str | None) -> None:
    await (await pool()).execute("UPDATE users SET pending_doc=$2 WHERE id=$1", user_id, description)


async def spend_credit(user_id: int) -> bool:
    row = await (await pool()).fetchval(
        "UPDATE users SET credits=credits-1 WHERE id=$1 AND credits>0 RETURNING credits", user_id
    )
    return row is not None


async def add_credits(user_id: int, n: int) -> int:
    await ensure_user(user_id)
    return await (await pool()).fetchval(
        "UPDATE users SET credits=GREATEST(credits+$2, 0) WHERE id=$1 RETURNING credits", user_id, n
    )


# ---------- payments ----------

async def receipt_seen(txn_id: str | None, image_hash: str) -> bool:
    return bool(await (await pool()).fetchval(
        "SELECT 1 FROM payments WHERE image_hash=$1 OR ($2::text IS NOT NULL AND txn_id=$2)", image_hash, txn_id
    ))


async def record_payment(user_id: int, amount: int | None, credits: int, txn_id: str | None,
                         image_hash: str, status: str, details: str) -> int | None:
    """Returns payment id, or None if this receipt was already used (unique constraint race).
    Only approved receipts reserve txn_id/image_hash, so a wrongly rejected receipt can be resent."""
    approved = status == "approved"
    try:
        return await (await pool()).fetchval(
            """INSERT INTO payments (user_id, amount, credits, txn_id, image_hash, status, details)
               VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb) RETURNING id""",
            user_id, amount, credits, txn_id if approved else None, image_hash if approved else None, status, details,
        )
    except asyncpg.UniqueViolationError:
        return None


async def revoke_payment(payment_id: int) -> asyncpg.Record | None:
    p = await pool()
    async with p.acquire() as con, con.transaction():
        row = await con.fetchrow(
            "UPDATE payments SET status='revoked' WHERE id=$1 AND status='approved' RETURNING user_id, credits",
            payment_id,
        )
        if row:
            await con.execute(
                "UPDATE users SET credits=GREATEST(credits-$2, 0) WHERE id=$1", row["user_id"], row["credits"]
            )
        return row


async def stats() -> asyncpg.Record:
    return await (await pool()).fetchrow(
        """SELECT (SELECT count(*) FROM users) AS users,
                  (SELECT count(*) FROM laws) AS laws,
                  (SELECT count(*) FROM chunks) AS chunks,
                  (SELECT count(*) FROM payments WHERE status='approved') AS paid,
                  (SELECT coalesce(sum(amount),0) FROM payments WHERE status='approved') AS revenue"""
    )
