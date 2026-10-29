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


LAWS_LIST = "https://lex.uz/uz/search/nat?lang=4&sort_id=3975&form_id=3968"  # "Qonunlar" category
_AMENDING = re.compile(r"o.zgartish|o.zgartirish|qo.shimcha|kuchini yo.qotgan|kiritish haqida|ratifikatsiya|"
                       r"to.xtatib turish|bekor qilish haqida|qo.shilish|qo.shilishi haqida|faxriy unvon|"
                       r"tasdiqlash to.g.risida|kunini belgilash", re.I)


async def _request(session: aiohttp.ClientSession, method: str, url: str, data: dict | None = None) -> str:
    """One listing page; a listing is ~600 sequential requests, so one network hiccup must not lose it all."""
    for attempt in range(4):
        try:
            async with session.request(method, url, data=data, timeout=aiohttp.ClientTimeout(total=90)) as r:
                r.raise_for_status()
                return await r.text()
        except (TimeoutError, aiohttp.ClientError):
            if attempt == 3:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _hidden_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    return {i["name"]: i.get("value", "") for i in soup.find_all("input", type="hidden") if i.get("name")}


# Government (VMQ), Presidential and ministry acts. Only normative ones (rules, regulations, procedures) —
# the rest (appointments, events, programmes, amendments) don't tell a citizen what the rules are.
REG_LISTS = {
    "VMQ": "https://lex.uz/uz/search/nat?lang=4&sort_id=3988",
    "Prezident": "https://lex.uz/uz/search/nat?lang=4&sort_id=3985",
    "Idoraviy": "https://lex.uz/uz/search/nat?lang=4&sort_id=3991",
    "Sud amaliyoti": "https://lex.uz/uz/search/court?lang=4",  # Supreme Court Plenum: how courts apply the law
}
_NORMATIVE = re.compile(r"nizom|qoida|tartib|reglament|yo.riqnoma|me.yor|talablar|tarif|to.lov|jarima|"
                        r"ro.yxatga olish|imtiyoz|nafaqa|pensiya|kommunal|yo.l harakati", re.I)
_NOT_NORMATIVE = re.compile(r"o.zgartish|o.zgartirish|qo.shimcha|kuchini yo.qotgan|bekor qilish|ta.sis etish|"
                            r"mukofot|nishon|oyligi|tashkil etish|ratifikatsiya|xalqaro|tayinlash haqida|"
                            r"ozod qilish haqida|vaqtinchalik|tajriba tariqasida", re.I)


_PLENUM = re.compile(r"plenum|sud amaliyoti|sudlar tomonidan", re.I)


def is_normative(title: str) -> bool:
    """Rules a citizen can rely on; Plenum resolutions count too (individual court cases don't)."""
    if _PLENUM.search(title):
        return not _AMENDING.search(title)
    return bool(_NORMATIVE.search(title)) and not _NOT_NORMATIVE.search(title)


async def list_laws(session: aiohttp.ClientSession, max_pages: int = 200, on_found=None) -> list[tuple[int, str]]:
    """Every law on lex.uz except amending/ratifying acts (their changes are already merged into the
    current text of the base law)."""
    return await list_docs(session, LAWS_LIST, lambda t: not _AMENDING.search(t), max_pages, on_found)


async def list_docs(session: aiohttp.ClientSession, url: str, keep, max_pages: int = 1000,
                    on_found=None) -> list[tuple[int, str]]:
    """All documents of one lex.uz listing whose title passes `keep`. The list is an ASP.NET page, so
    "next" is a form postback (pages can't be fetched in parallel)."""
    found: dict[int, str] = {}
    html = await _request(session, "GET", url)
    prev_page: list = []
    for _ in range(max_pages):
        page = re.findall(r'href="/uz/docs/(-?\d+)" target="_blank">([^<]{3,400})', html)
        if not page or page == prev_page:  # past the last page
            break
        prev_page = page
        for doc_id, title in page:
            title = normalize(re.sub(r"\s+", " ", title)).strip()
            doc_id = abs(int(doc_id))
            if keep(title) and doc_id not in found:
                found[doc_id] = title
                if on_found:  # lets the caller start downloading while the listing continues
                    on_found(doc_id)
        if 'ucFoundActsControl$LinkButton1' not in html:
            break
        form = _hidden_fields(html) | {"__EVENTTARGET": "ucFoundActsControl$LinkButton1", "__EVENTARGUMENT": ""}
        await asyncio.sleep(0.5)  # be polite
        next_html = await _request(session, "POST", url, form)
        if next_html == html:
            break
        html = next_html
    return list(found.items())


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
