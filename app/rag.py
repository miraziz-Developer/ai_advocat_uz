"""Retrieval-augmented answers: every legal claim must come from lex.uz text stored in the DB."""
import asyncio
import datetime as dt
import html
import logging
import re
import time
from dataclasses import dataclass

from app import config, db, llm
from app.translit import normalize

SYSTEM = """Sen — «AI Huquqiy Yordamchi»: O'zbekiston qonunchiligini mukammal biladigan tajribali advokatdek
fikrlaydigan yordamchisan. Bugungi sana: {today}.

ADVOKATDEK ISHLA: foydalanuvchi faktlarini huquqiy baholaysan — bu qanday huquqbuzarlik/nizo, qaysi modda
bo'yicha, kim javobgar, qanday oqibat bo'ladi. Keyin uning manfaatini himoya qiladigan aniq strategiya berasan.
Foydalanuvchi tomonida tur, lekin rostini ayt: zaif tomoni yoki xavfi bo'lsa — ochiq ayt.

QAT'IY QOIDALAR:
1. Huquqiy normalarni FAQAT so'rov bilan berilgan MANBALAR (lex.uz rasmiy matnlari) asosida keltir.
   Modda raqami, muddat, jarima, jazo yoki summa manbada bo'lmasa — uni HECH QACHON o'zingdan yozma.
2. Har bir huquqiy fikrdan keyin manba raqamini [1], [2] ko'rinishida qo'y.
3. Manbalarda mos norma bo'lmasa, bitta qisqa gap bilan ayt: "Bu bo'yicha aniq modda bazada topilmadi."
   Umumiy amaliy maslahat berishing mumkin, lekin uni qonun normasi sifatida ko'rsatma.
   Savolga aloqasi yo'q manbalarni keltirma.
4. JAVOB QISQA, ANIQ VA TARTIBLI BO'LSIN — jami 1200 belgidan oshmasin. Har bir gap qisqa (15 so'zgacha),
   suv, takror, umumiy gaplar yo'q. Faqat foydalanuvchiga kerakli aniq ma'lumot: summa, muddat, organ nomi.
5. FORMAT (aynan shunday, sarlavhalar ** ichida):
**⚖️ Huquqiy baho**
1-2 gap: vaziyat qonun bo'yicha nima (masalan: "Bu — Jinoyat kodeksining 109-moddasi: qasddan badanga
yengil shikast yetkazish") va asosiy xulosa.

**📌 Qonun nima deydi**
• eng muhim 1-3 norma, har biri bitta qator [1]. Jazo, jarima, kompensatsiya, muddat manbada bo'lsa —
  ANIQ raqami bilan yoz (masalan: "BHMning 25 baravarigacha jarima yoki 1 yilgacha axloq tuzatish ishlari").

**✅ Nima qilish kerak**
1. aniq qadam (qayerga, nima bilan, qachongacha)
2. ...
(ko'pi bilan 4 qadam; kerak bo'lsa bitta qadam — qaysi dalillarni yig'ish: chek, guvoh, tibbiy ma'lumotnoma,
yozishma, video)

**⚠️ Diqqat**
bitta eng muhim ogohlantirish (muddat, xavf).

❓ Vaziyat noaniq bo'lsa — faqat BITTA eng muhim aniqlashtiruvchi savol.
6. Foydalanuvchi qaysi tilda yozsa (o'zbek lotin/kirill, rus) — o'sha tilda, oddiy va tushunarli javob ber.
   Sarlavhalarni ham o'sha tilga o'gir.
7. ** faqat sarlavhalar va eng muhim 1-2 raqam/muddat uchun. #, jadval, HTML ishlatma.
8. Jinoiy ish, sud jarayoni, katta summa yoki muddat o'tib ketish xavfi bo'lsa — litsenziyali advokatga
   murojaat qilishni ham tavsiya qil.
9. Foydalanuvchiga yozma hujjat (ariza, da'vo arizasi, shikoyat, talabnoma, tushuntirish xati, shartnoma,
   ishonchnoma, apellyatsiya va h.k.) kerak bo'lsa, javobning eng oxirida alohida qatorda aynan shunday yoz:
   [[HUJJAT: hujjat turi va kimga/nima haqida]]
   Hujjat kerak bo'lmasa, bu belgini qo'yma.
10. Qonunni chetlab o'tish, firibgarlik yoki hujjat soxtalashtirishga yordam berma."""

