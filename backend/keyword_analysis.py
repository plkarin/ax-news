"""
Keyword-based Bayesian sentiment scoring for AX-NEWS.
Zero AI calls — pure static analysis on title + content.
"""
import re, json, logging
from typing import Optional

logger = logging.getLogger("ax-news")

# ── Keyword dictionaries with weights ─────────────────────────────
KEYWORDS = {
    # Weight +3 — Industry breakthrough
    3: [
        "breakthrough", "revolution", "revolutionary", "historic", "first ever",
        "first in history", "world first", "game changer", "game-changer",
        "paradigm shift", "landmark", "unprecedented", "groundbreaking",
        "major milestone", "disruptive", "transforms", "reinvents",
    ],
    # Weight +2 — Very positive
    2: [
        "record", "record-breaking", "all-time high", "launch", "launches",
        "funding", "raises", "acquisition", "acquires", "merger", "ipo",
        "partnership", "partners with", "growth", "profit", "revenue up",
        "beats expectations", "exceeds", "surpasses", "ahead of schedule",
        "approved", "approval", "cleared", "certified", "wins contract",
        "major deal", "billion dollar", "expands", "expansion", "hiring",
        "new jobs", "investment", "invests", "profitable", "positive results",
    ],
    # Weight +1 — Positive
    1: [
        "new", "announce", "announces", "upgrade", "update", "improve",
        "improvement", "enhance", "enhancement", "release", "releases",
        "progress", "advance", "advances", "support", "supports",
        "agreement", "collaboration", "initiative", "solution", "efficient",
        "cheaper", "faster", "better", "optimized", "boost", "opportunity",
    ],
    # Weight -1 — Negative
    -1: [
        "decline", "declining", "delay", "delayed", "miss", "misses",
        "concern", "concerns", "risk", "risks", "challenge", "challenges",
        "issue", "issues", "problem", "problems", "warning", "warns",
        "disappoints", "disappointing", "below expectations", "shortage",
        "supply chain", "uncertainty", "uncertain", "volatile", "volatility",
        "competition", "competitive pressure", "margin compression",
    ],
    # Weight -2 — Very negative
    -2: [
        "layoff", "layoffs", "laid off", "job cuts", "restructuring",
        "breach", "data breach", "lawsuit", "sues", "sued", "litigation",
        "loss", "losses", "quarterly loss", "annual loss", "recall",
        "fine", "fined", "penalty", "penalized", "investigation",
        "probe", "antitrust", "ban", "banned", "blocked", "rejected",
        "fails", "failure", "missed targets", "profit warning",
        "downgrade", "downgraded", "cut guidance",
    ],
    # Weight -3 — Severe
    -3: [
        "bankruptcy", "bankrupt", "insolvent", "collapse", "collapses",
        "hack", "hacked", "cyberattack", "ransomware", "data stolen",
        "scandal", "fraud", "fraudulent", "corruption", "corrupt",
        "explosion", "fire", "disaster", "crisis", "meltdown",
        "zero-day", "critical vulnerability", "emergency", "catastrophic",
        "catastrophe", "shutdown", "shuts down", "closes down",
    ],
}

# ── Country detection from feed source ────────────────────────────
SOURCE_COUNTRY_MAP = {
    # US
    "techcrunch": "US", "wired": "US", "engadget": "US", "gizmodo": "US",
    "verge": "US", "ars technica": "US", "venturebeat": "US", "cnet": "US",
    "zdnet": "US", "bloomberg": "US", "reuters": "US", "wsj": "US",
    "nytimes": "US", "washington post": "US", "fortune": "US",
    "openai": "US", "anthropic": "US", "google": "US", "microsoft": "US",
    "amazon": "US", "meta": "US", "apple": "US", "nvidia": "US",
    "aws": "US", "azure": "US", "netflix": "US", "uber": "US",
    "github": "US", "hashicorp": "US", "cloudflare": "US",
    "krebs": "US", "sans": "US", "cisa": "US", "nist": "US",
    # Korea
    "aitimes": "KR", "korea": "KR", "joongAng": "KR", "joongang": "KR",
    # Taiwan
    "digitimes": "TW", "trendforce": "TW",
    # Japan
    "nikkei": "JP", "japan": "JP",
    # China
    "huawei": "CN", "alibaba": "CN", "tencent": "CN", "baidu": "CN",
    # Europe
    "sifted": "EU", "eu-startups": "EU", "enisa": "EU",
    "ncsc": "GB", "bbc": "GB", "guardian": "GB",
    "inria": "FR",
    # India
    "yourstory": "IN", "entrackr": "IN",
    # Africa
    "techcabal": "NG", "disrupt africa": "ZA", "techpoint": "NG",
    # Australia
    "startupdaily": "AU", "itnews": "AU",
    # Global
    "ieee": "US", "acm": "US", "arxiv": "GLOBAL",
    "nature": "GB", "science": "US",
    # China
    "it之家": "CN", "ithome": "CN", "mydrivers": "CN",
    "south china morning post": "CN", "scmp": "CN",
    "wire china": "CN", "wirechina": "CN",
    "caixin": "CN", "yicai": "CN",
    # Korea
    "ai타임스": "KR", "aitimes": "KR",
    # Japan
    "nikkei": "JP", "nikkan": "JP",
    # Taiwan
    "digitimes": "TW", "trendforce": "TW",
    # US
    "hacker news": "US", "lobsters": "US", "lobste.rs": "US",
    "tom's hardware": "US", "toms hardware": "US", "latest from tom": "US",
    "anandtech": "US",
    "securityweek": "US",
    "fast company": "US",
    "the block": "US",
    "finextra": "GB",
    "canary media": "US",
    "arxiv machine learning": "GLOBAL",
    "quant-ph": "GLOBAL", "cs.ro": "GLOBAL", "cs.ai": "GLOBAL",
    "cs.lg": "GLOBAL", "cs.cr": "GLOBAL", "cs.ar": "GLOBAL",
    "the diplomat": "US",
    "blog": "US",
    "latest news": "GLOBAL",
}

