import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://www.gsmarena.com"

def browser_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

def safe_get_once(url: str, timeout: int = 12):
    """只请求一次，并打印真实错误"""
    try:
        time.sleep(random.uniform(0.8, 1.6))
        r = requests.get(url, headers=browser_headers(), timeout=timeout)
        print(f"[DEBUG] status={r.status_code} url={url}")

        # Cloudflare challenge often returns 200 but contains JS challenge
        if "cf-browser-verification" in r.text.lower():
            raise RuntimeError("Blocked by Cloudflare challenge")

        r.raise_for_status()
        return r

    except Exception as e:
        raise RuntimeError(f"Request failed: {url} ; err={repr(e)}")

def search_gsmarena(device: str, top_k: int = 5):
    """搜索 GSMArena 设备详情页"""
    q = device.replace(" ", "+")
    search_url = f"{BASE}/res.php3?sSearch={q}"

    try:
        r = safe_get_once(search_url)
    except Exception as e:
        return {
            "name": "GSMArena",
            "ok": False,
            "error": str(e),
            "attempt": 1,
            "search_url": search_url,
        }

    soup = BeautifulSoup(r.text, "html.parser")

    # 优先 makers 区域
    links = soup.select("div.makers a[href]") or soup.select("a[href]")

    candidates = []
    seen = set()

    for a in links:
        href = a.get("href", "").strip()
        if not href:
            continue

        # 过滤非详情页
        if not href.endswith(".php"):
            continue

        full = urljoin(BASE + "/", href)
        if full in seen:
            continue
        seen.add(full)

        text = a.get_text(" ", strip=True).lower()
        candidates.append((text, full))

    # 简单排序：包含 device 的优先
    device_l = device.lower()
    candidates.sort(key=lambda x: (device_l in x[0], x[0]), reverse=True)

    top = [c[1] for c in candidates[:top_k]]

    return {
        "name": "GSMArena",
        "ok": True,
        "search_url": search_url,
        "results": top,
    }