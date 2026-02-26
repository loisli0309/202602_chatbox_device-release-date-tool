
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import re
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter

# --------- date parsing helpers ----------

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

@dataclass(frozen=True)
class NormalizedDate:
    # granularity: "day" | "month" | "year"
    granularity: str
    year: int
    month: Optional[int] = None
    day: Optional[int] = None

    def key(self) -> str:
        if self.granularity == "day":
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.granularity == "month":
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"

    def display(self) -> str:
        if self.granularity == "day":
            return date(self.year, self.month, self.day).strftime("%b %d, %Y")
        if self.granularity == "month":
            # fake a day for display
            return date(self.year, self.month, 1).strftime("%b %Y")
        return str(self.year)

def _try_parse_iso(s: str) -> Optional[NormalizedDate]:
    # 2023-09-12 / 2023-09 / 2023
    s = s.strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return NormalizedDate("day", y, mo, d)
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        y, mo = map(int, m.groups())
        return NormalizedDate("month", y, mo, None)
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return NormalizedDate("year", int(m.group(1)), None, None)
    return None

def _try_parse_textual(s: str) -> Optional[NormalizedDate]:
    """
    Handles:
      - Sep 2023 / September 2023
      - Sep 12 2023 / September 12, 2023
      - 12 Sep 2023 / 12 September 2023
      - 2023 (year)
    """
    s0 = s.strip().lower()
    s0 = s0.replace(",", " ")
    s0 = re.sub(r"\s+", " ", s0)

    # year only
    m = re.search(r"\b(19\d{2}|20\d{2})\b", s0)
    year = int(m.group(1)) if m else None

    # Month name present?
    month = None
    for k, v in _MONTHS.items():
        if re.search(rf"\b{k}\b", s0):
            month = v
            break

    # Day number (1-31)
    day = None
    dm = re.search(r"\b([0-2]?\d|3[0-1])\b", s0)
    if dm:
        d = int(dm.group(1))
        # avoid picking the year as day
        if d <= 31:
            day = d

    if year and month and day:
        # Need to ensure day isn't actually the year token; crude but ok
        # If the string starts with year, prefer month granularity unless day clearly positioned
        return NormalizedDate("day", year, month, day)

    if year and month:
        return NormalizedDate("month", year, month, None)

    if year:
        return NormalizedDate("year", year, None, None)

    return None

def normalize_date(raw: Any) -> Optional[NormalizedDate]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return _try_parse_iso(s) or _try_parse_textual(s)

# --------- scoring / consensus ----------

SOURCE_WEIGHTS = {
    "GSMArena": 0.45,
    "Wikidata": 0.35,
    "Wikipedia": 0.20,
}

def choose_consensus(results: List[Tuple[str, NormalizedDate]]) -> Tuple[Optional[NormalizedDate], str, List[str]]:
    """
    results: list of (source_name, normalized_date)
    Returns: (chosen_date, confidence, supporting_sources)
    """
    if not results:
        return None, "Low", []

    # vote by month-level key first (more forgiving), then day-level
    # Create two keys for each: day_key and month_key
    month_votes = Counter()
    day_votes = Counter()
    month_support = {}
    day_support = {}

    for src, nd in results:
        w = SOURCE_WEIGHTS.get(src, 0.15)
        # month key: if day present, convert to month
        if nd.granularity == "day":
            mk = f"{nd.year:04d}-{nd.month:02d}"
            dk = nd.key()
        elif nd.granularity == "month":
            mk = nd.key()
            dk = None
        else:
            mk = nd.key()  # year
            dk = None

        month_votes[mk] += w
        month_support.setdefault(mk, []).append(src)

        if dk:
            day_votes[dk] += w
            day_support.setdefault(dk, []).append(src)

    # Prefer strongest day consensus if 2+ sources agree on same day
    if day_votes:
        best_day, best_day_w = day_votes.most_common(1)[0]
        if len(day_support.get(best_day, [])) >= 2:
            # pick a representative ND from that key
            y, m, d = map(int, best_day.split("-"))
            chosen = NormalizedDate("day", y, m, d)
            return chosen, "High", sorted(day_support[best_day])

    # Then month/year consensus
    best_mk, best_mw = month_votes.most_common(1)[0]
    supporters = month_support.get(best_mk, [])
    # determine chosen ND granularity from key
    if re.fullmatch(r"\d{4}-\d{2}", best_mk):
        y, m = map(int, best_mk.split("-"))
        chosen = NormalizedDate("month", y, m, None)
        if len(supporters) >= 2:
            return chosen, "High", sorted(set(supporters))
        # single source month-level
        return chosen, "Medium", sorted(set(supporters))

    if re.fullmatch(r"\d{4}", best_mk):
        chosen = NormalizedDate("year", int(best_mk), None, None)
        if len(supporters) >= 2:
            return chosen, "Medium", sorted(set(supporters))
        return chosen, "Low", sorted(set(supporters))

    return None, "Low", []

def summarize_release(sources_payload: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    sources_payload: list like:
      [{"name":"Wikidata","ok":True,"release_date":"2023-09-12"}, ...]
    Returns:
      {"release_date":"Sep 2023", "sources":["Wikidata","GSMArena"], "confidence":"High"}
    """
    parsed: List[Tuple[str, NormalizedDate]] = []
    for s in sources_payload:
        name = s.get("name") or s.get("source") or "Unknown"
        if not s.get("ok", True):
            continue
        raw = s.get("release_date") or s.get("date") or s.get("release")
        nd = normalize_date(raw)
        if nd:
            parsed.append((name, nd))

    chosen, conf, supporters = choose_consensus(parsed)
    if not chosen:
        return {"release_date": "Unknown", "sources": [], "confidence": "Low"}

    return {
        "release_date": chosen.display(),
        "sources": supporters,
        "confidence": conf,
    }