# ── Entity detection ───────────────────────────────────────────────
KNOWN_ENTITIES = [
    # Chips & Hardware
    "Nvidia", "AMD", "Intel", "Qualcomm", "Broadcom", "TSMC", "Samsung",
    "SK Hynix", "Micron", "ASML", "ARM", "MediaTek", "Marvell", "Ampere",
    "Apple Silicon", "RISC-V",
    # Cloud & Infra
    "AWS", "Azure", "Google Cloud", "Cloudflare", "Fastly", "Akamai",
    # AI companies
    "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Mistral",
    "Hugging Face", "Cohere", "xAI", "Stability AI", "Scale AI",
    # Big Tech
    "Apple", "Google", "Microsoft", "Meta", "Amazon", "Tesla", "SpaceX",
    "Netflix", "Uber", "Lyft", "Airbnb", "Stripe", "Palantir",
    # Cybersecurity
    "CrowdStrike", "Palo Alto", "SentinelOne", "Mandiant", "Fortinet",
    "Check Point", "Splunk", "Okta", "Zscaler",
    # Asia tech
    "Huawei", "Alibaba", "Tencent", "Baidu", "Xiaomi", "ByteDance",
    "TikTok", "SoftBank", "Sony", "Panasonic", "Foxconn",
    # Dev tools
    "GitHub", "GitLab", "Docker", "Kubernetes", "HashiCorp", "Grafana",
    # Telecom
    "Ericsson", "Nokia", "Qualcomm", "T-Mobile", "Verizon",
    # Fintech & Crypto
    "Stripe", "Visa", "Mastercard", "PayPal", "Square", "Coinbase",
    "Binance", "Ripple", "Ethereum", "Bitcoin", "BlockFi",
    # Cloud & SaaS
    "Salesforce", "ServiceNow", "Snowflake", "Databricks", "MongoDB",
    "Redis", "Elastic", "Datadog", "New Relic", "PagerDuty",
    "Twilio", "Zoom", "Slack", "Notion", "Figma", "Canva",
    # AI extended
    "Gemini", "GPT-4", "Claude", "Llama", "Grok", "Copilot",
    "Midjourney", "Stable Diffusion", "DALL-E", "Sora",
    "Perplexity", "Character.AI", "Inflection",
    # Semiconductors extended
    "RISC-V", "x86", "ARM", "CUDA", "ROCm", "TPU", "NPU",
    "HBM", "CoWoS", "3nm", "2nm", "GAA", "FinFET",
    "Blackwell", "Hopper", "Lovelace", "Raptor Lake",
    # Cybersecurity
    "Log4j", "CVE", "zero-day", "ransomware", "phishing",
    "NSA", "FBI", "Europol", "Interpol",
    # EV & Energy
    "Tesla", "Rivian", "Lucid", "BYD", "NIO", "CATL",
    "Li-ion", "solid-state battery", "lithium",
    # Space
    "SpaceX", "Starlink", "Blue Origin", "Rocket Lab",
    "NASA", "ESA", "JAXA", "ISRO",
    # Social & Media
    "Twitter", "X Corp", "LinkedIn", "Reddit", "Pinterest",
    "Snap", "TikTok", "YouTube", "Twitch",
    # Enterprise
    "Oracle", "SAP", "IBM", "Dell", "HP", "Lenovo", "Asus",
    "Cisco", "Juniper", "VMware", "Broadcom",
    # AI products & models
    "ChatGPT", "DeepSeek", "Gemma", "Mistral", "Phi-4",
    # Autonomous & Robotics
    "Waymo", "Cruise", "Aurora", "Mobileye", "Nuro",
    # Hardware brands
    "MSI", "ASUS ROG", "Corsair", "Logitech", "Razer",
    "Western Digital", "Seagate", "Kingston",
    # Semiconductor research
    "imec", "Lam Research", "Applied Materials", "KLA",
    # Consumer products
    "iPhone", "iPad", "MacBook", "Pixel", "Galaxy",
    "Windows", "Linux", "Android", "iOS",
    # Gaming
    "Epic Games", "Unreal Engine", "Unity", "Steam", "Valve",
    "PlayStation", "Xbox", "Nintendo",
    # Finance & Banking
    "ECB", "Fed", "Federal Reserve", "IMF", "World Bank",
    "JPMorgan", "Goldman Sachs", "BlackRock",
    # Telecom & Networking
    "Wi-Fi", "5G", "6G", "Qualcomm Snapdragon",
    # Open source & Dev
    "WebAssembly", "WASM", "Rust", "Python", "Go",
]

