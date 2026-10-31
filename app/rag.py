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
1. aniq qadam (qayerga, nima bilan, qachongacha). Eng tez qonuniy yo'lni birinchi yoz; manbalarda boshqa
   yo'l ham bo'lsa (masalan: qarzni o'zi to'lab taqiqni yechish, bo'lib to'lash, kechiktirish) — uni ham ayt
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
10. Foydalanuvchi aniq moddani tilga olsa va u manbalarda bo'lsa, avval u modda aslida nima haqida ekanini
   bir gapda ayt. Vaziyatiga taalluqli bo'lmasa, buni ochiq ayt va to'g'ri normalarni ko'rsat. Taalluqli
   bo'lmagan moddani boshqa joyda (📌 yoki ✅ bo'limida) ISHLATMA va undan maslahat chiqarma.
11. Qonunni chetlab o'tish, firibgarlik yoki hujjat soxtalashtirishga yordam berma.
12. MUQOBIL YO'LLARNI TASHLAB KETMA: javob yozishdan oldin BARCHA manbalarni ko'rib chiq. Ularda foydalanuvchiga
   yengillik beradigan norma bo'lsa (ijroni kechiktirish, bo'lib-bo'lib to'lash, kelishuv bitimi, ixtiyoriy
   to'lab cheklovni yechish, shikoyat yoki apellyatsiya, imtiyoz) — uni ✅ bo'limida ALOHIDA qadam qilib,
   kimga ariza berishini va manba raqamini ko'rsatib yoz. Bu foydalanuvchi uchun eng qimmatli ma'lumot."""

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


def display_title(title: str, kind: str = "law") -> str:
    """"...O'zbekiston Respublikasining Mehnat kodeksi" -> "Mehnat kodeksi" for compact source links;
    regulations keep their number ("... (VMQ-172-son)") so the user can tell a decree from a law."""
    t = re.sub(r"^O'zbekiston Respublikasi(ning)?\s+", "", short_title(title))
    if kind != "law":
        number = re.match(r"^\s*(\S+-son)\b", title)
        t = f"{t} ({number.group(1)})" if number else t
    elif t.endswith("to'g'risida"):  # "Iste'molchilarning ... to'g'risida" is a law, not a code
        t += "gi qonun"
    return t[:1].upper() + t[1:]


ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "laws": {"type": "array", "items": {"type": "integer"},
                 "description": "Vaziyatga taalluqli 1-4 ta hujjatning ID raqami (ro'yxatdan, eng muhimi birinchi)"},
        "terms": {"type": "string",
                  "description": "Qonun matnida qanday yozilsa, shunday 3-6 ta aniq huquqiy atama (o'zbek lotin)"},
    },
    "required": ["laws", "terms"],
}
_catalog: tuple[float, dict[int, str], str, dict[int, str]] = (0.0, {}, "", {})


async def law_catalog() -> tuple[dict[int, str], str]:
    """All laws in the DB as 'id | name' lines — the AI's table of contents (laws only: thousands of
    regulation titles would not fit a prompt; those are found by name/topic/keywords). Cached for an hour."""
    global _catalog
    if time.monotonic() - _catalog[0] > 3600:
        # "...kodeksini tasdiqlash" laws are one-article formalities; for regulations "...qoidalarini tasdiqlash"
        # IS the rulebook (traffic rules, VMQ-172), so the filter applies to laws only
        rows = [r for r in await db.law_catalog() if r["kind"] != "law" or not _CEREMONIAL.search(r["title"])]
        names = {r["doc_id"]: short_title(r["title"])[:90] for r in rows if r["kind"] == "law"}  # shorter = faster
        everything = {r["doc_id"]: short_title(r["title"])[:200] for r in rows}
        _catalog = (time.monotonic(), names, "\n".join(f"{i} | {n}" for i, n in names.items()), everything)
    return _catalog[1], _catalog[2]


async def all_doc_names() -> dict[int, str]:
    """Laws and regulations — for matching by name and the topic map."""
    await law_catalog()
    return _catalog[3]


_CEREMONIAL = re.compile(r"tasdiqlash to.g.risida|kunini belgilash|kuni to.g.risida|amalga kiritish tartibi", re.I)

# Everyday situations -> (title fragments of the laws that govern them, extra search terms). Works without AI,
# so answers stay on the right law even when free-tier models are overloaded. Matched without apostrophes.
TOPICS = [
    (r"musiqa|shovqin|baland ovoz|tinchlik bermay|uxlay olmay", ["aholini shovqinning", "mamuriy javobgarlik"],
     "shovqin osoyishtalik tungi vaqt maishiy shovqin"),
    (r"ish haq|oylik|oylig|maosh|ishdan bo.?shat|ishdan haydash|tatil|mehnat shartnoma|ish beruvchi|ishxona|ishga ol",
     ["ozbekiston respublikasining mehnat kodeksi"], "ish haqini tolash muddatlari kechiktirganlik ish beruvchining javobgarligi"),
    (r"ajrash|aliment|nikoh|erim|xotinim|farzand|vasiylik", ["ozbekiston respublikasining oila kodeksi"],
     "nikoh aliment bola ota-ona"),
    (r"ijara|ijarachi|kvartira|uy egasi|kvartirant", ["fuqarolik kodeksi (ikkinchi", "ozbekiston respublikasining uy-joy kodeksi"],
     "ijara shartnomasi ijaraga beruvchi ijarachi"),
    # "o'g'irlab" is spelt differently from "o'g'rilik", so each crime carries its legal term
    (r"ogirla|ogri|ugirla", ["ozbekiston respublikasining jinoyat kodeksi"], "ogrilik"),
    (r"firib|aldab|aldash|aldov|aldadi|pulimni olib|kartamdan", ["ozbekiston respublikasining jinoyat kodeksi"], "firibgarlik"),
    (r"urdi|urishdi|kaltak|tan jarohat|jarohat|dopposla",
     ["ozbekiston respublikasining jinoyat kodeksi", "mamuriy javobgarlik togrisidagi kodeksi"], "qasddan badanga yengil shikast"),
    (r"pora|qamal|jinoyat|tergov|ushlab olishdi|hibs", ["ozbekiston respublikasining jinoyat kodeksi", "jinoyat-protsessual"],
     "jinoyat jazo ushlab turish"),
    (r"jarima|yhxx|gai|inspektor|haydovchilik|prava|mast holda|svetofor|tezlik|radar|kamera|qizil chiroq|"
     r"mashina|avtomobil|piyoda|parkovka|toxtash joy",
     ["yol harakati qoidalarini tasdiqlash", "mamuriy javobgarlik togrisidagi kodeksi", "yol harakati togrisida"],
     "haydovchi transport vositasi yol harakati jarima tezlik"),
    (r"propiska|registratsiya|royxatga tur|yashash joyi|vaqtincha royxat|doimiy royxat",
     ["propiska", "yashash joyi manzilini", "doimiy yashash joyi boyicha"], "propiska yashash joyi royxatga olish doimiy vaqtincha"),
    (r"kommunal|svet|elektr|gaz puli|tabiiy gaz|suv puli|issiq suv|hisoblagich|schetchik|isitish",
     ["elektr energiyasini yetkazib berish tartibi", "elektr va issiqlik energiyasidan foydalanish qoidalari",
      "hisobga olish uskunala", "tabiiy gaz bilan limitsiz", "suv taminoti va suvoqava kommunal tizimidan foydalanish"],
     "kommunal xizmat isteʼmolchi hisoblagich tolov"),
    (r"kredit|qarz|bank|mikroqarz|nasiya|foiz", ["istemol krediti", "fuqarolik kodeksi (birinchi"], "kredit qarz foiz"),
    (r"ipoteka|garov", ["ipoteka togrisida", "garov togrisida"], "ipoteka garov"),
    (r"dokon|sifatsiz|kafolat|tovar|qaytarib olish|xarid|sotib oldim|buzildi|almashtir", ["istemolchilarning huquqlarini"],
     "istemolchi tovar sifat kafolat sotuvchi"),
    (r"notarius|ishonchnoma|vasiyat|meros", ["notariat togrisida", "fuqarolik kodeksi (ikkinchi"], "meros vasiyatnoma notarial"),
    (r"pensiya|nafaqa", ["davlat pensiya taminoti"], "pensiya tayinlash"),
    (r"maktab|oqish|universitet|kontrakt|oqituvchi|talaba", ["talim togrisida"], "talim oquvchi talaba"),
    (r"bogcha", ["maktabgacha talim"], "maktabgacha talim"),
    (r"soliq|yatt|tadbirkor|biznes|patent", ["ozbekiston respublikasining soliq kodeksi"], "soliq soliq tolovchi"),
    (r"zoravon|kaltakla|tazyiq|himoya order", ["xotin-qizlarni tazyiq"], "zoravonlik himoya order"),
    (r"advokat", ["advokatura togrisida"], "advokat yuridik yordam"),
    (r"shikoyat|murojaat|hokimiyat|byurokrat|javob bermay", ["jismoniy va yuridik shaxslarning murojaatlari"], "murojaat korib chiqish"),
    (r"sud qarori|ijrochi|\bmib|majburiy ijro|ijro varaq|taqiq|chet elga chiq|chiqa olmay|xatla|qarzdor|undiruv",
     ["sud hujjatlari va boshqa organlar hujjatlarini ijro etish togrisida", "chiqishini vaqtincha cheklash"],
     "qarzdor chiqishini vaqtincha cheklash cheklashni olib tashlash ixtiyoriy ijro bolib-bolib ijro kechiktirish"),
    (r"yer uchast|tomorqa|yer maydon", ["ozbekiston respublikasining yer kodeksi"], "yer uchastkasi"),
    (r"sugurta|osago", ["sugurta togrisida"], "sugurta"),
    (r"nogiron", ["nogironligi bolgan shaxslarning"], "nogironlik"),
    (r"shaxsiy malumot|malumotlarimni|pasport.*tarqat", ["shaxsga doir"], "shaxsga doir malumotlar"),
]


def topic_laws(text: str, names: dict[int, str]) -> tuple[list[int], str]:
    """Laws (and extra search terms) for everyday situations recognised in the user's own words."""
    low = normalize(text).lower().replace("'", "")
    flat = {i: n.lower().replace("'", "") for i, n in names.items()}
    ids: list[int] = []
    extra = []
    for pattern, fragments, terms in TOPICS:
        if re.search(pattern, low):
            extra.append(terms)
            for f in fragments:  # at most 2 documents per fragment, so one generic word can't take every slot
                ids += [i for i, n in flat.items() if f in n and i not in ids][:2]
    return ids[:6], " ".join(extra)


