from __future__ import annotations

import re
import unicodedata


_DASHES = "‐‑‒–—―−"
_UA_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d",
    "е": "e", "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i",
    "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "ъ": "", "ы": "y",
    "э": "e",
}


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = value.replace("\u00a0", " ")
    for dash in _DASHES:
        value = value.replace(dash, "-")
    value = re.sub(r"(?<=\d),(?=\d)", ".", value)
    value = re.sub(r"\b(?:No\.?|N)\s*(?=\d)", "№", value, flags=re.IGNORECASE)
    value = re.sub(r"№\s+", "№", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def slugify_ua(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    out: list[str] = []
    for ch in value:
        low = ch.lower()
        if low in _UA_MAP:
            piece = _UA_MAP[low]
            if ch.isupper() and piece:
                piece = piece[0].upper() + piece[1:]
            out.append(piece)
        elif ch.isascii() and (ch.isalnum() or ch in "-_ "):
            out.append(ch)
        else:
            out.append("-")
    ascii_value = "".join(out).upper()
    ascii_value = re.sub(r"[^A-Z0-9]+", "-", ascii_value)
    return ascii_value.strip("-")
