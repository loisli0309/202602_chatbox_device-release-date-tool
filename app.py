import re
import streamlit as st
from cachetools import TTLCache
from orchestrator import lookup

# ---------------------------
# Page Config (MUST be first Streamlit call)
# ---------------------------
st.set_page_config(page_title="Device Global Release Chat (Demo)", layout="centered")
st.title("📱 Device Global Release Chat (Demo)")

with st.expander("How it works"):
    st.markdown("""
- Type a device name (e.g., *iPhone 15*, *Galaxy S23*).
- The app searches public sources for global release dates.
- It resolves conflicts and shows evidence (source + excerpt).
- Results are cached for 24 hours.
""")

# ---------------------------
# Cache (device -> lookup result)
# ---------------------------
cache = TTLCache(maxsize=500, ttl=24 * 3600)  # 24 hours

# ---------------------------
# Utils: rule-based device extraction (Demo)
# ---------------------------
def extract_device_rule_based(text: str) -> str:
    """
    Demo: extract device name using simple rules
    - Remove common query phrases
    - Normalize iphone15 -> iphone 15
    """
    t = text.strip()

    patterns = [
        r"help me check", r"check", r"lookup",
        r"global", r"release",
        r"launch", r"launched", r"release date", r"date in market",
        r"when", r"what date", r"available"
    ]
    t = re.sub("|".join(patterns), " ", t, flags=re.I)

    # Normalize common device naming
    t = re.sub(r"(iphone)(\d+)", r"\1 \2", t, flags=re.I)
    t = re.sub(r"(pixel)(\d+)", r"\1 \2", t, flags=re.I)
    t = re.sub(r"(galaxy\s*s)(\d+)", r"\1 \2", t, flags=re.I)

    t = re.sub(r"\s+", " ", t).strip()
    return t if t else text.strip()

# ---------------------------
# Session State
# ---------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------------------------
# Render Chat History
# ---------------------------
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ---------------------------
# Chat Input
# ---------------------------
user_input = st.chat_input("e.g., When did iPhone 15 globally release? / Galaxy S23 release date?")

if user_input:
    # User message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    device = extract_device_rule_based(user_input)

    # Lookup with cache + error handling
    try:
        if device in cache:
            result = cache[device]
        else:
            result = lookup(device)
            cache[device] = result
    except Exception as e:
        answer = f"❌ Error while looking up **{device}**: `{e}`"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)
    else:
        # Prepare fields safely
        pf = result.get("picked_from") or {}
        source = pf.get("source", "N/A")
        evidence = pf.get("evidence", "N/A")
        url = pf.get("url", "N/A")

        # Format answer
        if result.get("global_release"):
            answer = f"""
**{result.get('device', device)}**

✅ **Global Release:** **{result['global_release']}**  
🔎 **Source:** {source}  
🔗 **Link:** {url}  
📌 **Evidence:** {evidence}
"""
            conflicts = result.get("conflicts", [])
            if conflicts:
                answer += "\n⚠️ **Other dates found:**\n"
                for c in conflicts[:5]:
                    answer += f"- {c.get('date')} ({c.get('type')}) — {c.get('source')}\n"
        else:
            # If no date, still show what we found (status/announcement/etc.) if available
            answer = f"""
**{result.get('device', device)}**

⚠️ **No confirmed global release date found.**  
🔎 **Source:** {source}  
🔗 **Link:** {url}  
📌 **Evidence:** {evidence}
"""

        # Assistant message
        st.session_state.messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)

            # Debug block (optional)
            with st.expander("Debug"):
                st.json(result.get("debug", {}))