_route_paused_until = 0.0


async def search_query(user_id: int, text: str) -> tuple[str, list[int]]:
    """Like a lawyer: decides which laws govern the situation (from the full list of laws in force) and
    turns everyday wording / follow-ups into legal search terms. Returns (terms, doc_ids)."""
    global _route_paused_until
    names, catalog = await law_catalog()
    everything = await all_doc_names()
    topic_ids, topic_terms = topic_laws(text, everything)
    if time.monotonic() < _route_paused_until:  # models overloaded a moment ago: answer fast from the topic map
        return _without_ai(text, topic_ids, topic_terms, everything)
    rows = await db.history(user_id, limit=4)
    convo = "\n".join(f"{r['role']}: {r['content'][:600]}" for r in rows)
    prompt = (f"O'zbekistonning amaldagi qonunlari va kodekslari (ID | nomi):\n{catalog}\n\n"
              f"Suhbat:\n{convo or '-'}\n\nOxirgi xabar: {text}\n\n"
              "Tajribali advokatdek o'yla: bu vaziyatga qaysi hujjatlar taalluqli? Ro'yxatdan 1-4 ta ID tanla "
              "(masalan: o'g'rilik — Jinoyat kodeksi; ijara — Fuqarolik kodeksi; ish haqi — Mehnat kodeksi; "
              "maxsus qonun bo'lsa — uni ham). Qidiruv uchun 3-6 ta aniq huquqiy atama yoz, \"O'zbekiston\", "
              "\"kodeks\", \"modda\" kabi umumiy so'zlarsiz.")
    try:
        plan = await asyncio.wait_for(llm.generate_json(
            prompt, "Sen O'zbekiston qonunchiligini to'liq biladigan advokatsan.", ROUTE_SCHEMA,
            models=config.ROUTER_MODELS, timeout=25), 60)
    except Exception as exc:
        _route_paused_until = time.monotonic() + 300
        log.warning("law routing failed (%s); using the topic map for 5 min", type(exc).__name__)
        return _without_ai(text, topic_ids, topic_terms, everything)
    terms = normalize(f"{plan.get('terms') or text} {topic_terms}")
    doc_ids = [i for i in plan.get("laws", []) if i in names][:4]  # model output: keep only real law ids
    doc_ids += [i for i in topic_ids if i not in doc_ids]
    return terms, doc_ids + [i for i in title_matches(terms, everything) if i not in doc_ids][:2]


