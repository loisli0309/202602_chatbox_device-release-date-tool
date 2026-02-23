# utils_text.py
import re
from typing import Optional

def norm_key(s: str) -> str:
    """lower + collapse inner spaces"""
    return " ".join((s or "").lower().split())

def clean_text(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "")).strip()

def extract_date_like(text: str) -> Optional[str]:
    if not text:
        return None
    t = clean_text(text)

    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        return m.group(1)

    m = re.search(r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b", t)
    if m:
        return m.group(1)

    m = re.search(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b", t)
    if m:
        return m.group(1)

    m = re.search(r"\b(19\d{2}|20\d{2}),\s*([A-Za-z]{3,9})(?:\s+(\d{1,2}))?\b", t)
    if m:
        year, mon, day = m.group(1), m.group(2), m.group(3)
        return f"{year}, {mon}" + (f" {day}" if day else "")

    m = re.search(r"\b(19\d{2}|20\d{2})\b", t)
    if m:
        return m.group(1)

    return None