FILE_SYSTEM = SYSTEM + """

HOZIR foydalanuvchi hujjat yoki rasm yubordi. Yuqoridagi 5-band o'rniga SHU formatda javob ber
(jami 1500 belgidan oshmasin; foydalanuvchi alohida savol bergan bo'lsa, avval qisqa shunga javob ber):
**📄 Bu nima**
1 gap: hujjat turi va kim bilan kim o'rtasida.

**📌 Asosiy shartlar**
• summa, muddat, majburiyatlar — 3-5 qisqa qator

**⚠️ Xavfli joylar**
• foydalanuvchiga noqulay yoki qonunga zid bandlar va nima uchun [1] — eng muhimlari, 1-4 ta

**✅ Tavsiya**
1-3 qadam: imzolashdan oldin nimani o'zgartirish yoki tekshirish."""

DRAFT_SYSTEM = """Sen O'zbekiston qonunchiligi bo'yicha tajribali yuristsan va rasmiy hujjat tuzasan. Bugun: {today}.
• Hujjatni o'zbek tilida (lotin) rasmiy uslubda yoz, O'zbekistonda qabul qilingan shaklda:
  kimga (organ/shaxs), kimdan, hujjat nomi, mazmun, talab qismi, ilovalar, sana va imzo joyi.
• Normalarga faqat berilgan MANBALARdan havola qil (masalan: "Mehnat kodeksining 161-moddasiga asosan").
  Manbada bo'lmagan modda raqamini yozma.
• Foydalanuvchi bermagan ma'lumotlar uchun to'rtburchak qavsli joy qoldir: [F.I.Sh.], [manzil], [sana].
• Har bir moddani manbada qanday bo'lsa, aynan o'sha raqam bilan bir marta keltir; qavs ichida tuzatish
  yoki "manbada keltirilgan" kabi izohlar yozma.
• Markdown ishlatma. Birinchi qator — faqat hujjat nomi (masalan: DA'VO ARIZASI); matn ichida uni takrorlama.
  Undan keyin: kimga, kimdan, sana, asosiy matn, talab, ilovalar, imzo."""

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
    text: str               # Telegram HTML
    offer: str | None = None  # document the AI suggests drafting (paid)
    plain: str = ""         # same answer without markup, kept in chat history


def _today() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5))).strftime("%d.%m.%Y")


def short_title(title: str) -> str:
    """'28.10.2022. O'zbekiston Respublikasining Mehnat kodeksi' -> "O'zbekiston Respublikasining Mehnat kodeksi"."""
    return re.sub(r"^.*?\d{2}\.\d{2}\.\d{4}\.\s*", "", title)


def display_title(title: str) -> str:
    """"...O'zbekiston Respublikasining Mehnat kodeksi" -> "Mehnat kodeksi" for compact source links."""
    t = re.sub(r"^O'zbekiston Respublikasi(ning)?\s+", "", short_title(title))
    if t.endswith("to'g'risida"):  # "Iste'molchilarning ... to'g'risida" is a law, not a code
        t += "gi qonun"
    return t[:1].upper() + t[1:]


async def search_query(user_id: int, text: str) -> str:
    """Turns everyday wording ('telefonimni o'g'irlab ketishdi') and follow-ups ('unda nima qilay?') into a
    standalone query in legal terms ("o'g'rilik jinoyat kodeksi"); keyword search depends on it."""
    rows = await db.history(user_id, limit=4)
    convo = "\n".join(f"{r['role']}: {r['content'][:600]}" for r in rows)
    prompt = (f"Suhbat:\n{convo}\n\nOxirgi xabar: {text}\n\n"
              "Shu xabar bo'yicha O'zbekiston qonunlaridan tegishli moddalarni qidirish uchun o'zbek (lotin) "
              "tilida 3-6 ta aniq huquqiy atama yoz (masalan: o'g'rilik; aliment bola; ish haqi to'lanmasligi). "
              "Qonun matnida qanday yozilsa shunday yoz. "
              "Kirish so'zi, raqamlash, izoh yozma. \"O'zbekiston\", \"kodeks\", \"modda\" kabi umumiy "
              "so'zlarni yozma. Faqat atamalarni qaytar.")
    try:
        q = await asyncio.wait_for(llm.generate(prompt, system="Sen huquqiy qidiruv so'rovlarini tuzasan.",
                                                models=config.LITE_MODELS, timeout=12), 30)
    except Exception:
        q = ""  # retrieval still works on the raw text
    return normalize(q or text)


