# sources/wikidata.py
import requests
from typing import Optional, Tuple, List, Dict
import streamlit as st

from config import HEADERS_WIKIDATA

def _wd_get_time_from_claims(claims: dict, prop: str) -> Optional[str]:
    try:
        arr = claims.get(prop) or []
        if not arr:
            return None
        time_val = arr[0]["mainsnak"]["datavalue"]["value"]["time"]
        return time_val.replace("+", "").split("T")[0]
    except Exception:
        return None

def _wd_first_time(claims: dict, props: List[str]) -> Tuple[Optional[str], Optional[str]]:
    for p in props:
        d = _wd_get_time_from_claims(claims, p)
        if d:
            return d, p
    return None, None

@st.cache_data(ttl=60 * 60)
def wikidata_lookup(device_name: str, debug: bool = False) -> Optional[Dict]:
    search_url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": device_name,
        "language": "en",
        "format": "json",
        "limit": 5
    }

    try:
        r = requests.get(search_url, params=params, headers=HEADERS_WIKIDATA, timeout=15)
    except Exception as e:
        return {"source": "Wikidata", "error": f"request failed: {e}"} if debug else None

    if r.status_code != 200:
        return {"source": "Wikidata", "error": f"status_code={r.status_code}", "url": r.url} if debug else None

    ctype = (r.headers.get("Content-Type") or "").lower()
    if "json" not in ctype:
        return {"source": "Wikidata", "error": f"unexpected content-type: {ctype}", "url": r.url,
                "preview": (r.text or "")[:200]} if debug else None

    try:
        data = r.json()
    except Exception as e:
        return {"source": "Wikidata", "error": f"json parse failed: {e}", "url": r.url,
                "preview": (r.text or "")[:200]} if debug else None

    results = data.get("search", [])
    if not results:
        return {"source": "Wikidata", "matched_entity": None, "raw": None,
                "announced_date": None, "released_date": None, "note": "No entity matched."}

    entity = results[0]
    qid = entity.get("id")
    label = entity.get("label")

    entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    try:
        r2 = requests.get(entity_url, headers=HEADERS_WIKIDATA, timeout=15)
    except Exception as e:
        return {"source": "Wikidata", "matched_entity": label, "raw": qid,
                "error": f"entity request failed: {e}"} if debug else None

    if r2.status_code != 200:
        return {"source": "Wikidata", "matched_entity": label, "raw": qid,
                "error": f"entity status_code={r2.status_code}", "page": entity_url} if debug else None

    try:
        entity_data = r2.json()
    except Exception as e:
        return {"source": "Wikidata", "matched_entity": label, "raw": qid,
                "error": f"entity json parse failed: {e}", "preview": (r2.text or "")[:200]} if debug else None

    claims = entity_data.get("entities", {}).get(qid, {}).get("claims", {})

    announced_date, announced_prop = _wd_first_time(claims, ["P6949", "P577", "P571", "P585"])
    released_date, released_prop = _wd_first_time(claims, ["P577", "P571"])
    best_date = announced_date or released_date

    return {
        "source": "Wikidata",
        "matched_entity": label,
        "raw": qid,
        "date": best_date,
        "announced_date": announced_date,
        "announced_prop": announced_prop,
        "released_date": released_date,
        "released_prop": released_prop,
        "note": "Primary date is announcement/introduced date from Wikidata; release/availability may be missing.",
    }