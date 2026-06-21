"""
FMCG Deal Pulse — Streamlit demo app.

Runs the full intelligence pipeline live (ingest → clean → de-dupe → score →
newsletter) and lets a business user explore ranked deals, inspect the funnel,
and download the newsletter + raw data.

Run locally:   streamlit run app.py
Deploy free:   Streamlit Community Cloud (see DEPLOY.md)
"""
from __future__ import annotations

import datetime as dt
import io
import json

import pandas as pd
import streamlit as st

from pipeline import clean, config, ingest, newsletter, relevance, run as pipeline_run

st.set_page_config(page_title="FMCG Deal Pulse", page_icon="📰", layout="wide")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0'>📰 FMCG Deal Pulse</h1>"
    "<p style='color:#666;margin-top:4px;font-size:1.05rem'>"
    "Real-time M&A &amp; investment intelligence for Fast-Moving Consumer Goods</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Pipeline controls")
    mode = st.radio(
        "Data source",
        ["Live news (Google News RSS)", "Bundled sample (offline)"],
        help="Live pulls fresh headlines. Sample uses a curated real-deal dataset "
             "so the demo always works, even offline.",
    )
    use_live = mode.startswith("Live")

    st.subheader("Relevance & credibility")
    rel_threshold = st.slider("Relevance threshold", 0, 100, config.RELEVANCE_THRESHOLD, 5)
    cred_floor = st.slider("Min source credibility", 0.0, 1.0, config.CREDIBILITY_FLOOR, 0.05)
    dup_threshold = st.slider("Near-duplicate sensitivity", 0.5, 0.95,
                              config.NEAR_DUP_THRESHOLD, 0.01,
                              help="Higher = stricter (fewer merges).")

    st.caption("Tune the knobs, then run the pipeline.")
    go = st.button("🚀 Run pipeline", type="primary", use_container_width=True)


@st.cache_data(show_spinner=False, ttl=900)
def _ingest_cached(use_live: bool):
    raw = ingest.ingest(use_live=use_live)
    src = "live"
    if not raw:
        raw = pipeline_run.load_seed()
        src = "seed (offline fallback)"
    if not use_live:
        raw = pipeline_run.load_seed()
        src = "seed"
    return raw, src


def run_with_params(use_live, rel_threshold, cred_floor, dup_threshold):
    # Apply the live-tuned thresholds.
    config.RELEVANCE_THRESHOLD = rel_threshold
    config.CREDIBILITY_FLOOR = cred_floor

    raw, src = _ingest_cached(use_live)
    ingested = len(raw)
    normalized = clean.normalize(raw)
    deduped, removed = clean.deduplicate(normalized, threshold=dup_threshold)
    scored = relevance.score_all(deduped)
    relevant = relevance.filter_relevant(scored)
    credible = [a for a in relevant if a.get("credibility", 0) >= cred_floor]
    stats = {
        "ingested": ingested,
        "after_dedup": len(deduped),
        "duplicates_removed": removed,
        "relevant": len(relevant),
        "credible_relevant": len(credible),
        "sources_count": len({a.get("publisher") or a.get("domain") for a in credible}),
        "data_source": src,
    }
    return {"articles": credible, "all_scored": scored, "stats": stats,
            "generated_at": dt.datetime.now()}


# Run on click, or once on first load with defaults.
if go or "result" not in st.session_state:
    with st.spinner("Ingesting, de-duplicating, scoring…"):
        st.session_state.result = run_with_params(
            use_live, rel_threshold, cred_floor, dup_threshold
        )

result = st.session_state.result
articles = result["articles"]
stats = result["stats"]

# ---------------------------------------------------------------------------
# Funnel metrics
# ---------------------------------------------------------------------------
st.caption(f"Data source: **{stats['data_source']}** · "
           f"generated {result['generated_at'].strftime('%d %b %Y, %H:%M')}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Ingested", stats["ingested"])
c2.metric("After de-dup", stats["after_dedup"], delta=f"-{stats['duplicates_removed']} dupes")
c3.metric("Relevant", stats["relevant"])
c4.metric("Credible deals", stats["credible_relevant"])
c5.metric("Sources", stats["sources_count"])

if not articles:
    st.warning("No deals passed the filters. Try lowering the relevance threshold "
               "or credibility floor in the sidebar.")
    st.stop()

tab_news, tab_deals, tab_raw, tab_how = st.tabs(
    ["📰 Newsletter", "📊 Deals table", "🗂️ Raw data", "🔬 How it works"]
)