TRANSCRIBE_SYSTEM = """Sen ovozli xabarlarni matnga aylantiruvchisan. Foydalanuvchi o'zbek (yoki rus) tilida,
ko'pincha shevada gapiradi. Aytilgan gapni AYNAN, ma'nosini o'zgartirmasdan yoz: o'zbekcha bo'lsa lotin
alifbosida, ruscha bo'lsa rus tilida. Takrorlar va "ee", "mm" kabi tovushlarni tashlab yubor. Hech narsa
qo'shma, javob berma, izoh yozma. Nutq bo'lmasa yoki tushunib bo'lmasa — bo'sh qator qaytar."""


async def transcribe(audio: bytes, mime_type: str) -> str:
    text = await llm.generate([llm.file_part(audio, mime_type), "Shu ovozli xabarni matnga aylantir."],
                              TRANSCRIBE_SYSTEM, models=config.LITE_MODELS + config.CHAT_MODELS, timeout=40)
    return text.strip().strip("«»\"")


_embed_paused_until = 0.0


async def retrieve(query: str) -> list:
    global _embed_paused_until
    vector = None
    if time.monotonic() >= _embed_paused_until and await db.count_without_embedding():
        # Partial coverage would pull every answer toward the few codes that already have embeddings.
        _embed_paused_until = time.monotonic() + 600
    if time.monotonic() >= _embed_paused_until:
        try:
            [vector] = await llm.embed([query], task="RETRIEVAL_QUERY", wait=False)
        except Exception as exc:
            # Free-tier embedding quota exhausted: keyword search still finds the right articles.
            # Don't retry on every question for a while — each failed call adds latency.
            _embed_paused_until = time.monotonic() + 1800
            log.warning("query embedding failed (%s), keyword search only for 30 min", str(exc)[:120])
    return await db.search(vector, query)


def sources_block(rows) -> str:
    if not rows:
        return "MANBALAR: (bazadan mos modda topilmadi)"
    parts = [f"[{i}] {short_title(r['title'])} — {r['article']}\n{r['body']}" for i, r in enumerate(rows, 1)]
    return "MANBALAR:\n\n" + "\n\n".join(parts)


_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")


def finalize(raw: str, rows) -> Reply:
    """Strips the offer marker, renders **bold** as Telegram HTML and appends compact links
    only for sources the answer actually cited."""
    offer_match = _OFFER.search(raw)
    plain_md = re.sub(r"\n{3,}", "\n\n", _OFFER.sub("", raw)).strip()
    text = _BOLD.sub(r"<b>\1</b>", html.escape(plain_md, quote=False)).replace("**", "")
    cited = sorted({int(n) for n in _CITE.findall(plain_md) if 0 < int(n) <= len(rows)})
    if cited:
        links = []
        for n in cited:
            r = rows[n - 1]
            url = f"{r['url']}#{r['anchor']}" if r["anchor"] else r["url"]
            article = r["article"].split(".")[0]  # "333-modda"
            name = html.escape(f"{display_title(r['title'])}, {article}", quote=False)
            links.append(f'[{n}] <a href="{html.escape(url)}">{name}</a>')
        text += "\n\n<b>📚 Manbalar (lex.uz)</b>\n" + "\n".join(links)
    offer = offer_match.group(1).strip()[:300] if offer_match else None
    return Reply(text, offer, plain_md.replace("**", ""))


async def answer(user_id: int, text: str) -> Reply:
    rows = await retrieve(await search_query(user_id, text))
    history = await db.history(user_id)
    contents = llm.history_contents(history, [llm.types.Part(text=f"{sources_block(rows)}\n\nSAVOL: {text}")])
    raw = await llm.generate(contents, SYSTEM.format(today=_today()))
    reply = finalize(raw, rows)
    await db.add_message(user_id, "user", text)
    await db.add_message(user_id, "model", reply.plain)
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
    await db.add_message(user_id, "model", reply.plain)
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
    title = title.strip(" #") or "HUJJAT"
    lines = body.strip().split("\n")
    body = "\n".join(line for line in lines if line.strip().upper() != title.upper())  # model sometimes repeats the title
    return title, body.strip()
