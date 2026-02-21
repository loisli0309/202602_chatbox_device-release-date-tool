# orchestrator.py
import re
import time
import random
from typing import Dict, Any, List, Optional

#from sources_gsmarena import gsmarena_release_date
from sources_gsmarena import search_gsmarena
#from sources_gsmarena import gsmarena_release 


# ---------------------------
# Helpers
# ---------------------------
def _normalize_device(device: str) -> str:
    d = (device or "").strip()
    d = re.sub(r"\s+", " ", d)

    # normalize iphone15 -> iphone 15
    d = re.sub(r"(iphone)\s*(\d+)", r"\1 \2", d, flags=re.I)
    d = re.sub(r"(pixel)\s*(\d+)", r"\1 \2", d, flags=re.I)
    d = re.sub(r"(galaxy\s*s)\s*(\d+)", r"\1 \2", d, flags=re.I)

    return d.lower().strip()


def _sleep_jitter(min_s=0.4, max_s=1.0):
    time.sleep(random.uniform(min_s, max_s))


def _pick_best_result(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Prefer:
      availability (Released found) > announcement > not_released > None
    """
    priority = {"availability": 3, "announcement": 2, "not_released": 1, None: 0}
    if not results:
        return None
    results_sorted = sorted(results, key=lambda r: priority.get(r.get("type"), 0), reverse=True)
    best = results_sorted[0]
    return best


# ---------------------------
# Public API used by Streamlit
# ---------------------------
def lookup(device: str) -> Dict[str, Any]:
    """
    Main entry:
    - call GSMArena extractor with retries
    - return unified schema for Streamlit
    """
    device_norm = _normalize_device(device)

    debug = {
        "device": device_norm,
        "sources": [],
    }

    # Retry wrapper to reduce 429 failures
    last_err = None
    result = None

    for attempt in range(3):
        try:
            # IMPORTANT: keep the number of pages small to avoid 429
            # top_k is backward-compatible if your sources_gsmarena supports it;
            # if not, change to top_k_pages=3 there.
            result = search_gsmarena(device)

            debug["sources"].append({"name": "GSMArena", "ok": True})
            last_err = None
            break
        except Exception as e:
            last_err = str(e)
            debug["sources"].append({"name": "GSMArena", "ok": False, "error": last_err, "attempt": attempt + 1})
            _sleep_jitter(1.0, 2.5)

    if last_err and not result:
        return {
            "device": device_norm,
            "global_release": None,
            "picked_from": None,
            "conflicts": [],
            "debug": debug,
            "error": last_err,
        }

    # Map GSMArena fields into your UI schema
    date_value = result.get("date")
    typ = result.get("type")
    url = result.get("url")
    evidence = result.get("evidence")

    # "global_release" in your demo = best available signal from sources
    # availability: Released date (from Status or Released row)
    # announcement: Announced date
    # not_released: no date, but we show status evidence
    if typ == "availability":
        global_release = date_value
    elif typ == "announcement":
        global_release = date_value
    else:
        global_release = None

    picked_from = None
    if url or evidence:
        picked_from = {
            "source": "GSMArena",
            "url": url,
            "evidence": evidence,
            "type": typ,
        }

    # Put everything helpful into debug for Streamlit expander
    debug["gsmarena_top_urls"] = result.get("tried_urls", [])
    debug["gsmarena_tried_queries"] = result.get("tried_queries", [])
    debug["gsmarena_debug_search"] = result.get("debug_search", {})
    debug["gsmarena_matched_page_name"] = result.get("matched_page_name", None)

    return {
        "device": device_norm,
        "global_release": global_release,
        "picked_from": picked_from,
        "conflicts": [],
        "debug": debug,
        "error": None,
    }