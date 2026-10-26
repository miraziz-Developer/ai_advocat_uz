"""Thin wrapper around the Gemini API (google-genai SDK)."""
import asyncio
import json
import logging

from google import genai
from google.genai import errors, types

from app import config

log = logging.getLogger(__name__)
_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            # No per-model retry: generate() moves to the next model on 429/503, which is faster for the user.
            http_options=types.HttpOptions(timeout=90_000, retry_options=types.HttpRetryOptions(attempts=1)),
        )
    return _client


def _batches(texts: list[str], max_items: int = 100, max_chars: int = 40_000) -> list[list[str]]:
    """API allows 100 texts per call; the free tier also caps tokens per minute (~30k), so keep each
    call well below that (Uzbek Latin is roughly 3 chars per token)."""
    batches: list[list[str]] = [[]]
    size = 0
    for t in texts:
        if batches[-1] and (len(batches[-1]) >= max_items or size + len(t) > max_chars):
            batches.append([])
            size = 0
        batches[-1].append(t)
        size += len(t)
    return [b for b in batches if b]


async def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    out: list[list[float]] = []
    for batch in _batches(texts):
        for attempt in range(6):
            try:
                resp = await client().aio.models.embed_content(
                    model=config.EMBED_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=config.EMBED_DIM),
                )
                break
            except errors.APIError as exc:
                if exc.code not in (429, 500, 503) or attempt == 5:
                    raise
                log.warning("embedding rate-limited (%s), waiting", exc.code)
                await asyncio.sleep(20 * (attempt + 1))  # per-minute quotas reset within a minute
        out.extend(e.values for e in resp.embeddings)
    return out


_FALLBACK_CODES = {404, 429, 500, 503, 504}


async def _generate_with_fallback(models: list[str], contents, cfg: types.GenerateContentConfig):
    """Free-tier models are often overloaded (503); move on to the next model instead of failing."""
    last: Exception | None = None
    for model in models:
        try:
            return await client().aio.models.generate_content(model=model, contents=contents, config=cfg)
        except errors.APIError as exc:
            if exc.code not in _FALLBACK_CODES:
                raise
            log.warning("model %s failed with %s, trying next", model, exc.code)
            last = exc
        except Exception as exc:  # network timeouts surface as httpx/aiohttp errors depending on transport
            log.warning("model %s failed (%s), trying next", model, type(exc).__name__)
            last = exc
    raise last or RuntimeError("no models configured")


async def generate(contents, system: str, models: list[str] | None = None, temperature: float = 0.2) -> str:
    cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    resp = await _generate_with_fallback(models or config.CHAT_MODELS, contents, cfg)
    return (resp.text or "").strip()


async def generate_json(contents, system: str, schema: dict, models: list[str] | None = None) -> dict:
    cfg = types.GenerateContentConfig(
        system_instruction=system, temperature=0, response_mime_type="application/json", response_schema=schema,
    )
    resp = await _generate_with_fallback(models or config.CHAT_MODELS, contents, cfg)
    return json.loads(resp.text or "{}")


def file_part(data: bytes, mime_type: str) -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def history_contents(rows, new_parts: list) -> list[types.Content]:
    """Chat history rows (role, content) + the new user turn."""
    contents = [types.Content(role=r["role"], parts=[types.Part(text=r["content"])]) for r in rows]
    contents.append(types.Content(role="user", parts=new_parts))
    return contents
