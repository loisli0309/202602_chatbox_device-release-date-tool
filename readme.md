# 📱 Phone Release Date Finder

A Streamlit app that retrieves phone release dates from multiple authoritative sources:
- **Wikidata** (structured knowledge base)
- **Wikipedia** (infobox parsing)
- **GSMArena** (direct device detail pages, optional due to rate limits)

The app auto-selects the best available release date and can calculate **days in market**.

---

## ✨ Features

- 🔎 Search by device name (e.g., iPhone 15, Galaxy S23)
- 🧠 Multi-source fallback (Wikidata → Wikipedia → GSMArena)
- ⚠️ Graceful handling of rate limits (GSMArena 429)
- 📅 Auto-pick best release date
- 📈 Days in market calculation
- 🧪 Debug mode for troubleshooting
- 🔗 Optional direct GSMArena detail page input (avoid search rate limits)

---

## 🛠 Tech Stack

- Python 3.10+
- Streamlit
- Requests
- BeautifulSoup4

---

## 🚀 Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/<your-username>/phone-release-date-finder.git
cd phone-release-date-finder