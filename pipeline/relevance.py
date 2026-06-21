"""
Relevance scoring + light deal-fact extraction.

Relevance logic (transparent, rule-based — readable and tunable):
  An article must show BOTH:
    * a DEAL signal  (acquire / merger / stake / buyout / divest / invests ...), AND
    * an FMCG signal (sector term OR a named FMCG company).
  Articles with a deal signal but no FMCG context (e.g. a tech acquisition) are
  filtered out, and vice-versa. This AND-gate is the core of the relevance filter.

Score (0-100) = weighted sum of matched deal terms + matched FMCG terms + company
hits, normalized. A higher score means stronger, clearer FMCG-deal language. The
RELEVANCE_THRESHOLD in config controls the cut-off.

We also do best-effort extraction of acquirer/target, deal value, and category so
the newsletter and CSV are structured rather than just headlines.
"""
from __future__ import annotations

import re

from . import config


def _count_terms(text: str, term_weights: dict[str, int]) -> tuple[int, list[str]]:
    score, hits = 0, []
    for term, w in term_weights.items():
        if term in text:
            score += w
            hits.append(term)
    return score, hits


def _company_hits(text: str) -> list[str]:
    return sorted({c for c in config.FMCG_COMPANIES if c in text})


# ---- deal-fact extraction --------------------------------------------------

_VALUE_RE = re.compile(
    r"(?:(?:US)?\$|usd|eur|€|£|rs\.?|inr)\s?\d[\d,\.]*\s?(?:billion|bn|million|mn|crore|cr|trillion)"
    r"|\d[\d,\.]*\s?(?:billion|bn|million|mn|crore|cr)\s?(?:dollars|euros|rupees)?",
    re.IGNORECASE,
)

# acquirer/target patterns, tried IN ORDER (most specific first).
_ACQ = r"(?P<a>[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,3})"  # 1-4 capitalized words
_QUAL = r"(?:a |an |its |the |majority |minority |remaining |full |\d[\d.]*%\s*)*"
_DEAL_PATTERNS = [
    # "... acquires/buys/raises ... stake in <Target>"
    re.compile(rf"{_ACQ}\s+(?:to acquire|acquires|acquired|buys|to buy|takes|raises|picks up|increases)\s+{_QUAL}stake in\s+(?P<b>[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){{0,3}})"),
    # "... acquisition/takeover/buyout/purchase of <Target>"
    re.compile(rf"{_ACQ}\s+(?:[a-z]+\s+){{0,2}}(?:acquisition|takeover|buyout|purchase)\s+of\s+{_QUAL}(?P<b>[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){{0,3}})"),
    # "... acquires/buys <Target>" (generic; target must start with a letter)
    re.compile(rf"{_ACQ}\s+(?:to acquire|acquires|acquired|buys|to buy|snaps up|takes over)\s+{_QUAL}(?P<b>[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){{0,3}})"),
]

# Words that signal the end of a target name (cut everything from here on).
_TARGET_STOP = re.compile(
    r"\b(in|for|to|worth|amid|as|after|with|from|valued|maker|owner|brand|"
    r"business|unit|deal|stake|expands?|strengthen\w*)\b", re.IGNORECASE
)

_CATEGORY_MAP = {
    "Beauty & Personal Care": ["beauty", "cosmetic", "skincare", "haircare", "personal care", "grooming", "fragrance", "perfume"],
    "Food": ["food", "snack", "confection", "bakery", "dairy", "nutrition", "pasta", "cereal", "chocolate"],
    "Beverages": ["beverage", "drink", "soda", "spirits", "beer", "brewer", "cocktail", "water", "coffee", "tea", "juice"],
    "Home & Household Care": ["household", "home care", "cleaning", "detergent", "hygiene"],
    "Health & Wellness": ["wellness", "supplement", "nutraceutical", "vitamin", "protein"],
    "Pet Care": ["pet food", "pet care", "petcare"],
}


def _extract_value(text: str) -> str:
    m = _VALUE_RE.search(text)
    return m.group(0).strip() if m else ""


_JUNK_NAMES = {"d2c", "us", "uk", "ai", "ceo", "cci", "rs", "inr", "non"}


def _clean_party(name: str) -> str:
    name = name.strip(" .,-")
    cut = _TARGET_STOP.search(name)
    if cut:
        name = name[: cut.start()].strip(" .,-")
    if name.lower() in _JUNK_NAMES:  # generic acronym, not a real brand
        return ""
    return name


def _extract_parties(title: str) -> tuple[str, str]:
    for pat in _DEAL_PATTERNS:
        m = pat.search(title)
        if m:
            a = _clean_party(m.group("a"))
            b = _clean_party(m.group("b"))
            if a and b:
                return a, b
    return "", ""


def _classify_category(text: str) -> str:
    for cat, kws in _CATEGORY_MAP.items():
        if any(k in text for k in kws):
            return cat
    return "Other / Diversified"


def score_article(article: dict) -> dict:
    """Annotate one article with relevance score + extracted deal facts."""
    text = f"{article.get('title_clean', article.get('title',''))} {article.get('summary','')}".lower()

    deal_score, deal_hits = _count_terms(text, config.DEAL_TERMS)
    fmcg_score, fmcg_hits = _count_terms(text, config.FMCG_TERMS)
    companies = _company_hits(text)

    has_deal = deal_score > 0
    has_fmcg = fmcg_score > 0 or len(companies) > 0

    # Normalize to 0-100. Caps keep any single article from dominating.
    raw = min(deal_score, 9) * 5 + min(fmcg_score, 9) * 3 + min(len(companies), 3) * 6
    score = min(100, round(raw / 0.93))  # 0.93 scales the practical max toward 100

    # Gate: must have BOTH a deal signal and an FMCG signal. It then qualifies if
    # the numeric score clears the threshold OR a recognized FMCG company is named
    # (a known major + any deal action is, in practice, a real sector deal).
    relevant = (
        has_deal
        and has_fmcg
        and (score >= config.RELEVANCE_THRESHOLD or len(companies) >= 1)
    )

    acquirer, target = _extract_parties(article.get("title_clean", article.get("title", "")))

    out = dict(article)
    out.update(
        {
            "relevance_score": score,
            "is_relevant": relevant,
            "deal_terms_hit": deal_hits,
            "fmcg_terms_hit": fmcg_hits,
            "companies_hit": companies,
            "acquirer": acquirer,
            "target": target,
            "deal_value": _extract_value(text),
            "category": _classify_category(text),
            "relevance_reason": (
                f"deal={deal_score}({','.join(deal_hits[:4]) or '-'}); "
                f"fmcg={fmcg_score}; companies={len(companies)}"
            ),
        }
    )
    return out


def score_all(articles: list[dict]) -> list[dict]:
    return [score_article(a) for a in articles]


def filter_relevant(articles: list[dict]) -> list[dict]:
    return [a for a in articles if a.get("is_relevant")]
