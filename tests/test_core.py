import datetime as dt

from app import db, lexuz, payments, rag
from app.bot import split_text
from app.translit import normalize, to_latin

TASHKENT = payments.TASHKENT


def test_translit():
    assert to_latin("Ўзбекистон Республикасининг Маъмурий жавобгарлик тўғрисидаги кодекси") == \
        "O'zbekiston Respublikasining Ma'muriy javobgarlik to'g'risidagi kodeksi"
    assert to_latin("Ер кодекси") == "Yer kodeksi"
    assert to_latin("Конституцияси") == "Konstitutsiyasi"
    assert to_latin("ШАРТНОМА") == "SHARTNOMA"
    assert normalize("oʻzbek g‘alla") == "o'zbek g'alla"


def _elem(cls, anchor, text):
    return (f'<div class="{cls} lx_elem"><div class="lx_elem2"><div class="lx_elem3"><span>Audioni tinglash</span>'
            f'</div></div><div name="{anchor}" id="{anchor}">{text}</div></div>')


HTML = ("<html><head><title>&nbsp; 28.10.2022.&nbsp;Ўзбекистон Республикасининг Меҳнат кодекси</title></head><body>"
        + _elem("TEXT_HEADER_DEFAULT", 1, "БИРИНЧИ БЎЛИМ. УМУМИЙ ҚОИДАЛАР")
        + _elem("TEXT_HEADER_DEFAULT", 2, "1-боб. Асосий қоидалар")
        + _elem("CLAUSE_DEFAULT", 3, "1-модда. Кодекснинг вазифалари")
        + _elem("ACT_TEXT", 4, "Биринчи қисм.")
        + _elem("ACT_TEXT", 5, "Иккинчи қисм.")
        + '<div class="COMMENT lx_no_select"><div id="99">LexUZ шарҳи</div></div>'
        + _elem("CLAUSE_DEFAULT", 6, "2<sup>1</sup>-модда.")
        + _elem("ACT_TEXT", 7, "Матн.")
        + "</body></html>")


def test_parse_document():
    doc = lexuz.parse_document(6257288, HTML)
    assert doc.title == "28.10.2022. O'zbekiston Respublikasining Mehnat kodeksi"
    assert [a.article for a in doc.articles] == ["1-modda. Kodeksning vazifalari", "2¹-modda."]
    first = doc.articles[0]
    assert first.heading == "BIRINCHI BO'LIM. UMUMIY QOIDALAR / 1-bob. Asosiy qoidalar"
    assert first.anchor == 3
    assert first.body == "Birinchi qism.\nIkkinchi qism."  # comments and UI text are excluded
    assert len(doc.content_hash) == 64


def test_chunks_split_long_articles():
    art = lexuz.Article("1-modda.", "", 1, "\n".join(["x" * 1000] * 7))
    parts = lexuz.chunks(art)
    assert len(parts) > 1 and all(len(p) <= lexuz.MAX_CHUNK for p in parts)
    assert "".join(parts).replace("\n", "") == art.body.replace("\n", "")


def test_or_query():
    assert db.or_query("Mehnat shartnomasi 15-modda o'z") == "mehn:* | shartn:* | 15"
    assert db.or_query("bolam aliment qancha") == "bola:* | alime:*"


def _row(n):
    return {"title": "28.10.2022. O'zbekiston Respublikasining Mehnat kodeksi", "article": f"{n}-modda.", "anchor": 100 + n,
            "url": "https://lex.uz/uz/docs/6257288", "body": "..."}


def test_finalize_cites_only_used_sources_and_extracts_offer():
    raw = "**⚖️ Qisqa javob**\nIsh haqi <kechikdi> [2] va [9].\n[[HUJJAT: ish beruvchiga talabnoma]]"
    reply = rag.finalize(raw, [_row(1), _row(2)])
    assert reply.offer == "ish beruvchiga talabnoma"
    assert reply.text.startswith("<b>⚖️ Qisqa javob</b>")
    assert "&lt;kechikdi&gt;" in reply.text  # model text is escaped, never raw HTML
    assert '<a href="https://lex.uz/uz/docs/6257288#102">Mehnat kodeksi, 2-modda</a>' in reply.text
    assert "#101" not in reply.text and "[[" not in reply.text
    assert "**" not in reply.plain and "<b>" not in reply.plain


def test_split_text():
    parts = split_text("a" * 9000 + "\nshort")
    assert all(len(p) <= 4000 for p in parts) and parts[-1].endswith("short")


NOW = dt.datetime(2026, 10, 26, 15, 0, tzinfo=TASHKENT)
GOOD = {"is_receipt": True, "success": True, "amount": 30000, "currency": "UZS", "recipient_card_last4": "4321",
        "recipient_name": "", "paid_at": "2026-10-26T12:00", "transaction_id": "T1", "tampering_signs": ""}


def decide(**changes):
    return payments.decide({**GOOD, **changes}, NOW, 15000, "8600 1234 5678 4321", "ALIYEV VALI", 48)


def test_receipt_accepted():
    assert decide() == (True, "To'lov qabul qilindi", 2)
    assert decide(recipient_card_last4="", recipient_name="VALI A.")[0]  # name match is enough


def test_receipt_rejections():
    assert not decide(is_receipt=False)[0]
    assert not decide(success=False)[0]
    assert not decide(amount=10000)[0]
    assert not decide(recipient_card_last4="9999")[0]
    assert not decide(paid_at="2026-10-20T12:00")[0]   # too old
    assert not decide(paid_at="2026-10-27T12:00")[0]   # future
    assert not decide(paid_at="")[0]
    assert not decide(tampering_signs="raqamlar shrifti boshqacha")[0]
    assert not decide(currency="USD")[0]


def test_display_title():
    assert rag.display_title("28.10.2022. O'zbekiston Respublikasining Mehnat kodeksi") == "Mehnat kodeksi"
    assert rag.display_title("221-I-son 26.04.1996. Iste'molchilarning huquqlarini himoya qilish to'g'risida") == \
        "Iste'molchilarning huquqlarini himoya qilish to'g'risidagi qonun"


def test_law_name():
    from app.ingest import law_name
    assert law_name("O'RQ-900-son 19.01.2024. Yo'l harakati to'g'risida") == "Yo'l harakati to'g'risida"
    assert law_name("28.10.2022. O'zbekiston Respublikasining Mehnat kodeksi") == "O'zbekiston Respublikasining Mehnat kodeksi"


def test_title_matches():
    names = {1: "Aholini shovqinning zararli ta'siridan himoya qilish to'g'risida", 2: "Mehnat kodeksi",
             3: "Fuqarolarning davlat pensiya ta'minoti to'g'risida"}
    assert rag.title_matches("shovqin solish, tungi vaqt, fuqarolar huquqi", names) == [1]
    assert rag.title_matches("pensiya tayinlash", names) == [3]
