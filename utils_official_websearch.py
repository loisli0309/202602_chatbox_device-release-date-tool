# utils_official_websearch.py
import os
import re
import requests
from urllib.parse import urlparse
from typing import Optional, Dict, List


# Brand -> official domains (whitelist)
BRAND_DOMAINS = {
    "Samsung": ["samsung.com"],
    "Apple": ["apple.com"],
    "Google": ["store.google.com", "google.com"],
    "Xiaomi": ["mi.com", "xiaomi.com"],
    "OnePlus": ["oneplus.com"],
    "Sony": ["sony.com"],
    "Motorola": ["motorola.com"],
    "Huawei": ["huawei.com"],
    "Oppo": ["oppo.com"],
    "Vivo": ["vivo.com"],
}

# Exclude obvious non-official sites
BLOCKLIST = [
    "gsmarena.com", "wikipedia.org", "youtube.com", "amazon.", "bestbuy.",
    "reddit.com", "facebook.com", "instagram.com", "tiktok.com"
]


def guess_brand(device: str) -> Optional[str]:
    d = (device or "").strip().lower()
    if d.startswith("samsung"):
        return "Samsung"
    if d.startswith("iphone") or d.startswith("apple"):
        return "Apple"
    if d.startswith("google") or d.startswith("pixel"):
        return "Google"
    if d.startswith("xiaomi") or d.startswith("redmi") or d.startswith("poco"):
        return "Xiaomi"
    if d.startswith("oneplus"):
        return "OnePlus"
    if d.startswith("sony"):
        return "Sony"
    if d.startswith("motorola") or d.startswith("moto"):
        return "Motorola"
    if d.startswith("huawei"):
        return "Huawei"
    if d.startswith("oppo"):
        return "Oppo"
    if d.startswith("vivo"):
        return "Vivo"
    return None


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _domain_match(dom: str, allowed: List[str]) -> bool:
    dom = dom.lower()
    for d in allowed:
        d = d.lower()
        if dom == d or dom.endswith("." + d):
            return True
    return False


def serpapi_search(query: str, api_key: str, num: int = 10) -> List[Dict]:
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "api_key": api_key, "num": num},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("organic_results", [])[:num]


def _page_title(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        html = r.text[:200000]
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        return (m.group(1) if m else "").strip()
    except Exception:
        return ""


def find_official_site_chatgpt_style(device: str, verify_page: bool = True) -> Dict:
    """
    Returns:
      {
        "official_website": ".../Unknown",
        "sources": ["web_search","domain_whitelist",...],
        "confidence": "High|Medium|Low",
        "debug": {...}
      }
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return {
            "official_website": "Unknown",
            "sources": [],
            "confidence": "Low",
            "debug": {"error": "Missing SERPAPI_KEY environment variable"},
        }

    brand = guess_brand(device)
    allowed = BRAND_DOMAINS.get(brand, []) if brand else []

    queries = []
    if brand and allowed:
        queries.append(f'{device} site:{allowed[0]}')
    queries.append(f"{device} official site")
    queries.append(f"{device} official product page")

    tokens = [t for t in re.split(r"\s+", device.strip()) if t]
    model_tokens = tokens[-2:] if len(tokens) >= 2 else tokens  # light heuristic

    candidates = []
    for q in queries:
        for item in serpapi_search(q, api_key=api_key, num=10):
            url = item.get("link")
            title = item.get("title", "")
            if not url:
                continue
            dom = _domain(url)

            if any(b in dom for b in BLOCKLIST):
                continue

            score = 0
            if allowed and _domain_match(dom, allowed):
                score += 60
            elif brand and allowed:
                score -= 10

            low_url = url.lower()
            for t in model_tokens:
                if t.lower() in low_url:
                    score += 10

            verified = False
            page_title = ""
            if verify_page and score >= 40:
                page_title = _page_title(url)
                low_title = page_title.lower()
                if all(t.lower() in low_title for t in model_tokens if t):
                    verified = True
                    score += 15

            candidates.append(
                {
                    "url": url,
                    "title": title,
                    "domain": dom,
                    "score": score,
                    "verified": verified,
                    "page_title": page_title,
                    "query": q,
                }
            )

    if not candidates:
        return {"official_website": "Unknown", "sources": [], "confidence": "Low", "debug": {"brand": brand, "candidates": []}}

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    if best["score"] >= 75:
        conf = "High"
    elif best["score"] >= 50:
        conf = "Medium"
    else:
        conf = "Low"

    src = ["web_search"]
    if brand and allowed:
        src.append("domain_whitelist")
    if best["verified"]:
        src.append("page_title_verification")

    return {
        "official_website": best["url"],
        "sources": src,
        "confidence": conf,
        "debug": {"brand": brand, "top_candidate": best, "top5": candidates[:5]},
    }