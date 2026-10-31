"""PostgreSQL + pgvector storage: laws, users, chat history, payments."""
import asyncio
import json
import re

import asyncpg
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from app import config

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS laws (
    doc_id       BIGINT PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind         TEXT NOT NULL DEFAULT 'law'
);

CREATE TABLE IF NOT EXISTS chunks (
    id        BIGSERIAL PRIMARY KEY,
    doc_id    BIGINT NOT NULL REFERENCES laws ON DELETE CASCADE,
    article   TEXT NOT NULL,
    heading   TEXT NOT NULL,
    anchor    BIGINT,
    body      TEXT NOT NULL,
    embedding vector(768),  -- NULL until backfilled (free-tier embedding quota is ~1000/day)
    -- apostrophes removed so o'g'irlik is one word (ogirlik), matching or_query()
    tsv       tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', replace(article, '''', '')), 'A') ||  -- "169-modda. O'g'rilik" says what it is about
        setweight(to_tsvector('simple', replace(heading, '''', '')), 'B') ||  -- law name + chapter: "Notariat to'g'risida"
        setweight(to_tsvector('simple', replace(body, '''', '')), 'D')) STORED
);
-- laws.kind: 'law' | 'reg' (VMQ, PQ, ministry, Plenum); added by init() on older databases
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

CREATE TABLE IF NOT EXISTS fsm (
    key   TEXT PRIMARY KEY,
    state TEXT,
    data  JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS feedback (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    good       BOOLEAN NOT NULL,
    question   TEXT,
    answer     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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


_pools: dict[str, asyncpg.Pool] = {}


async def pool(url: str | None = None) -> asyncpg.Pool:
    url = url or config.DATABASE_URL
    if url not in _pools:
        # statement_cache_size=0 keeps it working behind PgBouncer (Supabase/Neon poolers).
        # Neon closes idle connections (and suspends compute after 5 min), so never reuse a connection
        # that sat idle while an AI call was running.
        _pools[url] = await asyncpg.create_pool(
            url, min_size=0, max_size=5, statement_cache_size=0,
            max_inactive_connection_lifetime=30, command_timeout=30,
        )
    return _pools[url]


def law_dbs() -> list[str]:
    """Free Neon projects hold 0.5 GB each, so regulations can live in a second database (DATABASE_URL_REGS).
    Users, payments and chat history always stay in the main one."""
    return list(dict.fromkeys(u for u in (config.DATABASE_URL, config.DATABASE_URL_REGS) if u))


def db_for(kind: str) -> str:
    return config.DATABASE_URL_REGS if kind == "reg" and config.DATABASE_URL_REGS else config.DATABASE_URL


_DROPPED = (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, ConnectionError, OSError)


async def _run(method: str, *args, url: str | None = None):
    """Single-statement call with one retry when the server dropped the connection before answering."""
    for attempt in range(2):
        try:
            return await getattr(await pool(url), method)(*args)
        except _DROPPED:
            if attempt:
                raise


async def init() -> None:
    for url in law_dbs():
        p = await pool(url)
        async with p.acquire() as con:
            # never queue behind the live bot's queries for long: a waiting ALTER blocks every reader after it
            await con.execute("SET lock_timeout = '10s'")
            await con.execute(SCHEMA, timeout=300)
            missing_kind = not await con.fetchval(
                "SELECT 1 FROM information_schema.columns WHERE table_name='laws' AND column_name='kind'")
            if missing_kind:
                await con.execute("ALTER TABLE laws ADD COLUMN kind TEXT NOT NULL DEFAULT 'law'")
            await con.execute("RESET lock_timeout")


async def _each(method: str, sql: str, *args) -> list:
    """Same read on every law database, results concatenated."""
    out: list = []
    for url in law_dbs():
        out += await _run(method, sql, *args, url=url)
    return out


def vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


# ---------- laws ----------

async def recently_fetched(hours: int) -> list[int]:
    return [r["doc_id"] for r in await _each(
        "fetch", "SELECT doc_id FROM laws WHERE fetched_at > now() - make_interval(hours => $1)", hours)]


async def law_ids() -> list[int]:
    return sorted(r["doc_id"] for r in await _each("fetch", "SELECT doc_id FROM laws"))


async def law_hash(doc_id: int) -> str | None:
    for url in law_dbs():
        if h := await _run("fetchval", "SELECT content_hash FROM laws WHERE doc_id=$1", doc_id, url=url):
            return h
    return None


async def law_kinds() -> dict[int, str]:
    return {r["doc_id"]: r["kind"] for r in await _each("fetch", "SELECT doc_id, kind FROM laws")}


async def db_size_mb(kind: str = "law") -> float:
    return float(await _run("fetchval", "SELECT pg_database_size(current_database()) / 1048576.0", url=db_for(kind)))


async def replace_law(doc_id: int, title: str, url: str, content_hash: str, rows: list[tuple],
                      kind: str = "law") -> None:
    """rows: (article, heading, anchor, body). Atomic: old version stays until the new one is complete.
    Embeddings are filled in later by set_embeddings()."""
    target = db_for(kind)
    for url in law_dbs():  # a document may move between databases (e.g. regs loaded before the 2nd DB existed)
        if url != target:
            await _run("execute", "DELETE FROM laws WHERE doc_id=$1", doc_id, url=url)
    p = await pool(target)
    async with p.acquire() as con, con.transaction():
        await con.execute("DELETE FROM laws WHERE doc_id=$1", doc_id)
        await con.execute(
            "INSERT INTO laws (doc_id, title, url, content_hash, kind) VALUES ($1,$2,$3,$4,$5)",
            doc_id, title, url, content_hash, kind,
        )
        await con.executemany(
            "INSERT INTO chunks (doc_id, article, heading, anchor, body) VALUES ($1,$2,$3,$4,$5)",
            [(doc_id, *row) for row in rows],
        )


async def chunks_without_embedding(limit: int) -> list[asyncpg.Record]:
    return await _run("fetch",
        """SELECT c.id, c.article, c.heading, c.body, l.title FROM chunks c JOIN laws l USING (doc_id)
           WHERE c.embedding IS NULL AND l.kind = 'law' ORDER BY c.id LIMIT $1""", limit,
    )


async def count_without_embedding() -> int:
    # only laws get embeddings: ~100k regulation chunks would take months of free quota and too much space
    return await _run("fetchval", """SELECT count(*) FROM chunks c JOIN laws l USING (doc_id)
                                     WHERE c.embedding IS NULL AND l.kind = 'law'""")


async def set_embeddings(pairs: list[tuple[int, list[float]]]) -> None:
    await _run("executemany",
        "UPDATE chunks SET embedding=$2::vector WHERE id=$1", [(i, vec(e)) for i, e in pairs]
    )


async def search(query_embedding: list[float] | None, query_text: str, limit: int = 8,
                 doc_ids: list[int] | None = None) -> list[asyncpg.Record]:
    """Hybrid search: vector similarity + keyword match (everywhere, and boosted inside the laws the AI
    picked as applicable), merged with reciprocal rank fusion.
    query_embedding=None -> no vector part (embedding quota exhausted / not backfilled yet)."""
    sql = """
    WITH q AS (SELECT to_tsquery('simple', $2) AS q
    ), v AS (
        SELECT id, row_number() OVER (ORDER BY embedding <=> $1::vector) AS r, 1.0 AS w
        FROM chunks WHERE $1::vector IS NOT NULL AND embedding IS NOT NULL ORDER BY embedding <=> $1::vector LIMIT 30
    ), k AS (
        SELECT id, row_number() OVER (ORDER BY ts_rank(tsv, q, 1) DESC) AS r, 1.0 AS w
        FROM chunks, q WHERE tsv @@ q ORDER BY ts_rank(tsv, q, 1) DESC LIMIT 30
    ), d AS (  -- best 3 articles of EACH chosen law, so one big code can't crowd out a specific law
        SELECT id, r, 2.0 AS w FROM (
            SELECT id, row_number() OVER (PARTITION BY doc_id ORDER BY ts_rank(tsv, q, 1) DESC) AS r
            FROM chunks, q WHERE doc_id = ANY($4::bigint[]) AND tsv @@ q) x
        WHERE r <= 3
    ), fused AS (
        SELECT id, sum(w / (60 + r)) AS score FROM (SELECT * FROM v UNION ALL SELECT * FROM k UNION ALL SELECT * FROM d) x
        GROUP BY id ORDER BY score DESC LIMIT $3
    )
    SELECT c.article, c.heading, c.anchor, c.body, l.title, l.url, l.kind, f.score
    FROM fused f JOIN chunks c ON c.id = f.id JOIN laws l ON l.doc_id = c.doc_id
    ORDER BY f.score DESC
    """
    embedding = vec(query_embedding) if query_embedding else None
    args = (embedding, or_query(query_text), limit, doc_ids or [])
    results = await asyncio.gather(*(_run("fetch", sql, *args, url=u) for u in law_dbs()))
    # rank-fusion scores are comparable across databases, so merging keeps the best overall
    return sorted((r for rows in results for r in rows), key=lambda r: r["score"], reverse=True)[:limit]


async def article_rows(number: str, doc_ids: list[int]) -> list:
    """The exact article a user cited ("Mehnat kodeksi 454-modda"), whatever database it lives in."""
    return (await _each("fetch", """
        SELECT c.article, c.heading, c.anchor, c.body, l.title, l.url, l.kind, 1.0 AS score
        FROM chunks c JOIN laws l USING (doc_id)
        WHERE c.doc_id = ANY($2::bigint[]) AND c.article LIKE $1 || '-modda%'
        ORDER BY c.id LIMIT 2""", number, doc_ids))[:2]


async def law_catalog() -> list[asyncpg.Record]:
    return sorted(await _each("fetch", "SELECT doc_id, title, kind FROM laws"), key=lambda r: r["doc_id"])


_STOP = {"nima", "qanday", "qancha", "qilish", "qilay", "kerak", "bilan", "uchun", "ladi", "bormi", "mumkin",
         "menga", "mening", "meni", "men", "edi", "yoki", "lekin", "agar", "shu", "ham", "emas", "nimaga", "qayerga",
         # words present in almost every article drown the specific ones
         "ozbekiston", "respublikasi", "respublikasining", "respublika", "kodeks", "kodeksi", "kodeksiga", "modda",
         "moddasi", "moddalar", "qonun", "qonuni", "qonunchilik", "qonunchiligi", "belgilangan", "tartibi", "tartibda",
         "tahlili", "choralari", "huquqiy", "boyicha", "togrisida", "togrisidagi", "jazo", "jazosi", "jinoyat",
         "jinoyati", "beriladi", "javobgarlik", "huquqbuzarlik", "huquqbuzarliklar", "mamuriy"}


def _stem(w: str) -> str:
    """Uzbek stem for prefix search: suffixes change the root's last consonant (tezlik -> tezligi,
    oylik -> oyligi, qishloq -> qishlog'i), so drop a final k/q and keep at most 5 letters."""
    stem = w[:max(4, min(len(w) - 2, 5))]
    return stem[:-1] if len(stem) > 4 and stem[-1] in "kq" else stem


def or_query(text: str) -> str:
    """Any-word prefix match ('mehn:* | shartn:* | ...'). Uzbek adds suffixes (bola-lar-iga), so each word is
    cut to a short stem; AND of 15 words would almost never match."""
    words = []
    for w in re.findall(r"\w+", text.lower().replace("'", "")):
        if w in _STOP or (len(w) < 3 and not w.isdigit()):
            continue
        words.append(w if w.isdigit() or len(w) <= 4 else _stem(w) + ":*")
    return " | ".join(dict.fromkeys(words))


# ---------- users / history / limits ----------

async def ensure_user(user_id: int) -> asyncpg.Record:
    return await _run("fetchrow",
        "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO UPDATE SET id=EXCLUDED.id RETURNING *", user_id
    )


async def add_message(user_id: int, role: str, content: str) -> None:
    await _run("execute",
        "INSERT INTO messages (user_id, role, content) VALUES ($1,$2,$3)", user_id, role, content
    )


async def history(user_id: int, limit: int = 10) -> list[asyncpg.Record]:
    rows = await _run("fetch",
        "SELECT role, content FROM messages WHERE user_id=$1 ORDER BY id DESC LIMIT $2", user_id, limit
    )
    return list(reversed(rows))


async def clear_history(user_id: int) -> None:
    await _run("execute", "DELETE FROM messages WHERE user_id=$1", user_id)


async def take_daily_quota(user_id: int, limit: int) -> bool:
    """Counts one request; False when today's free limit is used up (Tashkent day)."""
    count = await _run("fetchval",
        """INSERT INTO usage (user_id, day, count) VALUES ($1, (now() AT TIME ZONE 'Asia/Tashkent')::date, 1)
           ON CONFLICT (user_id, day) DO UPDATE SET count = usage.count + 1 RETURNING count""",
        user_id,
    )
    return count <= limit


async def set_pending_doc(user_id: int, description: str | None) -> None:
    await _run("execute", "UPDATE users SET pending_doc=$2 WHERE id=$1", user_id, description)


async def spend_credit(user_id: int) -> bool:
    row = await _run("fetchval",
        "UPDATE users SET credits=credits-1 WHERE id=$1 AND credits>0 RETURNING credits", user_id
    )
    return row is not None


async def add_credits(user_id: int, n: int) -> int:
    await ensure_user(user_id)
    return await _run("fetchval",
        "UPDATE users SET credits=GREATEST(credits+$2, 0) WHERE id=$1 RETURNING credits", user_id, n
    )


# ---------- payments ----------

async def receipt_seen(txn_id: str | None, image_hash: str) -> bool:
    return bool(await _run("fetchval",
        "SELECT 1 FROM payments WHERE image_hash=$1 OR ($2::text IS NOT NULL AND txn_id=$2)", image_hash, txn_id
    ))


async def record_payment(user_id: int, amount: int | None, credits: int, txn_id: str | None,
                         image_hash: str, status: str, details: str) -> int | None:
    """Returns payment id, or None if this receipt was already used (unique constraint race).
    Only approved receipts reserve txn_id/image_hash, so a wrongly rejected receipt can be resent."""
    approved = status == "approved"
    try:
        return await _run("fetchval",
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


async def stats() -> dict:
    row = dict(await _run("fetchrow",
        """SELECT (SELECT count(*) FROM users) AS users,
                  (SELECT count(*) FROM laws) AS laws,
                  (SELECT count(*) FROM chunks) AS chunks,
                  (SELECT count(*) FROM chunks WHERE embedding IS NOT NULL) AS embedded,
                  (SELECT count(*) FROM payments WHERE status='approved') AS paid,
                  (SELECT count(*) FROM feedback WHERE good) AS good,
                  (SELECT count(*) FROM feedback WHERE NOT good) AS bad,
                  (SELECT coalesce(sum(amount),0) FROM payments WHERE status='approved') AS revenue"""
    ))
    for url in law_dbs()[1:]:  # regulations database, if configured
        extra = await _run("fetchrow", "SELECT (SELECT count(*) FROM laws) AS laws, (SELECT count(*) FROM chunks) AS chunks",
                           url=url)
        row["laws"] += extra["laws"]
        row["chunks"] += extra["chunks"]
    return row


async def recent_users(limit: int) -> list[asyncpg.Record]:
    return await _run("fetch", """
        SELECT u.id, u.created_at,
               (SELECT count(*) FROM messages m WHERE m.user_id = u.id AND m.role = 'user') AS questions
        FROM users u ORDER BY u.created_at DESC LIMIT $1""", limit)


async def user_counts() -> asyncpg.Record:
    return await _run("fetchrow", """
        SELECT (SELECT count(*) FROM users) AS total,
               (SELECT count(*) FROM users WHERE created_at > now() - interval '24 hours') AS new_24h,
               (SELECT count(DISTINCT user_id) FROM messages
                 WHERE role = 'user' AND created_at > now() - interval '24 hours') AS active_24h""")


async def save_feedback(user_id: int, good: bool) -> None:
    """Stores the rating with the user's latest question/answer pair, so bad answers can be reviewed."""
    await _run("execute", """
        INSERT INTO feedback (user_id, good, question, answer)
        SELECT $1, $2,
               (SELECT content FROM messages WHERE user_id=$1 AND role='user' ORDER BY id DESC LIMIT 1),
               (SELECT content FROM messages WHERE user_id=$1 AND role='model' ORDER BY id DESC LIMIT 1)""",
        user_id, good)


async def recent_bad_feedback(limit: int) -> list[asyncpg.Record]:
    return await _run("fetch", "SELECT question, answer FROM feedback WHERE NOT good ORDER BY id DESC LIMIT $1", limit)


class PgStorage(BaseStorage):
    """Bot conversation state ("waiting for receipt") in Postgres, so a Render restart doesn't lose it."""

    @staticmethod
    def _key(k: StorageKey) -> str:
        return f"{k.bot_id}:{k.chat_id}:{k.user_id}"

    async def set_state(self, key: StorageKey, state=None) -> None:
        state = state.state if isinstance(state, State) else state
        await _run("execute", """INSERT INTO fsm (key, state) VALUES ($1, $2)
                                 ON CONFLICT (key) DO UPDATE SET state = EXCLUDED.state""", self._key(key), state)

    async def get_state(self, key: StorageKey) -> str | None:
        return await _run("fetchval", "SELECT state FROM fsm WHERE key=$1", self._key(key))

    async def set_data(self, key: StorageKey, data) -> None:
        await _run("execute", """INSERT INTO fsm (key, data) VALUES ($1, $2::jsonb)
                                 ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data""",
                   self._key(key), json.dumps(dict(data)))

    async def get_data(self, key: StorageKey) -> dict:
        raw = await _run("fetchval", "SELECT data FROM fsm WHERE key=$1", self._key(key))
        return json.loads(raw) if raw else {}

    async def close(self) -> None:
        pass
