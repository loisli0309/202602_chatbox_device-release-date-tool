import re
import time
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional, List
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class DeviceRecord:
    raw_query: str
    source_name: str
    source_device_id: Optional[str]
    canonical_device_name: Optional[str]
    brand: Optional[str]
    model_numbers: Optional[str]
    source_device_url: Optional[str]
    release_date_raw: Optional[str]
    release_date_iso: Optional[str]
    internal_device_id: Optional[str]


class GSMArenaScraper:
    def __init__(self, timeout: int = 20, sleep_seconds: float = 1.0):
        self.base_url = "https://www.gsmarena.com/"
        self.search_url = "https://www.gsmarena.com/results.php3?sQuickSearch=yes&sName={query}"
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _get_html(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        time.sleep(self.sleep_seconds)
        return response.text

    def search(self, device_name: str) -> List[dict]:
        url = self.search_url.format(query=quote(device_name))
        html = self._get_html(url)
        soup = BeautifulSoup(html, "html.parser")

        candidates = []

        for a in soup.select("a[href$='.php']"):
            href = a.get("href", "").strip()
            if not href:
                continue

            # 设备详情页通常长这样：
            # apple_iphone_15_pro_max-12548.php
            if "-" not in href:
                continue

            skip_keywords = ["results.php3", "compare.php3", "news", "reviews", "blog"]
            if any(k in href.lower() for k in skip_keywords):
                continue

            full_url = urljoin(self.base_url, href)

            name = a.get_text(" ", strip=True)
            if not name:
                img = a.find("img")
                if img and img.get("title"):
                    name = img.get("title", "").strip()

            if not name:
                name = self._slug_to_name(href)

            candidates.append(
                {
                    "name": name,
                    "url": full_url,
                    "source_device_id": href.replace(".php", ""),
                }
            )

        # 去重
        dedup = {}
        for item in candidates:
            dedup[item["url"]] = item

        return list(dedup.values())

    def pick_best_candidate(self, raw_query: str, candidates: List[dict]) -> Optional[dict]:
        if not candidates:
            return None

        query_norm = self._normalize_name(raw_query)

        best = None
        best_score = -1

        for c in candidates:
            name_norm = self._normalize_name(c["name"])
            score = 0

            if name_norm == query_norm:
                score += 100
            if query_norm in name_norm:
                score += 30
            if name_norm in query_norm:
                score += 20

            query_tokens = set(query_norm.split())
            name_tokens = set(name_norm.split())
            score += len(query_tokens & name_tokens) * 5

            if score > best_score:
                best_score = score
                best = c

        return best

    def parse_device_page(self, device_url: str, raw_query: str = "") -> DeviceRecord:
        html = self._get_html(device_url)
        soup = BeautifulSoup(html, "html.parser")

        canonical_device_name = self._extract_device_name(soup)
        source_device_id = self._extract_source_device_id(device_url)
        brand = self._extract_brand(canonical_device_name, source_device_id)
        model_numbers = self._extract_model_numbers(soup)
        release_date_raw, release_date_iso = self._extract_release_date(soup)

        internal_device_id = self._build_internal_device_id(
            brand=brand,
            canonical_device_name=canonical_device_name,
            source_device_id=source_device_id,
            model_numbers=model_numbers,
        )

        return DeviceRecord(
            raw_query=raw_query,
            source_name="gsmarena",
            source_device_id=source_device_id,
            canonical_device_name=canonical_device_name,
            brand=brand,
            model_numbers=model_numbers,
            source_device_url=device_url,
            release_date_raw=release_date_raw,
            release_date_iso=release_date_iso,
            internal_device_id=internal_device_id,
        )

    def lookup(self, device_name: str) -> Optional[DeviceRecord]:
        candidates = self.search(device_name)
        best = self.pick_best_candidate(device_name, candidates)

        if not best:
            return None

        return self.parse_device_page(best["url"], raw_query=device_name)

    @staticmethod
    def _normalize_name(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _slug_to_name(slug: str) -> str:
        slug = slug.replace(".php", "")
        slug = re.sub(r"-\d+$", "", slug)
        slug = slug.replace("_", " ")
        return slug.title().strip()

    @staticmethod
    def _extract_device_name(soup: BeautifulSoup) -> Optional[str]:
        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(" ", strip=True)
            if text:
                return text

        if soup.title:
            title = soup.title.get_text(" ", strip=True)
            title = re.sub(r"\s*-\s*Full.*$", "", title, flags=re.I).strip()
            if title:
                return title

        return None

    @staticmethod
    def _extract_source_device_id(device_url: str) -> Optional[str]:
        match = re.search(r"/([^/]+)\.php$", device_url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_brand(
        canonical_device_name: Optional[str],
        source_device_id: Optional[str],
    ) -> Optional[str]:
        if canonical_device_name:
            return canonical_device_name.split()[0]

        if source_device_id:
            slug_prefix = source_device_id.split("-")[0]
            return slug_prefix.split("_")[0].capitalize()

        return None

    @staticmethod
    def _extract_model_numbers(soup: BeautifulSoup) -> Optional[str]:
        """
        从 specs table 里提取 Models / Model 字段
        例如:
        Models   A2894, A3089, A3090, A3094
        """
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) != 2:
                continue

            key = cells[0].get_text(" ", strip=True).lower()
            value = cells[1].get_text(" ", strip=True)

            if key in {"model", "models"}:
                return value if value else None

        # 兜底：整页文本 regex
        page_text = soup.get_text(" ", strip=True)
        page_text = re.sub(r"\s+", " ", page_text)

        match = re.search(r"Models?\s+([A-Za-z0-9,\-\s/]+)", page_text, flags=re.I)
        if match:
            value = match.group(1).strip()
            value = re.split(r"(Announced|Released|Status|Price)", value, flags=re.I)[0].strip()
            return value if value else None

        return None

    @staticmethod
    def _extract_release_date(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
        page_text = soup.get_text("\n", strip=True)
        page_text = re.sub(r"\s+", " ", page_text)

        raw = None

        released_match = re.search(
            r"Released\s+(\d{4}(?:,\s*[A-Za-z]+)?(?:\s+\d{1,2})?)",
            page_text,
            flags=re.I,
        )
        announced_match = re.search(
            r"Announced\s+(\d{4}(?:,\s*[A-Za-z]+)?(?:\s+\d{1,2})?)",
            page_text,
            flags=re.I,
        )

        if released_match:
            raw = released_match.group(1).strip()
        elif announced_match:
            raw = announced_match.group(1).strip()

        iso = GSMArenaScraper._normalize_release_date(raw) if raw else None
        return raw, iso

    @staticmethod
    def _normalize_release_date(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None

        raw = raw.strip()
        raw = re.sub(r"\s+", " ", raw)

        # 2023, September 22
        m = re.match(r"(\d{4}),\s*([A-Za-z]+)\s+(\d{1,2})$", raw)
        if m:
            year, month_name, day = m.groups()
            month_num = GSMArenaScraper._month_to_num(month_name)
            if month_num:
                return f"{year}-{month_num:02d}-{int(day):02d}"

        # 2023, September
        m = re.match(r"(\d{4}),\s*([A-Za-z]+)$", raw)
        if m:
            year, month_name = m.groups()
            month_num = GSMArenaScraper._month_to_num(month_name)
            if month_num:
                return f"{year}-{month_num:02d}-01"

        # 2023
        m = re.match(r"(\d{4})$", raw)
        if m:
            return f"{m.group(1)}-01-01"

        return None

    @staticmethod
    def _month_to_num(month_name: str) -> Optional[int]:
        months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        return months.get(month_name.lower())

    @staticmethod
    def _build_internal_device_id(
        brand: Optional[str],
        canonical_device_name: Optional[str],
        source_device_id: Optional[str],
        model_numbers: Optional[str],
    ) -> Optional[str]:
        parts = [
            brand or "",
            canonical_device_name or "",
            model_numbers or "",
            source_device_id or "",
        ]
        key = "|".join(parts).strip("|")
        if not key:
            return None
        return hashlib.sha1(key.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    scraper = GSMArenaScraper(timeout=20, sleep_seconds=1.0)

    queries = [
        "iPhone 15",
        "iPhone 15 Plus",
        "iPhone 15 Pro",
        "iPhone 15 Pro Max",
    ]

    for q in queries:
        try:
            result = scraper.lookup(q)
            if result:
                print(asdict(result))
            else:
                print({"raw_query": q, "error": "No match found"})
        except Exception as e:
            print({"raw_query": q, "error": str(e)})