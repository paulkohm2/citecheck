"""
streamlit_app.py — Streamlit version of the Citation Health Checker.

Run locally:
    streamlit run streamlit_app.py

Deploy: push to GitHub, connect the repo at share.streamlit.io.
Set COURTLISTENER_API_KEY under Settings → Secrets in the Streamlit Cloud UI.
"""

import pandas as pd
import streamlit as st

import core

st.set_page_config(
    page_title="Citation Health Checker",
    layout="wide",
)

st.title("Citation Health Checker")
st.caption("powered by CourtListener")

# ── Cached API calls ──────────────────────────────────────────────────────────
#
# @st.cache_data memoizes the return value keyed on the function arguments.
# The first call hits the API and shows the spinner; any repeat call with the
# same argument returns instantly from cache with no network request.

@st.cache_data(show_spinner="Searching CourtListener…")
def find_case(query: str):
    return core.find_case(query)


@st.cache_data(show_spinner="Fetching citations…")
def fetch_citations(opinion_id: int):
    return core.fetch_forward_citations(opinion_id)


# ── Search input ──────────────────────────────────────────────────────────────

query = st.text_input(
    "Case or citation",
    placeholder="e.g.  Roe v. Wade   or   410 U.S. 113",
)

if not query:
    st.stop()   # nothing typed yet — render nothing below this line

# ── Case lookup ───────────────────────────────────────────────────────────────

case = find_case(query.strip())
if not case:
    st.error("No case found.")
    st.stop()

# ── Citation fetch ────────────────────────────────────────────────────────────

total, cases = fetch_citations(case["opinion_id"])
by_year = core.citations_by_year(cases)

# ── Case metadata ─────────────────────────────────────────────────────────────

st.subheader(case["case_name"])

c1, c2, c3 = st.columns(3)
c1.metric("Court", case["court"])
c2.metric("Filed", case["date_filed"])
c3.metric(
    "Total Citations",
    f"{total:,}",
    help=f"Showing most recent {len(cases):,}" if len(cases) < total else None,
)

# ── Bar chart ─────────────────────────────────────────────────────────────────

if by_year:
    st.subheader("Citations by Year")
    st.bar_chart(by_year, x_label="Year", y_label="Citations")

# ── Results table ─────────────────────────────────────────────────────────────

st.subheader("Citing Cases — most recent first")

df = pd.DataFrame(cases)[["date_filed", "case_name", "court", "cite_count", "url"]]
df["cite_count"] = df["cite_count"].fillna(0).astype(int)

st.dataframe(
    df,
    column_config={
        "date_filed": st.column_config.TextColumn("Date Filed"),
        "case_name":  st.column_config.TextColumn("Case Name"),
        "court":      st.column_config.TextColumn("Court"),
        "cite_count": st.column_config.NumberColumn("Times Cited"),
        "url":        st.column_config.LinkColumn("Link"),
    },
    hide_index=True,
    use_container_width=True,
)
