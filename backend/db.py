import asyncpg, json, unicodedata
from datetime import datetime, timezone

def needs_translation(title: str) -> bool:
    """Returns True if title contains CJK/Korean/Japanese characters."""
    if not title:
        return False
    for c in title:
        if unicodedata.east_asian_width(c) in ('W', 'F'):
            return True
    return False

async def upsert_article(pool, art: dict) -> int:
    translation_status = 'pending' if needs_translation(art.get('title', '')) else 'done'

    # Skip if identical title already exists from same source in last 48h (no freshrss_id)
    if not art.get('freshrss_id'):
        existing = await pool.fetchrow("""
            SELECT id FROM articles
            WHERE lower(trim(title)) = lower(trim($1))
              AND feed_source = $2
              AND published_at > NOW() - INTERVAL '48 hours'
            LIMIT 1
        """, art.get('title', ''), art.get('feed_source', ''))
        if existing:
            return existing['id']

    row = await pool.fetchrow("""
        INSERT INTO articles
          (freshrss_id, feed_source, category, title, url,
           published_at, content_raw, image_url, translation_status)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (freshrss_id) DO UPDATE SET
            title = CASE
                WHEN articles.translation_status = 'done' THEN articles.title
                ELSE EXCLUDED.title
            END,
            feed_source = EXCLUDED.feed_source,
            category = EXCLUDED.category,
            content_raw = EXCLUDED.content_raw,
            image_url = COALESCE(articles.image_url, EXCLUDED.image_url),
            translation_status = CASE
                WHEN articles.translation_status = 'done' THEN 'done'
                WHEN articles.translation_status = 'pending' THEN articles.translation_status
                ELSE EXCLUDED.translation_status
            END,
            translated_at = articles.translated_at,
            original_lang = articles.original_lang,
            original_title = articles.original_title,
            original_content = articles.original_content,
            enriched_at = articles.enriched_at,
            sentiment = articles.sentiment,
            sentiment_score = articles.sentiment_score,
            entities = articles.entities,
            country_code = articles.country_code
        RETURNING id
    """, art["freshrss_id"], art["feed_source"], art["category"],
         art["title"], art["url"], art["published_at"],
         art["content_raw"], art["image_url"], translation_status)
    return row["id"]

async def get_articles(pool, limit=50, offset=0,
                       category=None, search=None, user_id=1) -> list:
    conditions = [
        "a.published_at <= NOW()",
        "a.published_at >= NOW() - INTERVAL '30 days'",
        "(a.translation_status = 'done' OR a.original_lang = 'en')",
        "a.title !~ '[가-힣]'",
        "a.title !~ '[\\u4e00-\\u9fff]'",
        "a.title !~ '[\\u3040-\\u309f]'"
    ]
    params = []
    i = 1
    if category:
        conditions.append(f"a.category = ${i}"); params.append(category); i += 1
    if search:
        conditions.append(f"(a.title ILIKE ${i} OR a.feed_source ILIKE ${i})"); params.append(f"%{search}%"); i += 1
    where = "WHERE " + " AND ".join(conditions)
    params += [user_id, limit, offset]
    rows = await pool.fetch(f"""
        SELECT a.id, a.title, a.feed_source, a.category,
               a.published_at, a.ingested_at, a.content_raw, a.image_url, a.url,
               a.country_code, a.entities, a.sentiment, a.sentiment_score,
               a.original_lang,
               (ur.id IS NOT NULL) as is_read
        FROM articles a
        LEFT JOIN user_reads ur
          ON ur.article_id = a.id AND ur.user_id = ${i}
        {where}
        ORDER BY a.published_at DESC
        LIMIT ${i+1} OFFSET ${i+2}
    """, *params)
    import json as _json
    result = []
    for r in rows:
        row = dict(r)
        if isinstance(row.get('entities'), str):
            try:
                row['entities'] = _json.loads(row['entities'])
            except Exception:
                row['entities'] = []
        if row.get('entities') is None:
            row['entities'] = []
        result.append(row)
    return result

async def get_article_by_id(pool, article_id: int, user_id=1) -> dict | None:
    row = await pool.fetchrow("""
        SELECT a.*, (ur.id IS NOT NULL) as is_read
        FROM articles a
        LEFT JOIN user_reads ur
          ON ur.article_id = a.id AND ur.user_id = $2
        WHERE a.id = $1
    """, article_id, user_id)
    if not row:
        return None
    import json as _json
    result = dict(row)
    if isinstance(result.get('entities'), str):
        try:
            result['entities'] = _json.loads(result['entities'])
        except Exception:
            result['entities'] = []
    if result.get('entities') is None:
        result['entities'] = []
    return result

async def mark_read(pool, user_id: int, article_id: int):
    await pool.execute("""
        INSERT INTO user_reads (user_id, article_id)
        VALUES ($1, $2) ON CONFLICT DO NOTHING
    """, user_id, article_id)

async def get_user_knowledge(pool, user_id=1, domain=None) -> list:
    if domain:
        rows = await pool.fetch("""
            SELECT * FROM user_knowledge
            WHERE user_id=$1 AND domain=$2
            ORDER BY created_at DESC
        """, user_id, domain)
    else:
        rows = await pool.fetch("""
            SELECT * FROM user_knowledge
            WHERE user_id=$1
            ORDER BY created_at DESC
        """, user_id)
    return [dict(r) for r in rows]

async def get_claude_session(pool, user_id: int, article_id: int) -> dict | None:
    row = await pool.fetchrow("""
        SELECT * FROM claude_sessions
        WHERE user_id=$1 AND article_id=$2
        ORDER BY created_at DESC LIMIT 1
    """, user_id, article_id)
    return dict(row) if row else None

async def create_claude_session(pool, user_id: int, article_id: int) -> int:
    row = await pool.fetchrow("""
        INSERT INTO claude_sessions (user_id, article_id)
        VALUES ($1, $2) RETURNING id
    """, user_id, article_id)
    return row["id"]

async def save_claude_session(pool, session_id: int,
                               messages: list, knowledge: list):
    await pool.execute("""
        UPDATE claude_sessions
        SET messages=$1, knowledge_extracted=$2, updated_at=NOW()
        WHERE id=$3
    """, json.dumps(messages), json.dumps(knowledge), session_id)

async def save_knowledge_update(pool, user_id: int, article_id: int,
                                 domain: str, gap_id: str, gap_res: str):
    await pool.execute("""
        INSERT INTO user_knowledge
          (user_id, domain, gap_identified, gap_resolved, source_article)
        VALUES ($1,$2,$3,$4,$5)
    """, user_id, domain, gap_id, gap_res, article_id)
