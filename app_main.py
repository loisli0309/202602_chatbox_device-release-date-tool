# app_main.py
import os
import sys
import streamlit as st

# ✅ ensure project root import works no matter where you run streamlit
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from source_wikidata import wikidata_lookup
from source_wikipedia import fetch_wikipedia_release

# ✅ use your existing GSMArena functions (no gsmarena_lookup needed)
from sources_gsmarena import (
    gsmarena_search_candidates,
    pick_best_gsm_candidate,
    fetch_gsmarena_from_detail_url,
)

# optional mapping config
try:
    from config import GSMA_DETAIL_URLS
except Exception:
    GSMA_DETAIL_URLS = {}

# norm_key is used for mapping lookups
try:
    from utils_text import norm_key
except Exception:
    norm_key = None

# =========================
# UI
# =========================
st.set_page_config(page_title="Phone Release Date Finder", page_icon="📱")
st.title("📱 Phone Release Date Finder (Wikidata / Wikipedia / GSMArena)")

device = st.text_input("Enter phone model (e.g., iPhone 15 / Samsung Galaxy S23)", "").strip()
debug_mode = st.checkbox("Debug mode (show detailed error info)", value=True)

enable_gsm = st.checkbox("Also query GSMArena", value=True)
auto_find_gsm = st.checkbox(
    "Auto-find GSMArena detail page (no manual URL)",
    value=True,
    disabled=not enable_gsm,
)

# =========================
# Session state init
# =========================
if "last_device" not in st.session_state:
    st.session_state["last_device"] = ""
if "gsm_candidates" not in st.session_state:
    st.session_state["gsm_candidates"] = None
if "last_results" not in st.session_state:
    st.session_state["last_results"] = None
if "used_detail_url" not in st.session_state:
    st.session_state["used_detail_url"] = None

# Reset candidates when device changes
if device != st.session_state["last_device"]:
    st.session_state["last_device"] = device
    st.session_state["gsm_candidates"] = None

# =========================
# Main search
# =========================
if st.button("Search") and device:
    with st.spinner("Fetching data..."):
        wd = wikidata_lookup(device, debug=debug_mode)
        wk = fetch_wikipedia_release(device, debug=debug_mode)

        gs = None
        used_detail_url = None

        if enable_gsm:
            # 1) search candidates
            res = gsmarena_search_candidates(device, debug=debug_mode)

            # if blocked / request failed, your function returns {"error": ...} (when debug=True)
            if isinstance(res, dict) and res.get("error"):
                gs = res

            # normal path: candidates found
            elif isinstance(res, dict) and res.get("candidates"):
                candidates = res["candidates"]
                st.session_state["gsm_candidates"] = candidates

                # 2) auto pick best
                if auto_find_gsm:
                    used_detail_url = pick_best_gsm_candidate(device, candidates)
                    if used_detail_url:
                        gs = fetch_gsmarena_from_detail_url(used_detail_url, debug=debug_mode)
                        if isinstance(gs, dict):
                            gs["_used_detail_url"] = used_detail_url
                else:
                    # auto-find is OFF: try mapping dict if available
                    if GSMA_DETAIL_URLS and norm_key is not None:
                        key = norm_key(device)
                        mapped_url = GSMA_DETAIL_URLS.get(key)
                        if mapped_url:
                            used_detail_url = mapped_url
                            gs = fetch_gsmarena_from_detail_url(mapped_url, debug=debug_mode)
                            if isinstance(gs, dict):
                                gs["_used_detail_url"] = mapped_url

        # ✅ choose best final date
        final_date = (
            (gs or {}).get("released_date")
            or (wk or {}).get("date")
            or (gs or {}).get("announced_date")
            or (wd or {}).get("released_date")
            or (wd or {}).get("announced_date")
        )

        st.session_state["last_results"] = {
            "device": device,
            "final_date_recommended": final_date,
            "sources": {
                "wikidata": wd,
                "wikipedia": wk,
                "gsmarena": gs,
            },
        }
        st.session_state["used_detail_url"] = used_detail_url

# =========================
# Display results
# =========================
if st.session_state.get("last_results"):
    st.subheader("📦 Structured Results")
    st.json(st.session_state["last_results"])

    results = st.session_state["last_results"]
    sources = results.get("sources", {})

    wd = sources.get("wikidata") or {}
    wk = sources.get("wikipedia") or {}
    gs = sources.get("gsmarena") or {}

    st.subheader("🗓️ Dates (by source)")
    st.write(
        {
            "Final_recommended": results.get("final_date_recommended"),
            "Wikidata_announced": wd.get("announced_date"),
            "Wikidata_released": wd.get("released_date"),
            "Wikipedia_date": wk.get("date"),
            "Wikipedia_raw": wk.get("raw"),
            "Wikipedia_page": wk.get("page"),
            "GSMArena_announced": gs.get("announced_date"),
            "GSMArena_released": gs.get("released_date"),
        }
    )

    used_detail_url = st.session_state.get("used_detail_url")
    if enable_gsm and used_detail_url:
        st.markdown(f"🔗 GSMArena detail page (used): [{used_detail_url}]({used_detail_url})")

# =========================
# Candidate picker (only if candidates exist)
# =========================
if enable_gsm and st.session_state.get("gsm_candidates"):
    st.subheader("🔎 GSMArena candidates (choose one if auto-pick failed)")

    options = st.session_state["gsm_candidates"]
    labels = [f'{c["name"]}  —  {c["url"]}' for c in options]

    choice = st.selectbox("Select a GSMArena detail page", labels)
    chosen_url = options[labels.index(choice)]["url"]

    if st.button("Fetch GSMArena from selected page"):
        with st.spinner("Fetching GSMArena detail page..."):
            gs2 = fetch_gsmarena_from_detail_url(chosen_url, debug=debug_mode)

        if st.session_state.get("last_results"):
            st.session_state["last_results"]["sources"]["gsmarena"] = gs2
            st.session_state["used_detail_url"] = chosen_url

        st.json({"gsmarena_selected": gs2})
        st.markdown(f"🔗 Selected GSMArena detail page: [{chosen_url}]({chosen_url})")