def _without_ai(text: str, topic_ids: list[int], topic_terms: str, names: dict[int, str]) -> tuple[str, list[int]]:
    """Search when the AI router is unavailable. A recognised situation searches its legal terms only: the user's
    own words ("telefonimni", "pulimni olishdi") would match unrelated acts (telecom rules, bribery)."""
    q = normalize(topic_terms or text)
    return q, topic_ids + [i for i in title_matches(q, names) if i not in topic_ids][:2]


_GENERIC = {"huquqi", "huquql", "qonunc", "fuqaro", "davlat", "himoya", "javobg", "majbur", "tartib", "shartn",
            "faoliy", "respub", "ozbeki", "toglis", "togris", "mamuri", "huquqb", "jinoya"}


def title_matches(terms: str, names: dict[int, str]) -> list[int]:
    """Laws whose very name contains a search term ("shovqin" -> the law on noise): a deterministic safety net
    for when the AI's pick from ~600 laws misses the specialized one."""
    stems = {w[:6] for w in re.findall(r"\w+", terms.lower().replace("'", "")) if len(w) >= 6} - _GENERIC
    flat = {i: n.lower().replace("'", "") for i, n in names.items()}
    hits = {st: [i for i, n in flat.items() if st in n] for st in stems}
    out: list[int] = []
    # rare words first ("shovqin" names 1 law, "solish" names dozens); words in >8 law names say nothing
    for st in sorted(hits, key=lambda st: len(hits[st])):
        if len(hits[st]) <= 8:
            out += [i for i in hits[st] if i not in out]
    return out[:5]


