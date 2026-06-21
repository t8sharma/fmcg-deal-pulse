"""
Cleaning & de-duplication.

Two stages:
  1. Normalize each article (clean title, resolve a publisher/domain).
  2. Remove exact and near-duplicate stories.

De-duplication logic (transparent, no ML model required):
  * EXACT: identical normalized URL or identical normalized title -> drop later copy.
  * NEAR:  cluster titles whose similarity >= NEAR_DUP_THRESHOLD, where similarity =
           max(token-set Jaccard, difflib sequence ratio) on normalized titles.
           Within a near-dup cluster we keep ONE representative — the one with the
           highest source credibility, breaking ties by earliest publish date.

Why both metrics? Jaccard catches reworded headlines with the same key tokens
("Mars completes Kellanova acquisition" vs "Mars closes acquisition of Kellanova"),
while difflib catches lightly edited strings. Taking the max makes the matcher
forgiving enough to catch syndicated/rewritten copy without over-merging.
"""
from __future__ import annotations

import difflib
import re
from urllib.parse import urlparse

from . import config
from .credibility import score_credibility

_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "with", "as",
    "at", "by", "from", "its", "it", "is", "are", "be", "into", "amid", "over",
}


def domain_of(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
        return net[4:] if net.startswith("www.") else net
    except Exception:  # noqa: BLE001
        return ""


def normalize_title(title: str) -> str:
    t = title.lower()
    # Google News appends " - Publisher"; drop the trailing publisher attribution.
    t = re.sub(r"\s+-\s+[^-]+$", "", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _publisher_from_title(title: str) -> str:
    m = re.search(r"\s+-\s+([^-]+)$", title)
    return m.group(1).strip() if m else ""


def _tokens(norm_title: str) -> set[str]:
    return {w for w in norm_title.split() if w not in _STOPWORDS and len(w) > 2}


def _similarity(a_norm: str, b_norm: str) -> float:
    ta, tb = _tokens(a_norm), _tokens(b_norm)
    if ta and tb:
        jacc = len(ta & tb) / len(ta | tb)
    else:
        jacc = 0.0
    seq = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
    return max(jacc, seq)


def entity_signature(title_clean: str) -> set[str]:
    """
    Key entities in a headline: canonical FMCG company names plus other proper
    nouns (capitalized words). Two stories about the *same deal* almost always
    share the acquirer and the target — so a 2+ entity overlap is a strong
    duplicate signal even when the wording differs a lot.
    """
    low = title_clean.lower()
    sig: set[str] = set()

    # 1. Known companies (alias-aware, longest match first to avoid double counts).
    companies = sorted(config.FMCG_COMPANIES, key=len, reverse=True)
    matched_spans = low
    for c in companies:
        if c in matched_spans:
            canon = config.COMPANY_ALIASES.get(c, c)
            sig.add(canon)
            matched_spans = matched_spans.replace(c, " ")  # avoid substring double-hits
    # apply aliases for any bare tokens too
    for alias, canon in config.COMPANY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            sig.add(canon)
            sig.discard(alias)

    # 2. Other proper nouns (capitalized, len>3) from the original title.
    for tok in re.findall(r"\b[A-Z][a-zA-Z0-9&'\-]{3,}\b", title_clean):
        t = tok.lower()
        if t not in _STOPWORDS:
            sig.add(t)

    return sig


def normalize(articles: list[dict]) -> list[dict]:
    """Add normalized fields, resolve publisher/domain, and attach credibility."""
    out = []
    for a in articles:
        title = a.get("title", "")
        url = a.get("url", "")
        publisher = a.get("source_name") or _publisher_from_title(title)
        domain = domain_of(url)
        rec = dict(a)
        rec["title_clean"] = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
        rec["title_norm"] = normalize_title(title)
        rec["publisher"] = publisher
        rec["domain"] = domain
        cred, cred_reason = score_credibility(domain, publisher)
        rec["credibility"] = cred
        rec["credibility_reason"] = cred_reason
        out.append(rec)
    return out


def deduplicate(articles: list[dict], threshold: float | None = None) -> tuple[list[dict], int]:
    """
    Returns (unique_articles, num_removed).

    Each surviving article gains a `dup_count` field = how many sources carried the
    same story (a small corroboration signal).
    """
    threshold = threshold or config.NEAR_DUP_THRESHOLD

    # Stage 1: exact dedupe on normalized URL or title.
    seen_url, seen_title = set(), set()
    staged = []
    for a in articles:
        key_url = a.get("url", "").split("?")[0].rstrip("/").lower()
        key_title = a.get("title_norm", "")
        if (key_url and key_url in seen_url) or (key_title and key_title in seen_title):
            continue
        if key_url:
            seen_url.add(key_url)
        if key_title:
            seen_title.add(key_title)
        staged.append(a)

    # Pre-compute entity signatures once.
    for a in staged:
        a["_sig"] = entity_signature(a.get("title_clean", a.get("title", "")))

    # Stage 2: near-duplicate clustering. Two stories merge if EITHER their titles
    # are similar enough OR they share >= 2 key entities (acquirer + target).
    clusters: list[list[dict]] = []
    for a in staged:
        placed = False
        for cluster in clusters:
            head = cluster[0]
            title_match = _similarity(a["title_norm"], head["title_norm"]) >= threshold
            entity_match = len(a["_sig"] & head["_sig"]) >= 2
            if title_match or entity_match:
                cluster.append(a)
                placed = True
                break
        if not placed:
            clusters.append([a])

    unique = []
    for cluster in clusters:
        # Keep highest credibility; tie-break by earliest publish date.
        rep = sorted(
            cluster,
            key=lambda x: (-x.get("credibility", 0), x.get("published", "z")),
        )[0]
        rep = dict(rep)
        rep.pop("_sig", None)
        rep["dup_count"] = len(cluster)
        rep["also_reported_by"] = sorted(
            {c.get("publisher", "") for c in cluster if c.get("publisher")}
        )
        unique.append(rep)

    removed = len(articles) - len(unique)
    return unique, removed
