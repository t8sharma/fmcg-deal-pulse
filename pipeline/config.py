"""
Central configuration for the FMCG Deal Intelligence pipeline.

Everything that controls *what* we look for and *how* we score it lives here so the
logic stays transparent and easy to tune. No API keys are required.
"""

# ---------------------------------------------------------------------------
# 1. INGESTION — search queries and feeds
# ---------------------------------------------------------------------------
# Google News RSS is keyless and free. Each query below becomes one RSS pull.
# Queries are deliberately scoped to FMCG + deal language to keep noise low.
GOOGLE_NEWS_QUERIES = [
    "FMCG acquisition",
    "FMCG merger",
    "consumer packaged goods acquisition",
    "consumer goods M&A deal",
    "food beverage company acquires",
    "personal care brand acquisition",
    "beauty brand acquired",
    "FMCG D2C brand stake acquisition",
    "packaged food company merger",
    "household products company acquisition",
    "FMCG private equity investment",
    "consumer staples divestiture",
]

# Optional extra RSS feeds (trade press). These work without keys too.
# They are best-effort: if a feed is unreachable it is skipped silently.
EXTRA_RSS_FEEDS = [
    # "https://www.foodbev.com/feed/",
    # "https://www.fooddive.com/feeds/news/",
]

# Google News RSS endpoint template (hl/gl/ceid control language & region).
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)

# How many days back to keep an article (recency window for "latest developments").
RECENCY_DAYS = 45

# Network politeness
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; FMCG-DealIntel/1.0)"


# ---------------------------------------------------------------------------
# 2. RELEVANCE — FMCG context terms and deal-action terms
# ---------------------------------------------------------------------------
# An article is relevant only if it shows BOTH a deal signal AND an FMCG signal.
# Weights let stronger signals (e.g. "acquisition") count more than weak ones.

DEAL_TERMS = {
    "acquire": 3, "acquires": 3, "acquired": 3, "acquisition": 3, "acquisitions": 3,
    "merger": 3, "merges": 3, "merge": 2, "to buy": 3, "buys": 3, "bought": 2,
    "buyout": 3, "take-private": 3, "take private": 3, "takeover": 3,
    "majority stake": 3, "minority stake": 2, "stake in": 2, "acquires stake": 3,
    "divest": 2, "divestiture": 2, "divestment": 2, "spin-off": 2, "spinoff": 2,
    "sells": 2, "sale of": 2, "sells stake": 3, "carve-out": 2, "carveout": 2,
    "invests": 2, "investment in": 2, "funding round": 2, "raises": 1,
    "series a": 1, "series b": 1, "series c": 1, "deal": 1, "transaction": 1,
}

# FMCG / CPG sector context terms (categories + sector labels).
FMCG_TERMS = {
    "fmcg": 3, "cpg": 3, "consumer packaged goods": 3, "consumer goods": 2,
    "consumer staples": 2, "packaged food": 2, "packaged foods": 2,
    "food": 1, "beverage": 2, "beverages": 2, "snack": 2, "snacks": 2,
    "dairy": 2, "confectionery": 2, "personal care": 3, "beauty": 2,
    "cosmetics": 2, "skincare": 2, "haircare": 2, "grooming": 2,
    "household products": 2, "home care": 2, "nutrition": 2, "wellness": 1,
    "d2c": 2, "direct-to-consumer": 2, "grocery": 1, "spirits": 2, "brewer": 2,
    "pet food": 2, "supplements": 2, "nutraceutical": 2,
}

