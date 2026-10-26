"""Load / refresh laws from lex.uz into the database.

    python -m app.ingest              # every id in data/sources.txt (unchanged docs are skipped)
    python -m app.ingest 6445145      # specific lex.uz document ids
    python -m app.ingest --force      # re-embed even if unchanged
"""
import asyncio
import logging
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


async def ingest_one(session: aiohttp.ClientSession, doc_id: int, force: bool) -> str:
    doc = lexuz.parse_document(doc_id, await lexuz.fetch_html(session, doc_id))
    if not force and await db.law_hash(doc_id) == doc.content_hash:
        return f"unchanged: {doc.title}"
    pieces = [(a, part) for a in doc.articles for part in lexuz.chunks(a)]
    texts = [f"{doc.title}\n{a.heading}\n{a.article}\n{part}" for a, part in pieces]
    vectors = await llm.embed(texts)
    rows = [(a.article, a.heading, a.anchor, part, v) for (a, part), v in zip(pieces, vectors, strict=True)]
    await db.replace_law(doc_id, doc.title, doc.url, doc.content_hash, rows)
    return f"saved {len(rows)} chunks / {len(doc.articles)} articles: {doc.title}"


async def main(argv: list[str]) -> int:
    config.require("DATABASE_URL", "GEMINI_API_KEY")
    force = "--force" in argv
    ids = [int(a) for a in argv if a.isdigit()] or read_sources()
    await db.init()
    failed = 0
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (ai-advokat-uz ingest)"}) as session:
        for doc_id in ids:
            try:
                log.info("%s %s", doc_id, await ingest_one(session, doc_id, force))
            except Exception as exc:
                failed += 1
                if "PerDay" in str(exc):
                    # Free tier: ~1000 embeddings/day. The daily workflow continues tomorrow.
                    log.warning("daily embedding quota used up; stopping, remaining docs load on the next run")
                    break
                log.exception("%s failed", doc_id)
            await asyncio.sleep(3)  # be polite to lex.uz
    log.info("done: %d ok, %d failed", len(ids) - failed, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.exit(asyncio.run(main(sys.argv[1:])))
