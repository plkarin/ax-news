import asyncio, json, logging, re
logger = logging.getLogger("ax-news")

ENRICH_PROMPT = """Analyse this tech news article and return ONLY a JSON object, no explanation, no markdown.

Article title: {title}
Article source: {source}
Article content (first 1500 chars): {content}

Return this exact JSON structure:
{{
  "country_code": "US",
  "entities": ["Nvidia", "TSMC"],
  "sentiment": "positive",
  "sentiment_score": 0.75
}}

Rules:
- country_code: 2-letter ISO code. Rules in order:

  If article is about a specific company, use that company's HQ country
  (Nvidia/Apple/Google/Meta/Microsoft/Amazon/Tesla/OpenAI/Anthropic = US,
  Samsung/SK Hynix/LG/Kakao/Naver = KR, TSMC/MediaTek/Foxconn/ASUS/Acer = TW,
  Huawei/Alibaba/Tencent/Baidu/Xiaomi/ByteDance/DJI/SMIC = CN,
  Sony/Toyota/SoftBank/NTT/Fujitsu/Renesas/NEC = JP,
  SAP/Siemens/Bosch/Infineon/Deutsche Telekom = DE,
  ARM/DeepMind/Rolls-Royce/BT/Vodafone/BAE = GB,
  ASML/NXP/Philips = NL, Ericsson/Spotify/Klarna = SE,
  Nokia/F-Secure = FI, STMicroelectronics/Stellantis = FR,
  Tata/Infosys/Wipro/Reliance = IN)
  If event happened in a specific country, use that country
  If purely global/multi-country with no dominant country, use "GLOBAL"
  Never use GLOBAL if a clear company or location is identified.
- entities: list of up to 5 company/organization names mentioned as main subjects.
  Use official short names: "Nvidia" not "NVIDIA Corporation", "Apple" not "Apple Inc."
  Return [] if no specific company is the main subject.
- sentiment: one of these exact values:
  "breakthrough"   — major industry-changing announcement, paradigm shift
  "very_positive"  — strong positive news (major deal, record earnings, breakthrough product)
  "positive"       — generally positive news (new product, partnership, growth)
  "neutral"        — informational, analysis, no clear positive/negative
  "negative"       — concerning news (layoffs, loss, recall, failure)
  "very_negative"  — severe negative (security breach, massive loss, scandal, bankruptcy)
- sentiment_score: float 0.0 to 1.0 representing confidence/intensity
  breakthrough=1.0, very_positive=0.85, positive=0.65, neutral=0.5, negative=0.35, very_negative=0.15

Return ONLY the JSON object. No other text."""


async def enrich_article(article: dict, claude_user: str = "cbrain") -> dict | None:
    title = article.get("title", "")
    source = article.get("feed_source", "")
    raw = article.get("content_raw", "") or ""
    content = re.sub(r"<[^>]+>", " ", raw)
    content = re.sub(r"\s+", " ", content).strip()[:1500]

    prompt = ENRICH_PROMPT.format(title=title, source=source, content=content)

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")), timeout=60
        )
        text = stdout.decode("utf-8", errors="replace").strip()

        json_match = re.search(r'\{[^{}]*"country_code"[^{}]*\}', text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if not json_match:
            logger.warning(f"No JSON in enrichment response for: {title[:50]}")
            return None

        data = json.loads(json_match.group())

        valid_sentiments = {"breakthrough","very_positive","positive","neutral","negative","very_negative"}
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in valid_sentiments:
            sentiment = "neutral"

        entities = data.get("entities", [])
        if not isinstance(entities, list):
            entities = []
        entities = [str(e).strip() for e in entities if e][:5]

        score = float(data.get("sentiment_score", 0.5))
        score = max(0.0, min(1.0, score))

        return {
            "country_code": str(data.get("country_code", "GLOBAL"))[:10],
            "entities": entities,
            "sentiment": sentiment,
            "sentiment_score": score,
        }

    except asyncio.TimeoutError:
        logger.warning(f"Enrichment timeout for: {title[:50]}")
        return None
    except Exception as e:
        logger.error(f"Enrichment error for {title[:50]}: {e}")
        return None


async def enrich_batch(pool, limit: int = 15):
    rows = await pool.fetch("""
        SELECT id, title, feed_source, content_raw
        FROM articles
        WHERE enriched_at IS NULL
        ORDER BY published_at DESC
        LIMIT $1
    """, limit)

    count = 0
    for row in rows:
        result = await enrich_article(dict(row))
        if result:
            await pool.execute("""
                UPDATE articles
                SET country_code    = $1,
                    entities        = $2::jsonb,
                    sentiment       = $3,
                    sentiment_score = $4,
                    enriched_at     = NOW()
                WHERE id = $5
            """, result["country_code"],
                json.dumps(result["entities"]),
                result["sentiment"],
                result["sentiment_score"],
                row["id"])
            count += 1
            logger.info(f"Enriched [{result['sentiment']}] {row['title'][:60]}")
        else:
            await pool.execute(
                "UPDATE articles SET enriched_at = NOW() WHERE id = $1", row["id"]
            )
    return count
