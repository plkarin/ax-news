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

async def drop_duplicates(pool, new: list[dict], owner: int | None) -> tuple[list[dict], int]:
    """The new items that duplicate nothing of their owner's (None: the
    shared feeds), stored or earlier in the batch, by dedup-worker.sh's rule:
    the same address, or the same title from the same source within 12
    hours. Returns (the others, oldest first; how many were left out)."""
    new = sorted(new, key=lambda a: (a.get("published_at") or datetime.max.replace(tzinfo=timezone.utc),
                                     a.get("freshrss_id") or ""))
    urls = {r["url"] for r in await pool.fetch(
        "SELECT url FROM articles WHERE url = ANY($1::text[]) AND owner_user_id IS NOT DISTINCT FROM $2",
        [a["url"] for a in new if a.get("url")], owner)}
    titles: dict = {}
    for r in await pool.fetch("""
            SELECT feed_source, lower(trim(title)) AS t, published_at FROM articles
             WHERE lower(trim(title)) = ANY($1::text[]) AND owner_user_id IS NOT DISTINCT FROM $2""",
            list({(a.get("title") or "").strip().lower() for a in new}), owner):
        titles.setdefault((r["feed_source"], r["t"]), []).append(r["published_at"])
    keep, duplicates = [], 0
    for a in new:
        t = (a.get("feed_source"), (a.get("title") or "").strip().lower())
        when = a.get("published_at")
        same_title = any(when and p and abs((when - p).total_seconds()) <= 12 * 3600 for p in titles.get(t, []))
        if (a.get("url") and a["url"] in urls) or same_title:
            duplicates += 1
            continue
        keep.append(a)
        if a.get("url"):
            urls.add(a["url"])                 # the same story twice in this batch
        titles.setdefault(t, []).append(when)
    return keep, duplicates


async def store_shared(pool, arts: list[dict]) -> dict:
    """The items of the FreshRSS sync (the shared feeds), in one pass. It reads
    FreshRSS's last 15,000 items every ten minutes, so:
    - an item already stored (its freshrss_id) is updated only when its feed
      changed it, and keeps a translation already made;
    - a new item whose address is already stored, or whose title is, from
      the same source, within 12 hours, is a duplicate and is left out
      (dedup-worker.sh used to delete it every hour, and the next sync
      brought it back: some 1,450 at all times);
    - the others are inserted.
    Only those inserts take a number from articles_id_seq: an INSERT … ON
    CONFLICT took one per item, 2 million a day, toward the int4 ceiling.
    Returns {"inserted", "updated", "duplicates"}."""
    from catalog import FEED_LANGS
    arts = [a for a in arts if a.get("freshrss_id")]
    if not arts:
        return {"inserted": 0, "updated": 0, "duplicates": 0}
    known = {r["freshrss_id"] for r in await pool.fetch(
        "SELECT freshrss_id FROM articles WHERE freshrss_id = ANY($1::text[])", [a["freshrss_id"] for a in arts])}
    old = [a for a in arts if a["freshrss_id"] in known]
    updated = 0
    if old:
        # Only rows whose feed changed something; a translated story keeps
        # its English title and text (the original is in original_*).
        updated = int((await pool.execute("""
            UPDATE articles a SET
                title = CASE WHEN a.translation_status = 'done' THEN a.title ELSE u.title END,
                feed_source = u.feed_source,
                category = u.category,
                content_raw = CASE WHEN a.translation_status = 'done' AND a.original_lang IS DISTINCT FROM 'en'
                                        AND a.original_content IS NOT NULL THEN a.content_raw
                                   ELSE u.content_raw END,
                image_url = COALESCE(a.image_url, u.image_url)
              FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[])
                   AS u(fid, feed_source, category, title, content_raw, image_url)
             WHERE a.freshrss_id = u.fid
               AND (a.feed_source IS DISTINCT FROM u.feed_source
                    OR a.category IS DISTINCT FROM u.category
                    OR (a.translation_status IS DISTINCT FROM 'done' AND a.title IS DISTINCT FROM u.title)
                    OR (NOT (a.translation_status = 'done' AND a.original_lang IS DISTINCT FROM 'en'
                             AND a.original_content IS NOT NULL)
                        AND a.content_raw IS DISTINCT FROM u.content_raw)
                    OR (a.image_url IS NULL AND u.image_url IS NOT NULL))""",
            [a["freshrss_id"] for a in old], [a["feed_source"] for a in old], [a["category"] for a in old],
            [a["title"] for a in old], [a["content_raw"] for a in old], [a["image_url"] for a in old])).split()[-1])

    keep, duplicates = await drop_duplicates(pool, [a for a in arts if a["freshrss_id"] not in known], None)
    inserted = 0
    if keep:
        langs = [FEED_LANGS.get(a.get("feed_source") or "") for a in keep]
        status = ["pending" if (lang or needs_translation(a.get("title", ""))) else "done" for a, lang in zip(keep, langs)]
        inserted = len(await pool.fetch("""
            INSERT INTO articles (freshrss_id, feed_source, category, title, url, published_at,
                                  content_raw, image_url, translation_status, original_lang)
            SELECT * FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::timestamptz[],
                                 $7::text[], $8::text[], $9::text[], $10::text[])
            ON CONFLICT (freshrss_id) DO NOTHING
            RETURNING id""",
            [a["freshrss_id"] for a in keep], [a["feed_source"] for a in keep], [a["category"] for a in keep],
            [a["title"] for a in keep], [a["url"] for a in keep], [a["published_at"] for a in keep],
            [a["content_raw"] for a in keep], [a["image_url"] for a in keep], status, langs))
    return {"inserted": inserted, "updated": updated, "duplicates": duplicates}

