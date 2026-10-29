"""Load / refresh laws from lex.uz into the database.

    python -m app.ingest              # every id in data/sources.txt (unchanged docs are skipped)
    python -m app.ingest 6445145      # specific lex.uz document ids
    python -m app.ingest --force      # reload even if unchanged
    python -m app.ingest --all        # plus every law in force listed on lex.uz (~30 min first time)

Laws already in the database are always refreshed too, so nothing loaded once goes stale.

Text goes in first (keyword search works at once, no API quota needed); embeddings are filled in
afterwards as far as the Gemini quota allows (free tier: ~1000/day) and continue on the next run.
"""
import asyncio
import logging
import re
import sys
from pathlib import Path

import aiohttp

from app import config, db, lexuz, llm

log = logging.getLogger("ingest")
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


async def ingest_one(session: aiohttp.ClientSession, doc_id: int, force: bool) -> str:
    doc = lexuz.parse_document(doc_id, await lexuz.fetch_html(session, doc_id))
    if not force and await db.law_hash(doc_id) == doc.content_hash:
        return f"unchanged: {doc.title}"
    law = law_name(doc.title)
    rows = [(a.article, f"{law} / {a.heading}" if a.heading else law, a.anchor, part)
            for a in doc.articles for part in lexuz.chunks(a)]
    await db.replace_law(doc_id, doc.title, doc.url, doc.content_hash, rows)
    return f"saved {len(rows)} chunks / {len(doc.articles)} articles: {doc.title}"


async def main(argv: list[str]) -> int:
    config.require("DATABASE_URL", "GEMINI_API_KEY")
    force = "--force" in argv
    await db.init()
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (ai-advokat-uz ingest)"}) as session:
        ids = [int(a) for a in argv if a.isdigit()]
        if not ids:
            ids = read_sources() + await db.law_ids()
            if "--all" in argv:
                listed = await lexuz.list_laws(session)
                log.info("lex.uz lists %d laws (amending acts excluded)", len(listed))
                ids += [doc_id for doc_id, _ in listed]
            ids = list(dict.fromkeys(ids))
            if not force:  # a restarted run doesn't fetch again what it loaded a few hours ago
                fresh = set(await db.recently_fetched(hours=20))
                ids = [i for i in ids if i not in fresh]
        log.info("%d documents to check", len(ids))
        sem = asyncio.Semaphore(4)  # 4 parallel downloads: ~4x faster, still gentle on lex.uz

        async def one(doc_id: int) -> bool:
            async with sem:
                try:
                    log.info("%s %s", doc_id, await ingest_one(session, doc_id, force))
                    return True
                except Exception:
                    log.exception("%s failed", doc_id)
                    return False
                finally:
                    await asyncio.sleep(1)

        failed = sum(not ok for ok in await asyncio.gather(*(one(i) for i in ids)))
    log.info("laws: %d ok, %d failed", len(ids) - failed, failed)
    await backfill_embeddings()
    return 1 if failed > len(ids) // 10 else 0  # a few odd pages (404, empty) must not fail the daily job


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