# ---------------------------------------------------------------------------
# Newsletter tab
# ---------------------------------------------------------------------------
with tab_news:
    md = newsletter.build_markdown(articles, result["generated_at"], stats)
    st.markdown(md)

    colA, colB = st.columns(2)
    with colA:
        st.download_button("⬇️ Download newsletter (Markdown)", md,
                           file_name="fmcg_deal_pulse.md", mime="text/markdown",
                           use_container_width=True)
    with colB:
        try:
            buf = io.BytesIO()
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                newsletter.build_docx(articles, tmp.name, result["generated_at"], stats)
                tmp_path = tmp.name
            with open(tmp_path, "rb") as f:
                buf.write(f.read())
            os.unlink(tmp_path)
            st.download_button(
                "⬇️ Download newsletter (Word .docx)", buf.getvalue(),
                file_name="fmcg_deal_pulse.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.info(f"Word export unavailable: {exc}")

# ---------------------------------------------------------------------------
# Deals table tab
# ---------------------------------------------------------------------------
with tab_deals:
    df = pd.DataFrame([
        {
            "Deal": a.get("title_clean", a.get("title", "")),
            "Acquirer": a.get("acquirer", ""),
            "Target": a.get("target", ""),
            "Value": a.get("deal_value", ""),
            "Category": a.get("category", ""),
            "Source": a.get("publisher") or a.get("domain", ""),
            "Credibility": round(a.get("credibility", 0), 2),
            "Relevance": a.get("relevance_score", 0),
            "Corroboration": a.get("dup_count", 1),
            "URL": a.get("url", ""),
        }
        for a in sorted(articles, key=lambda x: x.get("relevance_score", 0), reverse=True)
    ])
    cats = ["All"] + sorted(df["Category"].unique().tolist())
    pick = st.selectbox("Filter by category", cats)
    view = df if pick == "All" else df[df["Category"] == pick]
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )
    st.download_button("⬇️ Download deals (CSV)", view.to_csv(index=False),
                       file_name="fmcg_deals.csv", mime="text/csv")

# ---------------------------------------------------------------------------
# Raw data tab
# ---------------------------------------------------------------------------
with tab_raw:
    st.write("Every de-duplicated article with its scores — including items the "
             "relevance filter rejected, so you can see *what* was filtered and *why*.")
    raw_rows = [pipeline_run._flatten(a) for a in result["all_scored"]]
    raw_df = pd.DataFrame(raw_rows)
    st.dataframe(raw_df, use_container_width=True, hide_index=True)
    colC, colD = st.columns(2)
    colC.download_button("⬇️ Raw data (CSV)", raw_df.to_csv(index=False),
                         file_name="raw_data.csv", mime="text/csv",
                         use_container_width=True)
    colD.download_button(
        "⬇️ Raw data (JSON)",
        json.dumps([{k: v for k, v in a.items() if k != "title_norm"}
                    for a in result["all_scored"]], indent=2, ensure_ascii=False),
        file_name="raw_data.json", mime="application/json",
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# How it works tab
# ---------------------------------------------------------------------------
with tab_how:
    st.markdown(
        f"""
**Pipeline:** `ingest → clean → de-duplicate → score → filter → newsletter`

1. **Ingestion** — keyless public news via Google News RSS across
   {len(config.GOOGLE_NEWS_QUERIES)} FMCG + deal queries (recency window
   {config.RECENCY_DAYS} days). No API keys required.
2. **Clean & normalize** — strip publisher suffixes, resolve domain, attach a
   credibility score.
3. **De-duplication** — exact URL/title match, then **near-duplicate clustering**:
   two titles merge when `max(token-Jaccard, sequence-ratio) ≥ {dup_threshold}`.
   The highest-credibility copy is kept; the rest become a corroboration count.
4. **Relevance scoring** — an article must show **both** a deal signal
   (acquire / merger / stake / buyout / divest …) **and** an FMCG signal (sector
   term or named FMCG company). Scored 0–100; kept above **{rel_threshold}**.
5. **Credibility** — transparent source tiers: wire/financial **1.0**, trade
   **0.75**, general **0.5**, unknown **0.4**. Newsletter floor **{cred_floor}**.
6. **Newsletter** — ranked top deals, category breakdown, methodology footer;
   exportable to Word and Markdown.

**Transparent assumptions:** headlines/summaries are taken as accurate; deal value
and parties are best-effort regex extractions and should be verified against the
linked source before any decision.
        """
    )
    st.caption("Tune thresholds in the sidebar to see precision/recall trade-offs live.")