TRANSCRIBE_SYSTEM = """Sen ovozli xabarlarni matnga aylantiruvchisan. Foydalanuvchi o'zbek (yoki rus) tilida,
ko'pincha shevada gapiradi. Aytilgan gapni AYNAN, ma'nosini o'zgartirmasdan yoz: o'zbekcha bo'lsa lotin
alifbosida, ruscha bo'lsa rus tilida. Takrorlar va "ee", "mm" kabi tovushlarni tashlab yubor. Hech narsa
qo'shma, javob berma, izoh yozma. Nutq bo'lmasa yoki tushunib bo'lmasa — bo'sh qator qaytar."""


async def transcribe(audio: bytes, mime_type: str) -> str:
    text = await llm.generate([llm.file_part(audio, mime_type), "Shu ovozli xabarni matnga aylantir."],
                              TRANSCRIBE_SYSTEM, models=config.LITE_MODELS + config.CHAT_MODELS, timeout=40)
    return text.strip().strip("«»\"")


_embed_paused_until = 0.0


async def retrieve(query: str, doc_ids: list[int] | None = None) -> list:
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
    return await db.search(vector, query, doc_ids=doc_ids)


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
            name = html.escape(f"{display_title(r['title'], r.get('kind') or 'law')}, {article}", quote=False)
            links.append(f'[{n}] <a href="{html.escape(url)}">{name}</a>')
        text += "\n\n<b>📚 Manbalar (lex.uz)</b>\n" + "\n".join(links)
    offer = offer_match.group(1).strip()[:300] if offer_match else None
    return Reply(text, offer, plain_md.replace("**", ""))


