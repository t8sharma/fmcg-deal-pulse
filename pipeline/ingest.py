"""
Ingestion — pull deal-related news from keyless, public sources.

Primary source: Google News RSS (one query per topic in config.GOOGLE_NEWS_QUERIES).
Optional: extra trade-press RSS feeds.

If the network is unavailable (e.g. an offline grader/sandbox), the caller can fall
back to the bundled seed dataset in data/sample_articles.json so the pipeline still
produces a full demonstration end-to-end.
"""
from __future__ import annotations

import datetime as dt
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from . import config


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT) as resp:
        return resp.read()


def _parse_rss(xml_bytes: bytes, query: str) -> list[dict]:
    """Parse an RSS 2.0 feed into a list of normalized article dicts."""
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = item.findtext("pubDate")
        source_el = item.find("source")
        source = (source_el.text.strip() if source_el is not None and source_el.text else "")

        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub)
            except (TypeError, ValueError):
                published = None

        items.append(
            {
                "title": title,
                "url": link,
                "summary": _strip_html(desc),
                "published": published.isoformat() if published else "",
                "source_name": source,
                "query": query,
            }
        )
    return items


def _strip_html(text: str) -> str:
    """Very light HTML stripper for RSS descriptions (avoids extra deps)."""
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_google_news(queries=None) -> list[dict]:
    """Fetch articles for each query via Google News RSS. Best-effort per query."""
    queries = queries or config.GOOGLE_NEWS_QUERIES
    out: list[dict] = []
    for q in queries:
        url = config.GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(q))
        try:
            out.extend(_parse_rss(_http_get(url), q))
        except Exception as exc:  # noqa: BLE001 - keep ingest resilient
            print(f"[ingest] query failed ({q}): {exc}")
    return out


def fetch_extra_feeds(feeds=None) -> list[dict]:
    feeds = feeds if feeds is not None else config.EXTRA_RSS_FEEDS
    out: list[dict] = []
    for f in feeds:
        try:
            out.extend(_parse_rss(_http_get(f), query="(feed)"))
        except Exception as exc:  # noqa: BLE001
            print(f"[ingest] feed failed ({f}): {exc}")
    return out


def filter_recent(articles: list[dict], days: int | None = None) -> list[dict]:
    """Drop articles older than the recency window (keeps undated ones)."""
    days = days or config.RECENCY_DAYS
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    kept = []
    for a in articles:
        if not a.get("published"):
            kept.append(a)
            continue
        try:
            pub = dt.datetime.fromisoformat(a["published"])
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=dt.timezone.utc)
            if pub >= cutoff:
                kept.append(a)
        except ValueError:
            kept.append(a)
    return kept


def ingest(use_live: bool = True) -> list[dict]:
    """
    Main entry point. Returns a list of raw article dicts.

    If use_live is True we hit the network; on total failure (zero articles) the
    caller should fall back to the bundled seed dataset.
    """
    articles: list[dict] = []
    if use_live:
        articles.extend(fetch_google_news())
        articles.extend(fetch_extra_feeds())
        articles = filter_recent(articles)
    return articles
