"""Retrieval-augmented answers: every legal claim must come from lex.uz text stored in the DB."""
import asyncio
import datetime as dt
import logging
import re
from dataclasses import dataclass

from app import config, db, llm
from app.translit import normalize

SYSTEM = """Sen — «AI Huquqiy Yordamchi», O'zbekiston Respublikasi qonunchiligi bo'yicha yordamchisan.
Bugungi sana: {today}.

QAT'IY QOIDALAR:
1. Huquqiy normalarni FAQAT so'rov bilan berilgan MANBALAR (lex.uz rasmiy matnlari) asosida keltir.
   Modda raqami, muddat, jarima, jazo yoki summa manbada bo'lmasa — uni HECH QACHON o'zingdan yozma.
2. Har bir huquqiy fikrdan keyin manba raqamini [1], [2] ko'rinishida qo'y.
3. Manbalar yetarli bo'lmasa, ochiq ayt: "Bazamdagi qonun matnlarida bu bo'yicha aniq norma topilmadi".
   Umumiy amaliy maslahat berishing mumkin, lekin uni qonun normasi sifatida ko'rsatma.
4. Javob tartibi: qisqa xulosa → qonun nima deydi (manbalar bilan) → qadamma-qadam nima qilish kerak
   (qaysi organga, qanday hujjat bilan, qanday muddatda) → nimadan ehtiyot bo'lish kerak.
5. Vaziyat noaniq bo'lsa, javob oxirida 1-3 ta aniqlashtiruvchi savol ber.
6. Foydalanuvchi qaysi tilda yozsa (o'zbek lotin/kirill, rus) — o'sha tilda, oddiy va tushunarli javob ber.
7. Markdown ishlatma (**, #, jadval yo'q). Ro'yxat uchun "•" yoki "1." ishlat. Javob 3500 belgidan oshmasin.
8. Jinoiy ish, sud jarayoni, katta summa yoki muddat o'tib ketish xavfi bo'lsa — litsenziyali advokatga
   murojaat qilishni ham tavsiya qil.
9. Foydalanuvchiga yozma hujjat (ariza, da'vo arizasi, shikoyat, talabnoma, tushuntirish xati, shartnoma,
   ishonchnoma, apellyatsiya va h.k.) kerak bo'lsa, javobning eng oxirida alohida qatorda aynan shunday yoz:
   [[HUJJAT: hujjat turi va kimga/nima haqida]]
   Hujjat kerak bo'lmasa, bu belgini qo'yma.
10. Qonunni chetlab o'tish, firibgarlik yoki hujjat soxtalashtirishga yordam berma."""

FILE_SYSTEM = SYSTEM + """

HOZIR foydalanuvchi hujjat yoki rasm yubordi. Tahlil tartibi:
• Bu qanday hujjat/vaziyat (1-2 gap).
• Asosiy mazmuni: tomonlar, summa, muddatlar, majburiyatlar.
• Xavfli yoki foydalanuvchiga noqulay bandlar va nima uchun (manbalar bilan).
• Qonunga zid yoki yetishmayotgan narsalar.
• Imzolashdan oldin nimani tekshirish / o'zgartirish kerak.
Foydalanuvchi alohida savol bergan bo'lsa, avval shunga javob ber."""

DRAFT_SYSTEM = """Sen O'zbekiston qonunchiligi bo'yicha tajribali yuristsan va rasmiy hujjat tuzasan. Bugun: {today}.
• Hujjatni o'zbek tilida (lotin) rasmiy uslubda yoz, O'zbekistonda qabul qilingan shaklda:
  kimga (organ/shaxs), kimdan, hujjat nomi, mazmun, talab qismi, ilovalar, sana va imzo joyi.
• Normalarga faqat berilgan MANBALARdan havola qil (masalan: "Mehnat kodeksining 161-moddasiga asosan").
  Manbada bo'lmagan modda raqamini yozma.
• Foydalanuvchi bermagan ma'lumotlar uchun to'rtburchak qavsli joy qoldir: [F.I.Sh.], [manzil], [sana].
• Markdown ishlatma. Birinchi qator — faqat hujjat nomi (masalan: DA'VO ARIZASI)."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "description": "Hujjat turi yoki rasmda nima borligi, qisqa"},
        "text": {"type": "string", "description": "Hujjatdagi matnning to'liq ko'chirmasi (20000 belgigacha). "
                                                  "Matn bo'lmasa — rasmda ko'rinayotgan narsaning batafsil tavsifi"},
        "search_query": {"type": "string", "description": "Tegishli qonun moddalarini topish uchun o'zbek "
                                                          "(lotin) tilidagi huquqiy qidiruv so'rovi"},
    },
    "required": ["doc_type", "text", "search_query"],
}

log = logging.getLogger(__name__)
_OFFER = re.compile(r"\[\[\s*HUJJAT\s*:\s*(.+?)\]\]", re.S)
_CITE = re.compile(r"\[(\d{1,2})\]")


@dataclass
class Reply:
    text: str
    offer: str | None = None  # document the AI suggests drafting (paid)


def _today() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5))).strftime("%d.%m.%Y")


def short_title(title: str) -> str:
    """'28.10.2022. O'zbekiston Respublikasining Mehnat kodeksi' -> "O'zbekiston Respublikasining Mehnat kodeksi"."""
    return re.sub(r"^.*?\d{2}\.\d{2}\.\d{4}\.\s*", "", title)


