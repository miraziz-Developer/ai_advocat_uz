"""Card-transfer payments: the AI reads the receipt screenshot, plain code decides whether to accept it.

shortcut: an AI cannot prove a screenshot is genuine — a well-edited fake can pass. Every approval is sent to
the admins with a revoke button; move to Click/Payme merchant API (server-side confirmation) once revenue justifies it.
"""
import datetime as dt
import re

from app import config, llm
from app.translit import normalize

TASHKENT = dt.timezone(dt.timedelta(hours=5))
MAX_CREDITS_PER_RECEIPT = 50

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_receipt": {"type": "boolean", "description": "Bu bank/Click/Payme/Uzum va h.k. to'lov cheki yoki skrinshotimi"},
        "success": {"type": "boolean", "description": "To'lov muvaffaqiyatli o'tganmi (Успешно / Muvaffaqiyatli / O'tkazildi)"},
        "amount": {"type": "number", "description": "O'tkazilgan summa, so'mda (komissiyasiz)"},
        "currency": {"type": "string"},
        "recipient_card_last4": {"type": "string", "description": "Qabul qiluvchi karta raqamining oxirgi 4 raqami, ko'rinmasa bo'sh"},
        "recipient_name": {"type": "string", "description": "Qabul qiluvchi ismi, ko'rinmasa bo'sh"},
        "paid_at": {"type": "string", "description": "To'lov vaqti ISO formatda YYYY-MM-DDTHH:MM (Toshkent vaqti), ko'rinmasa bo'sh"},
        "transaction_id": {"type": "string", "description": "Tranzaksiya / chek raqami, ko'rinmasa bo'sh"},
        "tampering_signs": {"type": "string", "description": "Tahrirlanganlik belgilari (shriftlar, tekislash, "
                                                             "noodatiy elementlar); yo'q bo'lsa bo'sh"},
    },
    "required": ["is_receipt", "success", "amount", "currency", "recipient_card_last4", "recipient_name",
                 "paid_at", "transaction_id", "tampering_signs"],
}

SYSTEM = """Sen to'lov cheklarini tekshiruvchi mutaxassissan. Rasmdagi ma'lumotlarni AYNAN ko'ringanidek o'qi,
hech narsani taxmin qilma. Agar rasm chek emas (oddiy rasm, matn, boshqa narsa) bo'lsa — is_receipt=false.
To'lov holati "kutilmoqda", "bekor qilindi", "xato" bo'lsa — success=false. Bugungi sana: {today}."""


async def check_receipt(image: bytes, mime_type: str) -> dict:
    today = dt.datetime.now(TASHKENT).strftime("%Y-%m-%d %H:%M")
    return await llm.generate_json([llm.file_part(image, mime_type)], SYSTEM.format(today=today), RECEIPT_SCHEMA)


def _name_matches(holder: str, seen: str) -> bool:
    seen = normalize(seen).lower()
    return any(len(t) >= 3 and t in seen for t in re.findall(r"\w+", normalize(holder).lower()))


def decide(r: dict, now: dt.datetime, price: int, card_number: str, holder: str,
           max_age_hours: int) -> tuple[bool, str, int]:
    """Returns (approved, reason for the user, credits)."""
    if not r.get("is_receipt"):
        return False, "Bu to'lov chekiga o'xshamaydi. To'lov ilovasidagi chek skrinshotini yuboring.", 0
    if not r.get("success"):
        return False, "Chekda to'lov muvaffaqiyatli o'tgani ko'rinmayapti.", 0
    if r.get("tampering_signs"):
        return False, "Chek tekshiruvdan o'tmadi. Asl skrinshotni yuboring yoki admin bilan bog'laning.", 0

    currency = (r.get("currency") or "UZS").upper()
    if currency not in {"UZS", "SUM", "SO'M", "SOM", "СУМ", "СЎМ"}:
        return False, "To'lov so'mda bo'lishi kerak.", 0
    amount = int(r.get("amount") or 0)
    if amount < price:
        return False, f"Summa yetarli emas: {amount:,} so'm. Kamida {price:,} so'm kerak.".replace(",", " "), 0

    last4 = re.sub(r"\D", "", r.get("recipient_card_last4") or "")[-4:]
    card_ok = bool(last4) and card_number.replace(" ", "").endswith(last4)
    name_ok = bool(r.get("recipient_name")) and _name_matches(holder, r["recipient_name"])
    if not (card_ok or name_ok):
        return False, "Chekdagi qabul qiluvchi bizning karta/ism bilan mos kelmadi.", 0

    try:
        paid_at = dt.datetime.fromisoformat(r.get("paid_at") or "")
    except ValueError:
        return False, "Chekda to'lov sanasi/vaqti ko'rinmayapti. To'liq skrinshot yuboring.", 0
    if paid_at.tzinfo is None:
        paid_at = paid_at.replace(tzinfo=TASHKENT)
    if paid_at > now + dt.timedelta(minutes=15):
        return False, "Chekdagi vaqt noto'g'ri (kelajakdagi sana).", 0
    if now - paid_at > dt.timedelta(hours=max_age_hours):
        return False, f"Chek eski: {max_age_hours} soatdan oldingi to'lovlar qabul qilinmaydi.", 0

    credits = min(amount // price, MAX_CREDITS_PER_RECEIPT)
    return True, "To'lov qabul qilindi", credits


def decide_now(r: dict) -> tuple[bool, str, int]:
    return decide(r, dt.datetime.now(TASHKENT), config.DOC_PRICE, config.CARD_NUMBER, config.CARD_HOLDER,
                  config.RECEIPT_MAX_AGE_HOURS)