# Known FMCG players — strong FMCG signal if named.
FMCG_COMPANIES = {
    "unilever", "nestle", "nestlé", "procter & gamble", "p&g", "pepsico", "pepsi",
    "coca-cola", "coca cola", "mondelez", "mars", "kellanova", "kellogg", "ferrero",
    "danone", "general mills", "kraft heinz", "colgate", "colgate-palmolive",
    "reckitt", "l'oreal", "l'oréal", "estee lauder", "estée lauder", "beiersdorf",
    "henkel", "church & dwight", "clorox", "conagra", "campbell", "hershey",
    "molson coors", "constellation brands", "anheuser-busch", "diageo", "pernod ricard",
    "treehouse foods", "post holdings", "hindustan unilever", "hul", "itc",
    "marico", "dabur", "emami", "godrej", "britannia", "nestle india", "tata consumer",
    "patanjali", "varun beverages", "cvc capital", "advent international",
    "investindustrial", "the man company", "minimalist", "plix", "oziva",
    "wellbeing nutrition", "yoga bar", "mamaearth", "honasa", "boat", "sugar cosmetics",
}

# Aliases → canonical company name. Used by de-duplication so "HUL" and
# "Hindustan Unilever" count as the same entity when matching duplicate stories.
COMPANY_ALIASES = {
    "hul": "hindustan unilever",
    "p&g": "procter & gamble",
    "coca cola": "coca-cola",
    "nestlé": "nestle",
    "l'oréal": "l'oreal",
    "estée lauder": "estee lauder",
}

# Pass threshold (0-100). Tune to trade recall vs precision. A named FMCG company
# plus a deal action also qualifies regardless of this score (see relevance.py).
RELEVANCE_THRESHOLD = 30


# ---------------------------------------------------------------------------
# 3. CREDIBILITY — source tiers
# ---------------------------------------------------------------------------
# Transparent, assumption-driven tiers. Unknown domains get a cautious default.
# Score is on 0-1; surfaced in outputs so a reader can judge for themselves.

CREDIBILITY_TIERS = {
    1.00: [  # Tier 1: major wires, financial press, primary filings
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "apnews.com",
        "cnbc.com", "nikkei.com", "forbes.com", "economist.com",
        "economictimes.indiatimes.com", "business-standard.com", "livemint.com",
        "moneycontrol.com", "sec.gov", "businesswire.com", "prnewswire.com",
        "thehindubusinessline.com", "financialexpress.com",
    ],
    0.75: [  # Tier 2: established trade / industry press
        "foodbev.com", "fooddive.com", "just-food.com", "bakeryandsnacks.com",
        "beveragedaily.com", "foodbusinessnews.net", "consumergoods.com",
        "wwd.com", "beautymatter.com", "businessoffashion.com", "cosmeticsbusiness.com",
        "grocerydive.com", "supermarketnews.com", "foodnavigator.com",
        "inc42.com", "storyboard18.com", "afaqs.com", "exchange4media.com",
        "foodinstitute.com", "massmarketretailers.com", "spglobal.com",
        "themorningcontext.com", "pwc.com", "mckinsey.com", "bain.com",
    ],
    0.50: [  # Tier 3: general / regional outlets, aggregators
        "yahoo.com", "msn.com", "businessinsider.com", "thehindu.com",
        "timesofindia.indiatimes.com", "hindustantimes.com", "ndtv.com",
        "indiatimes.com", "medium.com",
    ],
}

# Default credibility for any domain not listed above.
DEFAULT_CREDIBILITY = 0.40

# Minimum credibility to include in the newsletter (raw data keeps everything).
CREDIBILITY_FLOOR = 0.40


# ---------------------------------------------------------------------------
# 4. DEDUPLICATION
# ---------------------------------------------------------------------------
# Two articles are "near-duplicates" if their normalized-title similarity is at or
# above this threshold. We combine token Jaccard overlap and difflib sequence ratio.
NEAR_DUP_THRESHOLD = 0.72


# ---------------------------------------------------------------------------
# 5. NEWSLETTER
# ---------------------------------------------------------------------------
NEWSLETTER_TITLE = "FMCG Deal Pulse"
NEWSLETTER_SUBTITLE = "Recent M&A & Investment Activity in Fast-Moving Consumer Goods"
TOP_DEALS_COUNT = 10  # how many ranked deals to feature