async def search_query(user_id: int, text: str) -> str:
    """Turns everyday wording ('telefonimni o'g'irlab ketishdi') and follow-ups ('unda nima qilay?') into a
    standalone query in legal terms ("o'g'rilik jinoyat kodeksi"); keyword search depends on it."""
    rows = await db.history(user_id, limit=4)
    convo = "\n".join(f"{r['role']}: {r['content'][:600]}" for r in rows)
    prompt = (f"Suhbat:\n{convo}\n\nOxirgi xabar: {text}\n\n"
              "Shu xabar bo'yicha O'zbekiston qonunlaridan tegishli moddalarni qidirish uchun o'zbek (lotin) "
              "tilida 3-6 ta aniq huquqiy atama yoz (masalan: o'g'rilik; aliment bola; ish haqi to'lanmasligi). "
              "Qonun matnida qanday yozilsa shunday yoz. \"O'zbekiston\", \"kodeks\", \"modda\" kabi umumiy "
              "so'zlarni yozma. Faqat atamalarni qaytar.")
    try:
        q = await asyncio.wait_for(llm.generate(prompt, system="Sen huquqiy qidiruv so'rovlarini tuzasan.",
                                                models=config.LITE_MODELS, timeout=8), 18)
    except Exception:
        q = ""  # retrieval still works on the raw text
    return normalize(q or text)


async def retrieve(query: str) -> list:
    try:
        [vector] = await llm.embed([query], task="RETRIEVAL_QUERY", wait=False)
    except Exception:
        # Free-tier embedding quota (daily) exhausted: keyword search still finds the right articles.
        log.warning("query embedding failed, using keyword search only", exc_info=True)
        vector = None
    return await db.search(vector, query)


def sources_block(rows) -> str:
    if not rows:
        return "MANBALAR: (bazadan mos modda topilmadi)"
    parts = [f"[{i}] {short_title(r['title'])} — {r['article']}\n{r['body']}" for i, r in enumerate(rows, 1)]
    return "MANBALAR:\n\n" + "\n\n".join(parts)


def finalize(raw: str, rows) -> Reply:
    """Strips the offer marker and appends links only for sources the answer actually cited."""
    offer_match = _OFFER.search(raw)
    text = _OFFER.sub("", raw).replace("**", "").strip()
    cited = sorted({int(n) for n in _CITE.findall(text) if 0 < int(n) <= len(rows)})
    if cited:
        links = []
        for n in cited:
            r = rows[n - 1]
            url = f"{r['url']}#{r['anchor']}" if r["anchor"] else r["url"]
            links.append(f"[{n}] {short_title(r['title'])}, {r['article'].rstrip('.')}\n{url}")
        text += "\n\n📚 Manbalar (lex.uz):\n" + "\n".join(links)
    return Reply(text, offer_match.group(1).strip()[:300] if offer_match else None)


async def answer(user_id: int, text: str) -> Reply:
    rows = await retrieve(await search_query(user_id, text))
    history = await db.history(user_id)
    contents = llm.history_contents(history, [llm.types.Part(text=f"{sources_block(rows)}\n\nSAVOL: {text}")])
    raw = await llm.generate(contents, SYSTEM.format(today=_today()))
    reply = finalize(raw, rows)
    await db.add_message(user_id, "user", text)
    await db.add_message(user_id, "model", reply.text)
    return reply


async def analyze_file(user_id: int, parts: list, caption: str) -> Reply:
    """parts: Gemini parts for the uploaded file (image/PDF bytes, or extracted text)."""
    extracted = await llm.generate_json(
        parts + [f"Foydalanuvchi izohi: {caption or '-'}"],
        system="Sen hujjatlardan matnni aniq ko'chirib oluvchi yordamchisan.",
        schema=EXTRACT_SCHEMA,
    )
    doc_text = (extracted.get("text") or "")[:20000]
    rows = await retrieve(normalize(extracted.get("search_query") or caption or doc_text[:500]))
    question = caption or "Shu hujjatni tahlil qilib ber."
    user_turn = f"[Yuborilgan hujjat: {extracted.get('doc_type', 'hujjat')}]\n{doc_text}\n\nSAVOL: {question}"
    contents = llm.history_contents(await db.history(user_id, limit=4),
                                    [llm.types.Part(text=f"{sources_block(rows)}\n\n{user_turn}")])
    raw = await llm.generate(contents, FILE_SYSTEM.format(today=_today()))
    reply = finalize(raw, rows)
    await db.add_message(user_id, "user", user_turn[:12000])  # keeps follow-up questions about the document working
    await db.add_message(user_id, "model", reply.text)
    return reply


async def draft_document(user_id: int, description: str) -> tuple[str, str]:
    """Returns (title, body) of the drafted document."""
    rows = await retrieve(normalize(description))
    history = await db.history(user_id, limit=10)
    contents = llm.history_contents(history, [llm.types.Part(
        text=f"{sources_block(rows)}\n\nYuqoridagi suhbat asosida quyidagi hujjatni tuzib ber: {description}")])
    raw = await llm.generate(contents, DRAFT_SYSTEM.format(today=_today()), temperature=0.3)
    raw = raw.replace("**", "").strip()
    title, _, body = raw.partition("\n")
    return title.strip(" #") or "HUJJAT", body.strip()