CODE_DOCS = {  # code names people write -> lex.uz doc ids
    "mehnat": [6257288], "jinoyat-protsessual": [111460], "jinoyat": [111453], "fuqarolik protsessual": [3517337],
    "fuqarolik": [111189, 180552], "mamuriy": [97664], "oila": [104720], "soliq": [4674902], "uy-joy": [106136],
    "uy joy": [106136], "konstitutsiya": [6445145], "yer kodeks": [152653], "bojxona": [2876354],
}
_ART = re.compile(r"(\d{1,4})\s*[-–]?\s*modda")


def cited(text: str) -> list[tuple[str, list[int]]]:
    """'Mehnat kodeksidagi 454-moddani' -> [('454', [6257288])]. Only when the code is named: a bare number is ambiguous."""
    low = normalize(text).lower().replace("'", "")
    docs: list[int] = []
    for key, ids in CODE_DOCS.items():
        if key in low:
            docs += [i for i in ids if i not in docs]
            low = low.replace(key, " ")  # "jinoyat-protsessual" must not also count as "jinoyat"
    return [(n, docs) for n in dict.fromkeys(_ART.findall(normalize(text).lower()))][:3] if docs else []


_CYRILLIC = re.compile(r"[а-яёқғҳў]", re.I)
_MIXED = re.compile(r"[a-z][а-яёқғҳў]|[а-яёқғҳў][a-z]", re.I)
_NOT_UZ_LATIN = re.compile(r"[а-яёқғҳўà-ÿ]|c(?!h)|w", re.I)


def garbled(question: str, raw: str) -> bool:
    """Free-tier models sometimes emit a broken token inside a word ("belgilanши", "conductoriga")."""
    if _CYRILLIC.search(question):  # Cyrillic/Russian question: only words mixing both scripts are wrong
        return bool(_MIXED.search(raw))
    return bool(_NOT_UZ_LATIN.search(raw))


async def generate_clean(contents, system: str, question: str) -> str:
    raw = await llm.generate(contents, system, temperature=0)  # higher temperature garbles Uzbek words more often
    if garbled(question, raw):
        log.warning("garbled answer, regenerating with the next model")
        raw = await llm.generate(contents, system, models=config.CHAT_MODELS[1:], temperature=0)
    return raw


async def answer(user_id: int, text: str) -> Reply:
    rows = await retrieve(*await search_query(user_id, text))
    exact = [r for n, docs in cited(text) for r in await db.article_rows(n, docs)]
    if exact:  # the article the user named goes first, so the answer can say what it really covers
        seen = {(r["url"], r["article"]) for r in exact}
        rows = (exact + [r for r in rows if (r["url"], r["article"]) not in seen])[:8]
    history = await db.history(user_id)
    contents = llm.history_contents(history, [llm.types.Part(text=f"{sources_block(rows)}\n\nSAVOL: {text}")])
    raw = await generate_clean(contents, SYSTEM.format(today=_today()), text)
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
    situation = f"{extracted.get('doc_type', '')}: {extracted.get('search_query') or caption or doc_text[:500]}"
    rows = await retrieve(*await search_query(user_id, situation))
    question = caption or "Shu hujjatni tahlil qilib ber."
    user_turn = f"[Yuborilgan hujjat: {extracted.get('doc_type', 'hujjat')}]\n{doc_text}\n\nSAVOL: {question}"
    contents = llm.history_contents(await db.history(user_id, limit=4),
                                    [llm.types.Part(text=f"{sources_block(rows)}\n\n{user_turn}")])
    raw = await generate_clean(contents, FILE_SYSTEM.format(today=_today()), question)
    reply = finalize(raw, rows)
    await db.add_message(user_id, "user", user_turn[:12000])  # keeps follow-up questions about the document working
    await db.add_message(user_id, "model", reply.plain)
    return reply


async def draft_document(user_id: int, description: str) -> tuple[str, str]:
    """Returns (title, body) of the drafted document."""
    rows = await retrieve(*await search_query(user_id, f"Hujjat tayyorlash kerak: {description}"))
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
