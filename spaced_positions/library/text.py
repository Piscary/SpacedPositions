"""Text folding for search and matching: case, accents and ß don't matter (`spiess` finds Spieß)."""

import re
import unicodedata


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).replace("ß", "ss").replace("ẞ", "ss"))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")[:90]
