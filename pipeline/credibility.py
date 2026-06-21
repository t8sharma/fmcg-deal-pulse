"""
Source credibility scoring.

We keep this deliberately simple and transparent: a domain-tier lookup plus a
publisher-name fallback. Every score ships with a human-readable reason so a
business reader can see *why* a source was rated the way it was — and override the
tiers in config.py if they disagree.

Assumptions (stated openly):
  * Major wires / financial press / primary filings (Reuters, Bloomberg, FT, SEC,
    company newswires) are most reliable for deal facts -> 1.00.
  * Established industry/trade press is reliable for sector deals -> 0.75.
  * General/regional outlets and aggregators -> 0.50.
  * Anything unrecognized gets a cautious default (0.40) — not zero, because an
    unknown outlet is not necessarily wrong, just unverified.
"""
from __future__ import annotations

from . import config

# Flatten the tier map into {domain: score} once at import time.
_DOMAIN_SCORE: dict[str, float] = {}
for _score, _domains in config.CREDIBILITY_TIERS.items():
    for _d in _domains:
        _DOMAIN_SCORE[_d] = _score

_TIER_LABEL = {1.00: "Tier 1 (wire/financial/primary)",
               0.75: "Tier 2 (trade press)",
               0.50: "Tier 3 (general/regional)"}


def score_credibility(domain: str, publisher: str = "") -> tuple[float, str]:
    """Return (score 0-1, reason)."""
    domain = (domain or "").lower()
    publisher = (publisher or "").lower()

    # 1. Exact domain match.
    if domain in _DOMAIN_SCORE:
        s = _DOMAIN_SCORE[domain]
        return s, f"{_TIER_LABEL.get(s, 'rated')}: {domain}"

    # 2. Suffix match (covers regional editions, e.g. edition.cnn.com).
    for d, s in _DOMAIN_SCORE.items():
        if domain.endswith("." + d) or domain == d:
            return s, f"{_TIER_LABEL.get(s, 'rated')}: matched {d}"

    # 3. Publisher-name fallback (Google News sometimes gives name, not domain).
    for d, s in _DOMAIN_SCORE.items():
        brand = d.split(".")[0]
        if brand and brand in publisher.replace(" ", ""):
            return s, f"{_TIER_LABEL.get(s, 'rated')}: publisher '{publisher}'"

    return config.DEFAULT_CREDIBILITY, f"Unrecognized source ({domain or publisher or 'unknown'}) — default"
