# sources/gsmarena.py
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote
from typing import Optional, Dict, List

from config import HEADERS_WEB
from utils_text import clean_text, extract_date_like, norm_key

@st.cache_data(ttl=6 * 60 * 60)
def gsmarena_search_candidates(model: str, debug: bool = False) -> Optional[Dict]:
    q = quote(model.strip())
    search_url = f"https://www.gsmarena.com/results.php3?sQuickSearch=yes&sName={q}"

    try:
        r = requests.get(search_url, headers=HEADERS_WEB, timeout=15)
    except requests.RequestException as e:
        return {"source": "GSMArena", "error": f"search request failed: {e}", "search_url": search_url} if debug else None

    if r.status_code != 200:
        return {"source": "GSMArena", "error": f"search status_code={r.status_code}", "search_url": search_url} if debug else None

    soup = BeautifulSoup(r.text, "html.parser")
    makers = soup.select_one(".makers")
    if not makers:
        preview = clean_text(soup.get_text(" ", strip=True))[:200]
        return {"source": "GSMArena", "error": "no .makers found (blocked or changed)",
                "search_url": search_url, "preview": preview} if debug else None

    candidates = []
    for a in makers.select("a[href]"):
        href = a.get("href")
        if href and href.endswith(".php"):
            candidates.append({
                "name": clean_text(a.get_text(" ", strip=True)),
                "url": "https://www.gsmarena.com/" + href.lstrip("/")
            })

    if not candidates:
        return {"source": "GSMArena", "error": "no candidates found", "search_url": search_url} if debug else None

    return {"source": "GSMArena", "search_url": search_url, "candidates": candidates}

def pick_best_gsm_candidate(model: str, candidates: List[Dict]) -> Optional[str]:
    if not candidates:
        return None

    q = norm_key(model)
    want_plus = "plus" in q
    want_pro = "pro" in q
    want_ultra = "ultra" in q
    want_mini = "mini" in q
    want_max = "max" in q

    bad_tokens = []
    if not want_plus: bad_tokens.append("plus")
    if not want_pro: bad_tokens.append("pro")
    if not want_ultra: bad_tokens.append("ultra")
    if not want_mini: bad_tokens.append("mini")
    if not want_max: bad_tokens.append("max")

    for c in candidates:
        name = norm_key(c["name"])
        if q in name and not any(bt in name for bt in bad_tokens):
            return c["url"]

    for c in candidates:
        name = norm_key(c["name"])
        if q in name:
            return c["url"]

    return candidates[0]["url"]

@st.cache_data(ttl=6 * 60 * 60)
def fetch_gsmarena_from_detail_url(detail_url: str, debug: bool = False) -> Optional[Dict]:
    detail_url = detail_url.strip()
    if not detail_url:
        return None

    try:
        r = requests.get(detail_url, headers=HEADERS_WEB, timeout=15)
    except requests.RequestException as e:
        return {"source": "GSMArena", "error": f"detail request failed: {e}", "page": detail_url} if debug else None

    html = r.text or ""
    soup = BeautifulSoup(html, "html.parser")

    lower = html.lower()
    blocked = any(x in lower for x in ["cloudflare", "just a moment", "checking your browser", "captcha"])
    if blocked:
        return {
            "source": "GSMArena",
            "page": detail_url,
            "error": "Likely blocked (anti-bot / Cloudflare). requests did not receive real device HTML.",
            "status_code": r.status_code,
            "debug_title": soup.title.get_text(" ", strip=True) if soup.title else None,
            "debug_preview": clean_text(soup.get_text(" ", strip=True))[:300],
        } if debug else {"source": "GSMArena", "page": detail_url, "error": "blocked"}

    def get_spec(spec_name: str) -> Optional[str]:
        cell = soup.select_one(f'td[data-spec="{spec_name}"]')
        return clean_text(cell.get_text(" ", strip=True)) if cell else None

    status_text = get_spec("status")
    announced_text = get_spec("announced")

    return {
        "source": "GSMArena",
        "page": detail_url,
        "status": status_text,
        "announced": announced_text,
        "released_date": extract_date_like(status_text),
        "announced_date": extract_date_like(announced_text),
        "note": "Parsed from td[data-spec].",
    }