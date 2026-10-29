"""Load / refresh laws from lex.uz into the database.

    python -m app.ingest              # every id in data/sources.txt (unchanged docs are skipped)
    python -m app.ingest 6445145      # specific lex.uz document ids
    python -m app.ingest --force      # reload even if unchanged
    python -m app.ingest --all        # plus every law in force listed on lex.uz (~8 min first time)
    python -m app.ingest --regs       # plus normative VMQ / Presidential / ministry acts (stops at MAX_DB_MB)

Laws already in the database are always refreshed too, so nothing loaded once goes stale.

Text goes in first (keyword search works at once, no API quota needed); embeddings are filled in
afterwards as far as the Gemini quota allows (free tier: ~1000/day) and continue on the next run.
"""
import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

import aiohttp

from app import config, db, lexuz, llm

log = logging.getLogger("ingest")
MAX_DB_MB = float(os.environ.get("MAX_DB_MB", "450"))
SOURCES = Path(__file__).resolve().parent.parent / "data" / "sources.txt"


def read_sources() -> list[int]:
    ids = []
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(int(line))
    return ids


def law_name(title: str) -> str:
    """'O'RQ-900-son 19.01.2024. Yo'l harakati to'g'risida' -> "Yo'l harakati to'g'risida" (searchable law name)."""
    return re.sub(r"^.*?\d{2}\.\d{2}\.\d{4}\.\s*", "", title)


async def ingest_one(session: aiohttp.ClientSession, doc_id: int, force: bool, kind: str = "law") -> str:
    doc = lexuz.parse_document(doc_id, await lexuz.fetch_html(session, doc_id))
    if not force and await db.law_hash(doc_id) == doc.content_hash:
        return f"unchanged: {doc.title}"
    law = law_name(doc.title)
    rows = [(a.article, f"{law} / {a.heading}" if a.heading else law, a.anchor, part)
            for a in doc.articles for part in lexuz.chunks(a)]
    await db.replace_law(doc_id, doc.title, doc.url, doc.content_hash, rows, kind)
    return f"saved {len(rows)} chunks / {len(doc.articles)} articles: {doc.title}"


async def main(argv: list[str]) -> int:
    config.require("DATABASE_URL", "GEMINI_API_KEY")
    force = "--force" in argv
    await db.init()
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (ai-advokat-uz ingest)"}) as session:
        explicit = [int(a) for a in argv if a.isdigit()]
        kinds = await db.law_kinds()
        # a restarted run doesn't fetch again what it loaded a few hours ago
        fresh = set() if force or explicit else set(await db.recently_fetched(hours=20))
        queue: asyncio.Queue = asyncio.Queue()
        seen: set[int] = set()

        def enqueue(doc_id: int, kind: str) -> None:
            if doc_id not in seen and doc_id not in fresh:
                seen.add(doc_id)
                kinds.setdefault(doc_id, kind)
                queue.put_nowait(doc_id)

        for doc_id in explicit or read_sources() + await db.law_ids():
            enqueue(doc_id, kinds.get(doc_id, "law"))

        size = {"mb": await db.db_size_mb("reg"), "at": time.monotonic()}
        result = {"ok": 0, "failed": 0}

        async def worker() -> None:
            # Pipeline: documents download while the (slow, sequential) lex.uz listings are still being read.
            while (doc_id := await queue.get()) is not None:
                kind = kinds.get(doc_id, "law")
                if kind == "reg":
                    if time.monotonic() - size["at"] > 30:
                        size.update(mb=await db.db_size_mb("reg"), at=time.monotonic())
                    if size["mb"] > MAX_DB_MB:  # free Neon tier is 512 MB: never risk the live bot
                        continue
                try:
                    log.info("%s %s", doc_id, await ingest_one(session, doc_id, force, kind))
                    result["ok"] += 1
                except Exception:
                    log.exception("%s failed", doc_id)
                    result["failed"] += 1
                await asyncio.sleep(0.5)

        workers = [asyncio.create_task(worker()) for _ in range(8)]  # 8 parallel downloads, still gentle
        listings: dict[str, object] = {}
        if not explicit and "--all" in argv:
            listings["Qonunlar"] = lexuz.list_laws(session, on_found=lambda i: enqueue(i, "law"))
        if not explicit and "--regs" in argv:
            for name, url in lexuz.REG_LISTS.items():
                listings[name] = lexuz.list_docs(session, url, lexuz.is_normative, on_found=lambda i: enqueue(i, "reg"))
        for name, listed in zip(listings, await asyncio.gather(*listings.values(), return_exceptions=True), strict=True):
            if isinstance(listed, BaseException):  # a broken listing must not stop the documents already queued
                log.error("lex.uz %s listing failed: %r", name, listed)
            else:
                log.info("lex.uz %s: %d documents listed", name, len(listed))
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)
    total = result["ok"] + result["failed"]
    log.info("laws: %d ok, %d failed; database %.0f MB", result["ok"], result["failed"], await db.db_size_mb())
    await backfill_embeddings()
    return 1 if result["failed"] > total // 10 else 0  # a few odd pages (404, empty) must not fail the daily job


async def backfill_embeddings(batch: int = 50) -> None:
    while rows := await db.chunks_without_embedding(batch):
        texts = [f"{r['title']}\n{r['heading']}\n{r['article']}\n{r['body']}" for r in rows]
        try:
            vectors = await llm.embed(texts)
        except Exception as exc:
            if "PerDay" in str(exc):
                log.warning("daily embedding quota used up; %d chunks still without embedding, next run continues",
                            await db.count_without_embedding())
                return
            raise
        await db.set_embeddings([(r["id"], v) for r, v in zip(rows, vectors, strict=True)])
    log.info("all chunks have embeddings")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.exit(asyncio.run(main(sys.argv[1:])))
