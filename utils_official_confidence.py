# utils_official_confidence.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict
from urllib.parse import urlparse


# 你可以按需要扩展
SOURCE_WEIGHTS = {
    "wikidata_device(P856)": 1.0,
    "wikidata_manufacturer(P176->P856)": 0.8,
    "wikipedia_fallback": 0.6,
    "gsmarena_fallback": 0.5,
    "fallback_html": 0.5,
    "unknown": 0.3,
}

# 简单“可信域名”例子：你可以把它和 manufacturer/brand 绑定
TRUSTED_DOMAINS = {
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


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    # 有些 wiki 链接可能是 //example.com
    if url.startswith("//"):
        url = "https:" + url
    return url


def _get_domain(url: str) -> str:
    try:
        p = urlparse(url)
        return (p.netloc or "").lower()
    except Exception:
        return ""


def _domain_matches(domain: str, allowed: List[str]) -> bool:
    domain = domain.lower()
    for d in allowed:
        d = d.lower()
        if domain == d or domain.endswith("." + d):
            return True
    return False


@dataclass
class OfficialCandidate:
    url: str
    source: str  # e.g. wikidata_device(P856)
    ok: bool = True


def summarize_official_website(
    candidates: List[Dict],
    brand: Optional[str] = None,
) -> Dict[str, object]:
    """
    candidates: list of dict like:
      [{"url": "...", "source": "wikidata_device(P856)", "ok": True}, ...]
    brand: optional, used for domain whitelist scoring
    Returns:
      {"official_website": "...", "sources": [...], "confidence": "High|Medium|Low"}
    """
    parsed: List[OfficialCandidate] = []
    for c in candidates or []:
        url = _normalize_url(c.get("url"))
        if not url:
            continue
        parsed.append(
            OfficialCandidate(
                url=url,
                source=c.get("source") or "unknown",
                ok=bool(c.get("ok", True)),
            )
        )

    if not parsed:
        return {"official_website": "Unknown", "sources": [], "confidence": "Low"}

    # 选出“最可信”的一个：先看 source weight，再看域名是否匹配可信列表
    best = None
    best_score = -1.0
    best_sources = []

    allowed = TRUSTED_DOMAINS.get(brand, []) if brand else []
    for cand in parsed:
        if not cand.ok:
            continue

        w = SOURCE_WEIGHTS.get(cand.source, SOURCE_WEIGHTS["unknown"])
        domain = _get_domain(cand.url)

        # 域名加分（如果 brand 提供了）
        domain_bonus = 0.0
        if allowed and _domain_matches(domain, allowed):
            domain_bonus = 0.5
        elif allowed and not _domain_matches(domain, allowed):
            domain_bonus = -0.3  # 看起来不像官网域名，扣一点

        score = w + domain_bonus

        if score > best_score:
            best_score = score
            best = cand
            best_sources = [cand.source]

    if not best:
        return {"official_website": "Unknown", "sources": [], "confidence": "Low"}

    # 置信度规则（简单可解释）
    # High: device-level wikidata + domain match（或权重>=1.2）
    # Medium: manufacturer wikidata 或 fallback 但 domain match
    # Low: 只有 fallback 且 domain 不明确/没brand
    conf = "Low"
    if best_score >= 1.2:
        conf = "High"
    elif best_score >= 0.7:
        conf = "Medium"

    return {
        "official_website": best.url,
        "sources": best_sources,
        "confidence": conf,
    }