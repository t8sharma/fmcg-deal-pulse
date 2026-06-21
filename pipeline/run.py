"""
Orchestrator — runs the full pipeline end to end:

    ingest → clean/normalize → de-duplicate → score relevance → filter →
    credibility floor → outputs (CSV/JSON) + newsletter (Markdown/DOCX)

Run from the project root:
    python -m pipeline.run               # live fetch, fall back to seed if offline
    python -m pipeline.run --offline     # force the bundled seed dataset
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os

from . import clean, config, ingest, newsletter, relevance

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
SEED_PATH = os.path.join(DATA_DIR, "sample_articles.json")
OUT_DIR = os.path.join(DATA_DIR, "outputs")


def load_seed() -> list[dict]:
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(use_live: bool = True, fallback_to_seed: bool = True) -> dict:
    """
    Execute the pipeline and return a result dict:
        {articles, all_scored, stats, generated_at}
    `articles` = final relevant, credible, de-duplicated deals.
    `all_scored` = every de-duplicated article with scores (for the raw export).
    """
    if not use_live:
        raw = load_seed()
        used_source = "seed (forced offline)"
    else:
        raw = ingest.ingest(use_live=True)
        used_source = "live"
        if not raw and fallback_to_seed:
            raw = load_seed()
            used_source = "seed (offline fallback)"

    ingested = len(raw)

    normalized = clean.normalize(raw)
    deduped, removed = clean.deduplicate(normalized)
    scored = relevance.score_all(deduped)

    relevant = relevance.filter_relevant(scored)
    # credibility floor for the newsletter
    credible = [a for a in relevant if a.get("credibility", 0) >= config.CREDIBILITY_FLOOR]

    stats = {
        "ingested": ingested,
        "after_dedup": len(deduped),
        "duplicates_removed": removed,
        "scored": len(scored),
        "relevant": len(relevant),
        "credible_relevant": len(credible),
        "sources_count": len({a.get("publisher") or a.get("domain") for a in credible}),
        "data_source": used_source,
    }

    return {
        "articles": credible,
        "all_scored": scored,
        "stats": stats,
        "generated_at": dt.datetime.now(),
    }


# ---- export helpers --------------------------------------------------------

_CSV_FIELDS = [
    "title_clean", "acquirer", "target", "deal_value", "category",
    "publisher", "domain", "credibility", "credibility_reason",
    "relevance_score", "is_relevant", "dup_count", "published", "url",
    "deal_terms_hit", "fmcg_terms_hit", "companies_hit", "relevance_reason",
]


def _flatten(a: dict) -> dict:
    out = {}
    for k in _CSV_FIELDS:
        v = a.get(k, "")
        if isinstance(v, list):
            v = "; ".join(map(str, v))
        out[k] = v
    return out


def export_csv(articles: list[dict], path: str) -> str:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for a in articles:
            w.writerow(_flatten(a))
    return path


def export_json(articles: list[dict], path: str) -> str:
    clean_records = []
    for a in articles:
        rec = {k: v for k, v in a.items() if k not in ("title_norm",)}
        clean_records.append(rec)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean_records, f, indent=2, ensure_ascii=False)
    return path


def main():
    ap = argparse.ArgumentParser(description="Run the FMCG Deal Intelligence pipeline.")
    ap.add_argument("--offline", action="store_true", help="Use bundled seed data only.")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    result = run_pipeline(use_live=not args.offline)

    # Raw data exports = every de-duplicated, scored article (relevant or not),
    # so reviewers can see what was filtered and why.
    export_csv(result["all_scored"], os.path.join(OUT_DIR, "raw_data.csv"))
    export_json(result["all_scored"], os.path.join(OUT_DIR, "raw_data.json"))

    md = newsletter.build_markdown(result["articles"], result["generated_at"], result["stats"])
    with open(os.path.join(OUT_DIR, "newsletter.md"), "w", encoding="utf-8") as f:
        f.write(md)

    try:
        newsletter.build_docx(
            result["articles"], os.path.join(OUT_DIR, "newsletter.docx"),
            result["generated_at"], result["stats"],
        )
        docx_ok = True
    except Exception as exc:  # noqa: BLE001
        docx_ok = False
        print(f"[run] DOCX export skipped ({exc}); install python-docx to enable.")

    s = result["stats"]
    print("=" * 60)
    print("FMCG Deal Intelligence — pipeline complete")
    print("=" * 60)
    print(f"Data source        : {s['data_source']}")
    print(f"Ingested           : {s['ingested']}")
    print(f"After de-dup       : {s['after_dedup']}  (removed {s['duplicates_removed']})")
    print(f"Relevant           : {s['relevant']}")
    print(f"Credible+relevant  : {s['credible_relevant']}  from {s['sources_count']} sources")
    print(f"Outputs            : {OUT_DIR}")
    print(f"  - raw_data.csv / raw_data.json")
    print(f"  - newsletter.md" + ("  / newsletter.docx" if docx_ok else ""))


if __name__ == "__main__":
    main()
