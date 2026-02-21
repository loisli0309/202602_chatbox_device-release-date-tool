import re
import time
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote
from typing import Optional
from datetime import date, datetime

# =========================
# UI
# =========================
st.set_page_config(page_title="Phone Release Date Finder", page_icon="📱")
st.title("📱 Phone Release Date Finder (Wikidata / Wikipedia / GSMArena)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
}

device = st.text_input("Enter phone model (e.g., iPhone 15 / Samsung Galaxy S23)", "").strip()
debug_mode = st.checkbox("Debug mode (show detailed error info)", value=True)

# =========================
# Utils
# =========================
def clean_text(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "")).strip()

def extract_date_like(text: str) -> Optional[str]:
    """
    Extract a date-like string from free text (conservative).
    """
    if not text:
        return None
    t = clean_text(text)

    # 2023-09-22
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        return m.group(1)

    # September 22, 2023 / Sep 22, 2023
    m = re.search(r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b", t)
    if m:
        return m.group(1)

    # 22 September 2023
    m = re.search(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b", t)
    if m:
        return m.group(1)

    # 2023, September 22  (GSMArena often uses this)
    m = re.search(r"\b(19\d{2}|20\d{2}),\s*([A-Za-z]{3,9})(?:\s+(\d{1,2}))?\b", t)
    if m:
        year, mon, day = m.group(1), m.group(2), m.group(3)
        return f"{year}, {mon}" + (f" {day}" if day else "")

    # Year only
    m = re.search(r"\b(19\d{2}|20\d{2})\b", t)
    if m:
        return m.group(1)

    return None

def get_with_backoff(url: str, headers: dict, timeout: int = 15, retries: int = 3) -> requests.Response:
    """
    Friendly retry for 429 rate limits.
    """
    last = None
    for i in range(retries):
        last = requests.get(url, headers=headers, timeout=timeout)
        if last.status_code != 429:
            return last
        time.sleep(2 ** i)  # 1s, 2s, 4s
    return last

# =========================
# Source 1: Wikidata (safe)
# =========================
import requests

HEADERS = {
    "User-Agent": "PhoneReleaseDateFinder/1.0 (contact: your-email@example.com)"
}

def wikidata_lookup(device_name: str, debug: bool = False):
    search_url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": device_name,
        "language": "en",
        "format": "json",
        "limit": 5
    }

    try:
        r = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
    except Exception as e:
        return {"source": "Wikidata", "error": f"request failed: {e}"} if debug else None

    # ✅ check status code first
    if r.status_code != 200:
        return {
            "source": "Wikidata",
            "error": f"status_code={r.status_code}",
            "url": r.url
        } if debug else None

    # ✅ check content type (sometimes HTML is returned)
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "json" not in ctype:
        return {
            "source": "Wikidata",
            "error": f"unexpected content-type: {ctype}",
            "url": r.url,
            "preview": (r.text or "")[:200]
        } if debug else None

    try:
        data = r.json()
    except Exception as e:
        return {
            "source": "Wikidata",
            "error": f"json parse failed: {e}",
            "url": r.url,
            "preview": (r.text or "")[:200]
        } if debug else None

    results = data.get("search", [])
    if not results:
        return {
            "source": "Wikidata",
            "matched_entity": None,
            "raw": None,
            "date": None,
            "property": None,
            "note": "No entity matched on Wikidata search."
        }

    entity = results[0]
    qid = entity.get("id")
    label = entity.get("label")

    # Fetch entity JSON
    entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    try:
        r2 = requests.get(entity_url, headers=HEADERS, timeout=15)
    except Exception as e:
        return {"source": "Wikidata", "matched_entity": label, "raw": qid, "error": f"entity request failed: {e}"} if debug else None

    if r2.status_code != 200:
        return {"source": "Wikidata", "matched_entity": label, "raw": qid, "error": f"entity status_code={r2.status_code}", "page": entity_url} if debug else None

    try:
        entity_data = r2.json()
    except Exception as e:
        return {"source": "Wikidata", "matched_entity": label, "raw": qid, "error": f"entity json parse failed: {e}", "preview": (r2.text or "")[:200]} if debug else None

    claims = entity_data.get("entities", {}).get(qid, {}).get("claims", {})

    raw_time = None
    prop_used = None
    if "P577" in claims and claims["P577"]:
        raw_time = claims["P577"][0]["mainsnak"]["datavalue"]["value"]["time"]
        prop_used = "P577"
    elif "P571" in claims and claims["P571"]:
        raw_time = claims["P571"][0]["mainsnak"]["datavalue"]["value"]["time"]
        prop_used = "P571"

    date_only = None
    if raw_time:
        date_only = raw_time.replace("+", "").split("T")[0]

    return {
        "source": "Wikidata",
        "matched_entity": label,
        "raw": qid,
        "date": date_only,
        "property": prop_used,
    }

# =========================
# Source 2: Wikipedia (safe)
# =========================
@st.cache_data(ttl=60 * 60)
def fetch_wikipedia_release(model: str, debug: bool = False):
    model = model.strip()
    if not model:
        return None

    try:
        url_guess = f"https://en.wikipedia.org/wiki/{quote(model.replace(' ', '_'))}"
        r = requests.get(url_guess, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        return {"source": "Wikipedia", "error": f"request failed: {e}"} if debug else None

    html = r.text if r.status_code == 200 else ""
    is_disambig = "may refer to" in html.lower() if html else False

    if r.status_code != 200 or is_disambig:
        search_url = f"https://en.wikipedia.org/w/index.php?search={quote(model)}"
        try:
            rs = requests.get(search_url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            return {"source": "Wikipedia", "error": f"search request failed: {e}", "search_url": search_url} if debug else None

        if rs.status_code != 200:
            return {"source": "Wikipedia", "error": f"search status_code={rs.status_code}", "search_url": search_url} if debug else None

        soup_s = BeautifulSoup(rs.text, "html.parser")
        first = soup_s.select_one(".mw-search-results li .mw-search-result-heading a")
        if not first or not first.get("href"):
            return {"source": "Wikipedia", "error": "no search result found", "search_url": search_url} if debug else None

        url_guess = "https://en.wikipedia.org" + first["href"]
        try:
            r = requests.get(url_guess, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            return {"source": "Wikipedia", "error": f"page request failed: {e}", "page": url_guess} if debug else None

        if r.status_code != 200:
            return {"source": "Wikipedia", "error": f"page status_code={r.status_code}", "page": url_guess} if debug else None

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

        return {
            "source": "Wikipedia",
            "page": url_guess,
            "raw": release_text,
            "date": extract_date_like(release_text),
        }
    except Exception as e:
        return {"source": "Wikipedia", "error": f"parse failed: {e}", "page": url_guess, "preview": r.text[:300]} if debug else None

# =========================
# Source 3: GSMArena (DIRECT detail page)
# =========================
@st.cache_data(ttl=6 * 60 * 60)
def fetch_gsmarena_from_detail_url(detail_url: str, debug: bool = False):
    """
    Directly fetch GSMArena device detail page (NO search page).
    Parses Status / Announced.
    """
    detail_url = detail_url.strip()
    if not detail_url:
        return None

    try:
        r = requests.get(detail_url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        return {"source": "GSMArena", "error": f"detail request failed: {e}", "page": detail_url} if debug else None

    if r.status_code == 429:
        return {"source": "GSMArena", "error": "Rate limited (429) on detail page.", "status_code": 429, "page": detail_url} if debug else None
    if r.status_code != 200:
        return {"source": "GSMArena", "error": f"detail status_code={r.status_code}", "page": detail_url} if debug else None

    soup = BeautifulSoup(r.text, "html.parser")

    status_text = None
    announced_text = None

    for row in soup.select("table tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue

        key = th.get_text(" ", strip=True)
        val = clean_text(td.get_text(" ", strip=True))

        if key == "Status":
            status_text = val
        elif key == "Announced":
            announced_text = val

        if status_text and announced_text:
            break

    return {
        "source": "GSMArena",
        "page": detail_url,
        "raw": {"Status": status_text, "Announced": announced_text},
        "date": extract_date_like(status_text) or extract_date_like(announced_text),
    }


# Optional: a small local mapping (avoid search page completely)
GSMA_DETAIL_URLS = {
    "iphone 15": "https://www.gsmarena.com/apple_iphone_15-12559.php",
    # add more models over time...
}

def fetch_gsmarena_direct(model: str, debug: bool = False):
    key = model.lower().strip()
    url = GSMA_DETAIL_URLS.get(key)
    if not url:
        return {"source": "GSMArena", "error": "No cached detail URL for this model. Paste a detail URL below to fetch.", "model_key": key} if debug else None
    return fetch_gsmarena_from_detail_url(url, debug=debug)


# =========================
# Helper
# =========================
def pick_best_release_date(wd, wk, gs):
    if wd and isinstance(wd, dict) and wd.get("date"):
        return wd["date"], "Wikidata"
    if wk and isinstance(wk, dict) and wk.get("date"):
        return wk["date"], "Wikipedia"
    if gs and isinstance(gs, dict) and gs.get("date"):
        return gs["date"], "GSMArena"
    return None, None


# =========================
# UI controls
# =========================
enable_gsm = st.checkbox("Also query GSMArena (direct detail page)", value=False)

gsm_detail_url = st.text_input(
    "GSMArena detail URL (paste one if not cached):",
    placeholder="e.g., https://www.gsmarena.com/apple_iphone_15-12559.php"
)

if st.button("Search") and device:
    with st.spinner("Fetching data..."):
        wd = wikidata_lookup(device, debug=debug_mode)
        wk = fetch_wikipedia_release(device, debug=debug_mode)

        gs = None
        used_detail_url = None

        if enable_gsm:
            # 1) try cached mapping
            key = device.lower().strip()
            used_detail_url = GSMA_DETAIL_URLS.get(key)

            # 2) if no cached URL, use user pasted URL
            if not used_detail_url and gsm_detail_url.strip():
                used_detail_url = gsm_detail_url.strip()

            # 3) fetch if we have a detail URL
            if used_detail_url:
                gs = fetch_gsmarena_from_detail_url(used_detail_url, debug=debug_mode)

    st.subheader("📦 Structured Results")
    st.json({"device": device, "wikidata": wd, "wikipedia": wk, "gsmarena": gs})

    # ✅ always print what detail URL was used / expected
    if enable_gsm:
        if used_detail_url:
            st.markdown(f"🔗 GSMArena detail page (used): [{used_detail_url}]({used_detail_url})")
        else:
            st.warning("GSMArena enabled, but no detail URL available. Paste a GSMArena detail URL above or add it to GSMA_DETAIL_URLS.")