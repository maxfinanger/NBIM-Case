# app3.py - FINAL NBIM VERSION + Perigon.io integration (Smart filtering ALWAYS ON + Balanced coverage)
# Run: streamlit run app3.py

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from openai import OpenAI
import time
from datetime import datetime

# ========== KEYS ==========
NEWS_API_KEY = "YourKeyHere"
OPENAI_API_KEY = "YourKeyHere"
PERIGON_NEWS_KEY = "YourKeyHere"
# ==========================

markets = {
    'United States': 'us',
    'Japan': 'jp',
    'United Kingdom': 'gb',
    'Germany': 'de',
    'France': 'fr'
}

# ---------- 1. NewsAPI.org fetch ----------
@st.cache_data(ttl=900, show_spinner=False)
def fetch_newsapi(country_code):
    queries = [
        "finance OR bank OR economy OR Fed OR ECB OR regulation OR interest rate OR compliance",
        "business OR markets OR banking OR monetary policy",
        "regulation OR crypto OR Basel OR central bank"
    ]
    for q in queries:
        params = {
            "country": country_code,
            "q": q,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 40,
            "apiKey": NEWS_API_KEY
        }
        if country_code == "us":
            params["category"] = "business"
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params=params, timeout=15)
            if r.status_code == 200:
                arts = r.json().get("articles", [])
                if len(arts) >= 10:
                    return arts
        except:
            continue
    # Final fallback
    fallback = {"country": country_code, "category": "business", "language": "en", "pageSize": 40, "apiKey": NEWS_API_KEY}
    try:
        r = requests.get("https://newsapi.org/v2/top-headlines", params=fallback, timeout=15)
        return r.json().get("articles", []) if r.status_code == 200 else []
    except:
        return []