# Who may see an article: everyone if it came from the shared feeds
# (owner_user_id IS NULL), only its owner if it came from their own sources.
PUBLIC = "a.owner_user_id IS NULL"
VISIBLE = [
    "a.published_at <= NOW()",
    "a.published_at >= NOW() - INTERVAL '30 days'",
    "(a.translation_status = 'done' OR a.original_lang = 'en')",
    "a.title !~ '[가-힣]'",
    "a.title !~ '[\\u4e00-\\u9fff]'",
    "a.title !~ '[\\u3040-\\u309f]'",
]


import re as _re
_CJK = _re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def _json_list(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v or []


def excerpt(html: str, n: int = 320) -> str:
    """Plain text of an article's HTML, cut on a word near n characters."""
    import html as html_lib, re
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", html_lib.unescape(text)).strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:.-–—") + "…"


def paragraphs(html: str, limit: int = 12000) -> list[str]:
    """An article's text as plain paragraphs, for the reader: no markup from
    a feed is ever rendered as HTML."""
    import html as html_lib, re
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<\s*(br|/p|/div|/li|/h[1-6]|/blockquote)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)[:limit]
    out = [re.sub(r"[ \t\u00a0]+", " ", p).strip() for p in text.split("\n")]
    return [p for p in out if len(p) > 1]


def reading_minutes(html: str) -> int:
    words = len(excerpt(html, 10**9).split())
    return max(1, round(words / 220))


