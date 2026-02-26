# app_main.py
import os
import sys
import streamlit as st
from typing import Optional, List, Dict

# ensure project root import works
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from source_wikidata import wikidata_lookup
from source_wikipedia import fetch_wikipedia_release
from sources_gsmarena import (
    gsmarena_search_candidates,
    pick_best_gsm_candidate,
    fetch_gsmarena_from_detail_url,
)

from utils_confidence import summarize_release
from utils_official_websearch import find_official_site_chatgpt_style

# Optional mapping config
try:
    from config import GSMA_DETAIL_URLS
except Exception:
    GSMA_DETAIL_URLS = {}

try:
    from utils_text import norm_key
except Exception:
    norm_key = None


def safe_get(d: dict, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


def compute_final_date(wd: dict, wk: dict, gs: dict) -> Optional[str]:
    return (
        safe_get(gs, "released_date", "release_date")
        or safe_get(wk, "date")
        or safe_get(gs, "announced_date")
        or safe_get(wd, "released_date", "release_date")
        or safe_get(wd, "announced_date")
    )


def build_sources_payload(last_results: dict) -> List[Dict]:
    payload: List[Dict] = []
    sources = (last_results or {}).get("sources", {})

    for key, name in [("wikidata", "Wikidata"), ("wikipedia", "Wikipedia"), ("gsmarena", "GSMArena")]:
        src = sources.get(key)
        if not isinstance(src, dict):
            continue
        raw_date = safe_get(src, "release_date", "released_date", "date", "released", "announced_date")
        payload.append({"name": name, "ok": bool(src.get("ok", True)) and bool(raw_date), "release_date": raw_date})
    return payload


# UI
st.set_page_config(page_title="Phone Release Date Finder", page_icon="📱")
st.title("📱 Phone Release Date Finder (Wikidata / Wikipedia / GSMArena + ChatGPT-style Official Website)")

device = st.text_input("Enter phone model (e.g., iPhone 15 / Samsung Galaxy S23)", "").strip()
debug_mode = st.checkbox("Debug mode", value=True)

enable_gsm = st.checkbox("Also query GSMArena", value=True)
auto_find_gsm = st.checkbox("Auto-find GSMArena detail page", value=True, disabled=not enable_gsm)

verify_official_page = st.checkbox("Verify official page title (slower, higher confidence)", value=True)

# session state
if "last_device" not in st.session_state:
    st.session_state["last_device"] = ""
if "gsm_candidates" not in st.session_state:
    st.session_state["gsm_candidates"] = None
if "last_results" not in st.session_state:
    st.session_state["last_results"] = None
if "used_detail_url" not in st.session_state:
    st.session_state["used_detail_url"] = None

if device and device != st.session_state["last_device"]:
    st.session_state["last_device"] = device
    st.session_state["gsm_candidates"] = None
    st.session_state["used_detail_url"] = None

run_search = st.button("Search", type="primary", disabled=not bool(device))

if run_search and device:
    with st.spinner("Fetching sources..."):
        wd = wikidata_lookup(device, debug=debug_mode)
        wk = fetch_wikipedia_release(device, debug=debug_mode)

        gs = None
        used_detail_url = None

        if enable_gsm:
            res = gsmarena_search_candidates(device, debug=debug_mode)

            if isinstance(res, dict) and res.get("error"):
                gs = res
            elif isinstance(res, dict) and res.get("candidates"):
                candidates = res["candidates"]
                st.session_state["gsm_candidates"] = candidates

                if auto_find_gsm:
                    used_detail_url = pick_best_gsm_candidate(device, candidates)
                    if used_detail_url:
                        gs = fetch_gsmarena_from_detail_url(used_detail_url, debug=debug_mode)
                        if isinstance(gs, dict):
                            gs["_used_detail_url"] = used_detail_url
                else:
                    if GSMA_DETAIL_URLS and norm_key is not None:
                        key = norm_key(device)
                        mapped = GSMA_DETAIL_URLS.get(key)
                        if mapped:
                            used_detail_url = mapped
                            gs = fetch_gsmarena_from_detail_url(mapped, debug=debug_mode)
                            if isinstance(gs, dict):
                                gs["_used_detail_url"] = mapped

        final_date = compute_final_date(wd or {}, wk or {}, gs or {})

        st.session_state["last_results"] = {
            "device": device,
            "final_date_recommended": final_date,
            "sources": {"wikidata": wd, "wikipedia": wk, "gsmarena": gs},
        }
        st.session_state["used_detail_url"] = used_detail_url


results = st.session_state.get("last_results")
if results:
    # Release summary
    st.subheader("✅ Release Date Summary")
    sources_payload = build_sources_payload(results)
    summary = summarize_release(sources_payload)
    st.markdown(f"**Release date:** {summary['release_date']}")
    st.markdown(f"**Sources:** {', '.join(summary['sources']) if summary['sources'] else 'N/A'}")
    st.markdown(f"**Confidence:** {summary['confidence']}")

    st.divider()

    # Official website (ChatGPT-style)
    st.subheader("🌐 Official Website Summary (ChatGPT-style)")
    official = find_official_site_chatgpt_style(results["device"], verify_page=verify_official_page)

    st.markdown(f"**Official website:** {official['official_website']}")
    st.markdown(f"**Sources:** {', '.join(official['sources']) if official['sources'] else 'N/A'}")
    st.markdown(f"**Confidence:** {official['confidence']}")

    with st.expander("Debug: official search"):
        st.json(official.get("debug", {}))

    st.divider()
    st.subheader("📦 Structured Results")
    st.json(results)


# Manual GSMArena picker
if enable_gsm and st.session_state.get("gsm_candidates"):
    st.divider()
    st.subheader("🔎 GSMArena candidates (manual pick)")

    options = st.session_state["gsm_candidates"]
    labels = [f'{c.get("name")}  —  {c.get("url")}' for c in options]
    choice = st.selectbox("Select a GSMArena detail page", labels)
    chosen_url = options[labels.index(choice)].get("url")

    if st.button("Fetch GSMArena from selected page"):
        with st.spinner("Fetching GSMArena detail page..."):
            gs2 = fetch_gsmarena_from_detail_url(chosen_url, debug=debug_mode)
            if isinstance(gs2, dict):
                gs2["_used_detail_url"] = chosen_url

        if st.session_state.get("last_results"):
            st.session_state["last_results"]["sources"]["gsmarena"] = gs2

            wd = st.session_state["last_results"]["sources"].get("wikidata") or {}
            wk = st.session_state["last_results"]["sources"].get("wikipedia") or {}
            st.session_state["last_results"]["final_date_recommended"] = compute_final_date(wd, wk, gs2)

            st.session_state["used_detail_url"] = chosen_url

        st.success("Updated GSMArena source from selected page.")