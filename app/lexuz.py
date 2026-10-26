"""Fetch official legal acts from lex.uz and split them into articles."""
import asyncio
import hashlib
import re
from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup

from app.translit import normalize

BASE = "https://lex.uz/uz/docs/"
MAX_CHUNK = 3000  # chars; keeps each piece well under the embedding model's input limit
_HEADER_CLASSES = {"TEXT_HEADER_DEFAULT", "TEXT_BOLD_CENTER", "TEXT_HEADER_CENTER"}


@dataclass
class Article:
    article: str   # "15-modda. Sarlavha" or "Muqaddima"
    heading: str   # section / chapter path
    anchor: int | None  # lex.uz element id -> url#anchor jumps to the article
    body: str


@dataclass
class Document:
    doc_id: int
    title: str
    url: str
    articles: list[Article]

    @property
    def content_hash(self) -> str:
        h = hashlib.sha256()
        for a in self.articles:
            h.update(f"{a.article}\n{a.body}\n".encode())
        return h.hexdigest()


async def fetch_html(session: aiohttp.ClientSession, doc_id: int) -> str:
    for attempt in range(3):
        try:
            async with session.get(f"{BASE}{doc_id}", timeout=aiohttp.ClientTimeout(total=180)) as r:
                r.raise_for_status()
                return await r.text()
        except (TimeoutError, aiohttp.ClientError):
            if attempt == 2:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _text(el) -> str:
    for junk in el.select(".lx_elem2"):
        junk.decompose()
    for sup in el.find_all("sup"):  # 4<sup>1</sup>-modda -> 4¹-modda
        sup.replace_with(sup.get_text().translate(_SUPERSCRIPT))
    for br in el.find_all("br"):
        br.replace_with(" ")
    # No separator: inline tags (<a>, <em>) sit mid-word in lex.uz markup.
    return re.sub(r"\s+", " ", el.get_text()).strip()


def parse_document(doc_id: int, html: str) -> Document:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.title.get_text() if soup.title else ""
    if "404" in title_tag:
        raise ValueError(f"lex.uz document {doc_id} not found")
    # "&nbsp; 30.04.2023.&nbsp;Ўзбекистон Республикаси Конституцияси" -> keep date + name
    title = normalize(re.sub(r"\s+", " ", title_tag.replace("\xa0", " ")).strip())

    articles: list[Article] = []
    section = chapter = ""
    current: Article | None = None
    for el in soup.select("div.lx_elem"):
        kind = el["class"][0]
        anchor_div = el.find("div", id=re.compile(r"^\d+$"))
        anchor = int(anchor_div["id"]) if anchor_div else None
        text = normalize(_text(el))
        if not text:
            continue
        heading = " / ".join(h for h in (section, chapter) if h)
        if kind == "CLAUSE_DEFAULT":
            current = Article(text, heading, anchor, "")
            articles.append(current)
        elif kind in _HEADER_CLASSES:
            if "bo'lim" in text.lower():
                section, chapter = text, ""
            else:
                chapter = text
            current = None
        else:
            if current is None:
                current = Article(chapter or section or "Kirish", heading, anchor, "")
                articles.append(current)
            current.body = f"{current.body}\n{text}" if current.body else text

    articles = [a for a in articles if a.body]
    if not articles:
        raise ValueError(f"lex.uz document {doc_id}: no articles parsed (page layout changed?)")
    return Document(doc_id, title, f"{BASE}{doc_id}", articles)


def chunks(article: Article) -> list[str]:
    """Split long articles on line boundaries; each chunk keeps the article header for context."""
    if len(article.body) <= MAX_CHUNK:
        return [article.body]
    parts, buf = [], ""
    for line in article.body.split("\n"):
        while len(line) > MAX_CHUNK:  # a single huge paragraph (e.g. a table)
            parts.append(line[:MAX_CHUNK])
            line = line[MAX_CHUNK:]
        if buf and len(buf) + len(line) + 1 > MAX_CHUNK:
            parts.append(buf)
            buf = ""
        buf = f"{buf}\n{line}" if buf else line
    if buf:
        parts.append(buf)
    return parts
