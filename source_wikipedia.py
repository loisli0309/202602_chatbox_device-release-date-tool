# sources/wikipedia.py
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote
from typing import Optional, Dict

from config import HEADERS_WEB
from utils_text import clean_text, extract_date_like

@st.cache_data(ttl=60 * 60)
def fetch_wikipedia_release(model: str, debug: bool = False) -> Optional[Dict]:
    model = model.strip()
    if not model:
        return None

    try:
        url_guess = f"https://en.wikipedia.org/wiki/{quote(model.replace(' ', '_'))}"
        r = requests.get(url_guess, headers=HEADERS_WEB, timeout=15)
    except requests.RequestException as e:
        return {"source": "Wikipedia", "error": f"request failed: {e}"} if debug else None

    html = r.text if r.status_code == 200 else ""
    is_disambig = "may refer to" in html.lower() if html else False

    if r.status_code != 200 or is_disambig:
        search_url = f"https://en.wikipedia.org/w/index.php?search={quote(model)}"
        try:
            rs = requests.get(search_url, headers=HEADERS_WEB, timeout=15)
        except requests.RequestException as e:
            return {"source": "Wikipedia", "error": f"search request failed: {e}", "search_url": search_url} if debug else None

        if rs.status_code != 200:
            return {"source": "Wikipedia", "error": f"search status_code={rs.status_code}", "search_url": search_url} if debug else None

        soup_s = BeautifulSoup(rs.text, "html.parser")
        first = soup_s.select_one(".mw-search-results li .mw-search-result-heading a")
        if not first or not first.get("href"):
            return {"source": "Wikipedia", "error": "no search result found", "search_url": search_url} if debug else None

        url_guess = "https://en.wikipedia.org" + first["href"]
        r = requests.get(url_guess, headers=HEADERS_WEB, timeout=15)

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        infobox = soup.find("table", class_=lambda x: x and "infobox" in x)
        if not infobox:
            return {"source": "Wikipedia", "error": "infobox not found", "page": url_guess} if debug else None

        release_text = None
        for row in infobox.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            key = clean_text(th.get_text(" ", strip=True)).lower()
            if "release" in key or "first released" in key:
                release_text = clean_text(td.get_text(" ", strip=True))
                break

        if not release_text:
            return {"source": "Wikipedia", "error": "release date not found in infobox", "page": url_guess} if debug else None

        return {"source": "Wikipedia", "page": url_guess, "raw": release_text, "date": extract_date_like(release_text)}
    except Exception as e:
        return {"source": "Wikipedia", "error": f"parse failed: {e}", "page": url_guess, "preview": r.text[:300]} if debug else None