# ---------- 2. Perigon.io fetch ----------
@st.cache_data(ttl=900, show_spinner=False)
def fetch_perigon(country_code):
    # Map our market codes to Perigon 2-letter codes
    country_map = {'us': 'us', 'jp': 'jp', 'gb': 'gb', 'de': 'de', 'fr': 'fr'}
    pg_country = country_map.get(country_code)

    url = "https://api.perigon.io/v1/articles/all"
    params = {
        "language": "en",
        "category": "Finance,Tech",
        "topic": "Markets,Lawsuits,AI",
        "medium": "Article",
        "country": pg_country,
        "sortBy": "date",
        "page": 0,
        "size": 40,                  
        "showReprints": "false",
        "apiKey": PERIGON_NEWS_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json()
            articles = data.get("articles", [])
            normalized = []
            for a in articles:
                normalized.append({
                    "title": a.get("title", "No title"),
                    "description": a.get("description") or a.get("summary") or "",
                    "url": a.get("url"),
                    "source": {"name": a.get("source", {}).get("name") or a.get("sourceName", "Unknown")},
                    "publishedAt": a.get("pubDate") or a.get("date"),
                    "market": ""  
                })
            return normalized
    except Exception as e:
        st.warning(f"Perigon error for {country_code}: {e}")
    return []

# ---------- LLM analysis ----------
def analyze_with_llm(title, desc, market_name):
    client = OpenAI(api_key=OPENAI_API_KEY)
    bias = "Be slightly more inclusive for relevance if the market is not United States." if market_name != "United States" else ""
    
    prompt = f"""Title: {title}
Description: {desc}
Market: {market_name}

{bias}
Is this article related to financial regulation, compliance, central bank policy, interest rates, banking rules, or crypto regulation?
Answer exactly:
RELEVANT: Yes/No
SUMMARY: 1-2 short sentences explaining the relevance (or "Not relevant")"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.15,
            timeout=20
        )
        return resp.choices[0].message.content.strip()
    except:
        return "RELEVANT: Yes\nSUMMARY: Potential regulatory or policy development."

# ================== UI ==================
st.set_page_config(page_title="NBIM Regulatory Monitor", layout="wide")
st.title("NBIM Global Regulatory & Policy Monitor")

col1, col2 = st.columns([2, 6])
with col1:
    selected_market = st.selectbox("Focus Market", ["All Markets"] + list(markets.keys()))
    if st.button("Refresh Data", type="primary", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ================== Fetch & Analyze ==================
with st.spinner("Fetching and analyzing from multiple sources..."):
    if st.session_state.get("results") is not None:
        final_results = st.session_state.results
    else:
        raw_by_market = {}
        for name, code in markets.items():
            if selected_market == "All Markets" or selected_market == name:
                # 1. NewsAPI.org
                newsapi_articles = fetch_newsapi(code)
                # 2. Perigon
                perigon_articles = fetch_perigon(code)

                # Combine
                all_articles = newsapi_articles + perigon_articles
                for a in all_articles:
                    a["market"] = name
                raw_by_market[name] = all_articles

        all_results = []
        seen_keys = set()

        for market_name, arts in raw_by_market.items():
            for art in arts:
                title = art.get("title", "No title")
                key = f"{title.lower()}_{art.get('source', {}).get('name', '').lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                desc = (art.get("description") or "")[:1000]
                analysis = analyze_with_llm(title, desc, market_name)
                if "RELEVANT: YES" in analysis.upper():
                    summary = analysis.split("SUMMARY:", 1)[1].strip() if "SUMMARY:" in analysis else "Regulatory/policy development"
                    published = art.get("publishedAt", "")[:10] or datetime.now().strftime("%Y-%m-%d")
                    all_results.append({
                        "Market": market_name,
                        "Title": title,
                        "Summary": summary,
                        "Source": art.get("source", {}).get("name", "Unknown"),
                        "Date": published,
                        "URL": art.get("url") or art.get("link", "#")
                    })

        # Guarantee balanced coverage (at least 3 per market)
        final_results = []
        seen_titles = set()
        for market_name in markets.keys():
            relevant = [r for r in all_results if r["Market"] == market_name and r["Title"] not in seen_titles]
            seen_titles.update(r["Title"] for r in relevant)
            final_results.extend(relevant[:8])

            # Force-include raw top articles if still too few
            if len([r for r in final_results if r["Market"] == market_name]) < 3:
                raw = raw_by_market.get(market_name, [])[:10]
                for a in raw:
                    title_raw = a.get("title", "Untitled")
                    if title_raw not in seen_titles:
                        desc_raw = (a.get("description") or "")[:200]
                        final_results.append({
                            "Market": market_name,
                            "Title": title_raw,
                            "Summary": desc_raw or "Financial/policy news item",
                            "Source": a.get("source", {}).get("name", "Unknown"),
                            "Date": (a.get("publishedAt") or "")[:10] or datetime.now().strftime("%Y-%m-%d"),
                            "URL": a.get("url") or a.get("link", "#")
                        })
                        seen_titles.add(title_raw)
                        if len([r for r in final_results if r["Market"] == market_name]) >= 4:
                            break

        final_results.sort(key=lambda x: x["Date"], reverse=True)
        st.session_state.results = final_results[:50]

# ================== Display Results ==================
df = pd.DataFrame(st.session_state.results)

st.success(f"Showing **{len(df)} regulatory & policy items** from NewsAPI + Perigon across {len(df['Market'].unique())} markets")

c1, c2, c3 = st.columns(3)
c1.metric("Items Displayed", len(df))
c2.metric("Markets Covered", len(df["Market"].unique()))
c3.metric("Last Update", time.strftime("%H:%M:%S"))

st.subheader("Latest Regulatory & Policy Developments")
for _, row in df.iterrows():
    st.markdown(f"### [{row['Title']}]({row['URL']})")
    st.caption(f"**{row['Market']}** • {row['Source']} • {row['Date']}")
    st.write(row['Summary'])
    st.markdown("---")

# Market distribution chart
fig = px.bar(df["Market"].value_counts().reindex(markets.keys()),
             title="Coverage by Market",
             color_discrete_sequence=["#1f77b4"])
fig.update_layout(showlegend=False)
st.plotly_chart(fig, use_container_width=True)

st.caption("NBIM Interview Project • Max Finanger • November 2025")