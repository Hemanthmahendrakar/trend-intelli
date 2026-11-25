"""Streamlit MVP dashboard.

Purpose: presents the API's data: top trends with score breakdowns, emerging
topics, per-platform discussion, clickable source articles, history and
methodology. It talks only to the FastAPI backend (API_BASE_URL), never to the
database directly.

Run with: streamlit run src/trendintel/dashboard/app.py
"""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

from trendintel.trends.scoring import METHODOLOGY_MD

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="Internet Trend Intelligence", page_icon="📈", layout="wide")


@st.cache_data(ttl=60, show_spinner=False)
def api_get(path: str, params: tuple = ()) -> list | dict:
    response = requests.get(f"{API_BASE_URL}{path}", params=list(params), timeout=15)
    response.raise_for_status()
    return response.json()


def safe_get(path: str, **params):
    flat = tuple(
        (k, item) for k, v in params.items() for item in (v if isinstance(v, (list, tuple)) else [v])
    )
    try:
        return api_get(path, flat)
    except requests.RequestException as exc:
        st.error(f"Could not reach the API at {API_BASE_URL}: {exc}")
        st.stop()


def md_link(title: str, url: str) -> str:
    return f"[{title.replace('[', '(').replace(']', ')')}]({url})"


def trends_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["change"] = frame["mention_count"] - frame["prev_mention_count"]
    frame["sources_list"] = frame["sources"].apply(lambda s: ", ".join(s))
    return frame


# ----------------------------------------------------------------- sidebar
st.sidebar.title("📈 Trend Intelligence")
top_n = st.sidebar.slider("Topics to show", 5, 25, 10)
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
st.sidebar.caption(f"API: {API_BASE_URL}")

st.title("What's trending right now")

trends = safe_get("/trends", limit=max(top_n, 25))
if not trends:
    st.info("No trend snapshot yet. Run `trendintel run` (or `collect` then `analyze`) and refresh.")
    st.stop()

frame = trends_frame(trends)
top = frame.head(top_n)
st.caption(
    f"Snapshot computed {pd.to_datetime(frame['computed_at'].iloc[0]):%Y-%m-%d %H:%M UTC} · "
    f"window: last {frame['window_hours'].iloc[0]:.0f} h vs the {frame['window_hours'].iloc[0]:.0f} h before"
)
if not bool(frame["history_available"].iloc[0]):
    st.warning(
        "Not enough collection history yet: growth is excluded from scores and nothing is flagged as emerging. "
        "Keep the collector running for a day or two."
    )

tab_top, tab_emerging, tab_platform, tab_history, tab_health, tab_method = st.tabs(
    ["Top trends", "Emerging", "By platform", "History", "Source health", "Methodology"]
)

# ---------------------------------------------------------------- top trends
with tab_top:
    display = top[["label", "total_score", "mention_count", "prev_mention_count", "change", "sources_list", "is_emerging"]]
    display = display.rename(
        columns={
            "label": "Topic",
            "total_score": "Score",
            "mention_count": "Mentions",
            "prev_mention_count": "Previous window",
            "change": "Change",
            "sources_list": "Sources",
            "is_emerging": "Emerging",
        }
    )
    display.index = range(1, len(display) + 1)
    st.dataframe(
        display,
        use_container_width=True,
        column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f")},
    )

    st.subheader("Drill down")
    choice = st.selectbox("Topic", top["label"].tolist())
    row = top[top["label"] == choice].iloc[0]
    left, right = st.columns([2, 1])
    with left:
        st.markdown("**Articles**")
        articles = safe_get(f"/topics/{int(row['topic_id'])}/articles", limit=30)
        if not articles:
            st.write("No linked articles.")
        for a in articles:
            when = pd.to_datetime(a["published_at"] or a["collected_at"]).strftime("%Y-%m-%d %H:%M")
            st.markdown(f"- {md_link(a['title'], a['url'])} — *{a['source']}*, {when} UTC")
    with right:
        st.markdown("**Score components (0-1)**")
        comp = pd.DataFrame(
            {
                "value": [row["frequency_score"], row["recency_score"], row["growth_score"], row["diversity_score"]],
            },
            index=["Frequency", "Recency", "Growth", "Source diversity"],
        )
        st.bar_chart(comp)
        st.caption(f"{int(row['mention_count'])} mentions now vs {int(row['prev_mention_count'])} in the previous window.")

# ------------------------------------------------------------------ emerging
with tab_emerging:
    emerging = safe_get("/trends/emerging", limit=top_n)
    if not emerging:
        st.info("No emerging topics in the latest snapshot (needs history, and topics absent from the previous window).")
    for t in emerging:
        with st.expander(f"{t['label']} — {t['mention_count']} mentions · score {t['total_score']:.1f}"):
            st.write("Sources: " + ", ".join(t["sources"]))
            for a in safe_get(f"/topics/{t['topic_id']}/articles", limit=5):
                st.markdown(f"- {md_link(a['title'], a['url'])} — *{a['source']}*")

# ----------------------------------------------------------------- platforms
with tab_platform:
    st.caption("Top currently-trending topics within each platform (last 24 h).")
    rows = safe_get("/platforms/topics", hours=24, per_source=5)
    if not rows:
        st.info("No platform data yet.")
    else:
        sources = sorted({r["source"] for r in rows})
        columns = st.columns(len(sources))
        for column, source in zip(columns, sources):
            with column:
                st.markdown(f"**{source}**")
                for r in (r for r in rows if r["source"] == source):
                    st.write(f"{r['label']} ({r['mentions']})")

# ------------------------------------------------------------------- history
with tab_history:
    options = dict(zip(frame["label"], frame["topic_id"]))
    selected = st.multiselect("Topics to compare", list(options), default=list(options)[:3])
    days = st.slider("Days", 1, 30, 7)
    metric = st.radio("Metric", ["total_score", "mention_count"], horizontal=True)
    if selected:
        history = safe_get("/trends/history", topic_ids=[int(options[s]) for s in selected], days=days)
        if history:
            chart = pd.DataFrame(history)
            chart["computed_at"] = pd.to_datetime(chart["computed_at"])
            st.line_chart(chart.pivot_table(index="computed_at", columns="label", values=metric))
            st.caption("History accumulates with each analysis run; topics only appear for runs in which they ranked.")
        else:
            st.info("No history for these topics yet.")

# -------------------------------------------------------------------- health
with tab_health:
    st.markdown("**Sources**")
    st.dataframe(pd.DataFrame(safe_get("/sources")), use_container_width=True)
    st.markdown("**Recent collection runs**")
    st.dataframe(pd.DataFrame(safe_get("/runs", limit=30)), use_container_width=True)

# --------------------------------------------------------------- methodology
with tab_method:
    st.markdown(METHODOLOGY_MD)
