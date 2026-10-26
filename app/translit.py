"""Uzbek Cyrillic -> Latin (lex.uz publishes Uzbek texts in Cyrillic, users write in Latin)."""
import re

_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'",
    "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}
_VOWELS = set("аеёиоуўэюяaeiou")
_APOSTROPHES = re.compile(r"[ʻʼ‘’`´]")


def to_latin(text: str) -> str:
    out = []
    prev = ""
    for i, ch in enumerate(text):
        low = ch.lower()
        if low == "е":
            # "е" is "ye" at word start or after a vowel: Ер -> Yer
            lat = "ye" if (not prev.isalpha() or prev.lower() in _VOWELS) else "e"
        else:
            lat = _MAP.get(low)
        if lat is None:
            out.append(ch)
        elif ch.isupper() and lat:
            nxt = text[i + 1] if i + 1 < len(text) else ""
            all_caps = prev.isupper() or nxt.isupper()  # ШАРТНОМА -> SHARTNOMA, Шарт -> Shart
            out.append(lat.upper() if all_caps else lat[0].upper() + lat[1:])
        else:
            out.append(lat)
        prev = ch
    return "".join(out)


def normalize(text: str) -> str:
    """Unify apostrophe variants (o‘, oʻ, o`) so search matches."""
    return _APOSTROPHES.sub("'", to_latin(text))