def _normalize(text: str) -> str:
    """Lowercase and remove extra whitespace."""
    return re.sub(r'\s+', ' ', text.lower().strip())

def detect_country(feed_source: str, title: str) -> str:
    """Detect country from feed source name."""
    src = _normalize(feed_source or "")
    for key, country in SOURCE_COUNTRY_MAP.items():
        if key.lower() in src:
            return country
    return "GLOBAL"

def detect_entities(title: str, content: str) -> list:
    """Find known entities mentioned in title and content."""
    text = (title or "") + " " + (content or "")[:2000]
    found = []
    for entity in KNOWN_ENTITIES:
        pattern = r'\b' + re.escape(entity) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            found.append(entity)
    return found[:5]  # Max 5 entities

def compute_sentiment(title: str, content: str) -> tuple[str, float]:
    """
    Bayesian keyword scoring.
    Returns (sentiment_label, confidence_score 0.0-1.0)
    """
    # Use title with 3x weight, content with 1x weight
    title_text = _normalize(title or "")
    content_text = _normalize((content or "")[:3000])

    positive_score = 0.0
    negative_score = 0.0

    for weight, keywords in KEYWORDS.items():
        for kw in keywords:
            # Title match (weighted 3x)
            title_count = len(re.findall(r'\b' + re.escape(kw) + r'\b', title_text))
            # Content match (weighted 1x)
            content_count = len(re.findall(r'\b' + re.escape(kw) + r'\b', content_text))
            total = (title_count * 3 + content_count) * abs(weight)
            if weight > 0:
                positive_score += total
            else:
                negative_score += total

    total_score = positive_score + negative_score

    # Bayesian probability: P(positive) = pos / (pos + neg)
    if total_score == 0:
        return "neutral", 0.5

    p_positive = positive_score / total_score

    # Map to sentiment levels based on raw score magnitude and p_positive
    magnitude = total_score

    if p_positive >= 0.85 and magnitude >= 6:
        return "breakthrough", round(p_positive, 3)
    elif p_positive >= 0.75:
        return "very_positive", round(p_positive, 3)
    elif p_positive >= 0.60:
        return "positive", round(p_positive, 3)
    elif p_positive <= 0.15 and magnitude >= 6:
        return "very_negative", round(1 - p_positive, 3)
    elif p_positive <= 0.30:
        return "very_negative" if magnitude >= 4 else "negative", round(1 - p_positive, 3)
    elif p_positive <= 0.42:
        return "negative", round(1 - p_positive, 3)
    else:
        return "neutral", 0.5

def enrich_article_static(article: dict) -> dict:
    """
    Full static enrichment of one article.
    Returns dict with country_code, entities, sentiment, sentiment_score.
    """
    title = article.get("title", "") or ""
    content = article.get("content_raw", "") or ""
    feed_source = article.get("feed_source", "") or ""

    # Strip HTML from content
    clean_content = re.sub(r'<[^>]+>', ' ', content)
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()

    country_code = detect_country(feed_source, title)
    entities = detect_entities(title, clean_content)
    sentiment, score = compute_sentiment(title, clean_content)

    return {
        "country_code": country_code,
        "entities": entities,
        "sentiment": sentiment,
        "sentiment_score": score,
    }

async def enrich_batch_static(pool, limit: int = 200) -> int:
    """
    Enrich articles without sentiment using static keyword analysis.
    Fast — no AI calls, no subprocess. Can process 1000+ articles in seconds.
    """
    rows = await pool.fetch("""
        SELECT id, title, content_raw, feed_source
        FROM articles
        WHERE enriched_at IS NULL
        ORDER BY published_at DESC
        LIMIT $1
    """, limit)

    count = 0
    for row in rows:
        result = enrich_article_static(dict(row))
        await pool.execute("""
            UPDATE articles
            SET country_code    = $1,
                entities        = $2::jsonb,
                sentiment       = $3,
                sentiment_score = $4,
                enriched_at     = NOW()
            WHERE id = $5
        """,
            result["country_code"],
            json.dumps(result["entities"]),
            result["sentiment"],
            result["sentiment_score"],
            row["id"]
        )
        count += 1

    return count