async def get_articles(pool, limit=50, offset=0, category=None, search=None,
                       user_id=0, scope="public", source=None, feed_id=None,
                       saved=False, since=None, count_only=False):
    """Articles a reader sees, newest first.

    scope: "public" (the shared feeds), "mine" (the reader's own sources),
    "all" (both). source: a feed's name; feed_id: one of the reader's own
    sources. saved: only those the reader saved. since: only newer ones."""
    conditions = list(VISIBLE)
    params = []

    def arg(v):
        params.append(v)
        return f"${len(params)}"

    uid = arg(user_id or 0)
    # Typed once here: a count of public articles uses $1 nowhere else, and
    # PostgreSQL refuses a parameter it cannot type.
    conditions.append(f"{uid}::int IS NOT NULL")
    if scope == "mine":
        conditions.append(f"a.owner_user_id = {uid}")
    elif scope == "all":
        conditions.append(f"(a.owner_user_id IS NULL OR a.owner_user_id = {uid})")
    else:
        conditions.append(PUBLIC)
    if saved:
        conditions[:] = [c for c in conditions if "30 days" not in c]
        conditions.append(f"EXISTS (SELECT 1 FROM user_saves s WHERE s.article_id = a.id AND s.user_id = {uid})")
    if category:
        conditions.append(f"a.category = {arg(category)}")
    if source:
        conditions.append(f"a.feed_source = {arg(source)}")
    if feed_id:
        conditions.append(f"a.user_feed_id = {arg(feed_id)} AND a.owner_user_id = {uid}")
    if search:
        q = arg(f"%{search}%")
        conditions.append(f"(a.title ILIKE {q} OR a.feed_source ILIKE {q})")
    if since:
        conditions.append(f"a.published_at > {arg(since)}")
    where = "WHERE " + " AND ".join(conditions)
    if count_only:
        return await pool.fetchval(f"SELECT count(*) FROM articles a {where}", *params)
    lim, off = arg(limit), arg(offset)
    rows = await pool.fetch(f"""
        SELECT a.id, a.title, a.feed_source, a.category,
               a.published_at, a.ingested_at, left(a.content_raw, 4000) AS content_raw,
               a.image_url, a.url, a.country_code, a.entities, a.sentiment,
               a.sentiment_score, a.original_lang, a.view_count,
               a.owner_user_id IS NOT NULL AS personal, a.user_feed_id,
               EXISTS (SELECT 1 FROM user_reads ur WHERE ur.article_id = a.id AND ur.user_id = {uid}) AS is_read,
               EXISTS (SELECT 1 FROM user_saves us WHERE us.article_id = a.id AND us.user_id = {uid}) AS is_saved
        FROM articles a
        {where}
        ORDER BY a.published_at DESC
        LIMIT {lim} OFFSET {off}
    """, *params)
    result = []
    for r in rows:
        row = dict(r)
        row["entities"] = _json_list(row.get("entities"))
        # Some feeds send their titles HTML-escaped ("&#x5b;Guest Diary&#x5d;").
        import html as html_lib
        row["title"] = html_lib.unescape(row.get("title") or "")
        html = row.pop("content_raw") or ""
        row["excerpt"] = excerpt(html)
        # A translated title over a text still in its first language reads
        # badly: no excerpt then.
        if row.get("original_lang") not in (None, "en") and _CJK.search(row["excerpt"]):
            row["excerpt"] = ""
        row["reading_minutes"] = reading_minutes(html)
        result.append(row)
    return result


async def get_article_by_id(pool, article_id: int, user_id=0) -> dict | None:
    """One article, if this reader may see it."""
    row = await pool.fetchrow("""
        SELECT a.*,
               EXISTS (SELECT 1 FROM user_reads ur WHERE ur.article_id = a.id AND ur.user_id = $2) AS is_read,
               EXISTS (SELECT 1 FROM user_saves us WHERE us.article_id = a.id AND us.user_id = $2) AS is_saved
        FROM articles a
        WHERE a.id = $1 AND (a.owner_user_id IS NULL OR a.owner_user_id = $2)
    """, article_id, user_id or 0)
    if not row:
        return None
    result = dict(row)
    result["entities"] = _json_list(result.get("entities"))
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


async def purge_old(pool, days: int) -> int:
    """Delete the stories older than `days`, except those someone saved
    (user_saves would lose them, ON DELETE CASCADE). A knowledge note keeps
    its text and loses its link to the story (user_knowledge.source_article
    has no ON DELETE rule)."""
    old = """coalesce(published_at, ingested_at) < NOW() - make_interval(days => $1)
             AND NOT EXISTS (SELECT 1 FROM user_saves s WHERE s.article_id = articles.id)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"""
                UPDATE user_knowledge SET source_article = NULL
                WHERE source_article IN (SELECT id FROM articles WHERE {old})""", days)
            result = await conn.execute(f"DELETE FROM articles WHERE {old}", days)
    return int(result.split()[-1])
