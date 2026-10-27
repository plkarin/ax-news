"""AX-NEWS tests.

Those that need PostgreSQL run on a database of their own, migrated like a
new install (migrations 001, 003 and 004), and empty its tables: point
AXNEWS_TEST_DATABASE_URL at it. Its name must contain "test", so that a
production database is never emptied by mistake. Without it, they are
skipped and the others run.

    createdb ax_news_test
    for m in 001_schema 003_personal_sources 004_catalog_tv; do psql ax_news_test -f migrations/$m.sql; done
    AXNEWS_TEST_DATABASE_URL=postgresql:///ax_news_test python -m pytest tests
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DB = os.getenv("AXNEWS_TEST_DATABASE_URL", "")
TABLES = "articles, app_meta, user_saves, user_knowledge, feed_catalog, users"


def with_db(test):
    """Runs the async test(pool) on emptied tables."""
    if not DB:
        pytest.skip("AXNEWS_TEST_DATABASE_URL is not set")
    if "test" not in DB.rsplit("/", 1)[-1]:
        pytest.fail("AXNEWS_TEST_DATABASE_URL must name a test database (its name holds 'test')")

    async def go():
        import asyncpg
        pool = await asyncpg.create_pool(DB, min_size=1, max_size=3)
        try:
            await pool.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
            await test(pool)
        finally:
            await pool.close()
    asyncio.run(go())


async def add_story(pool, title, *, url=None, source="Test Source", hours_ago=1.0, ingested_hours_ago=None,
                    content="", owner=None, lang="en", status="done", original_title=None) -> int:
    """A story, published `hours_ago` (negative: in the future)."""
    return await pool.fetchval("""
        INSERT INTO articles (title, url, feed_source, category, content_raw, published_at, ingested_at,
                              owner_user_id, original_lang, translation_status, original_title)
        VALUES ($1, $2, $3, 'Cybersecurity', $4, now() - make_interval(secs => $5),
                now() - make_interval(secs => $6), $7, $8, $9, $10)
        RETURNING id""", title, url or f"https://example.org/{uuid.uuid4().hex}", source,
        content, hours_ago * 3600, (hours_ago if ingested_hours_ago is None else ingested_hours_ago) * 3600,
        owner, lang, status, original_title)


async def add_user(pool, name="reader") -> int:
    return await pool.fetchval("INSERT INTO users (username) VALUES ($1) RETURNING id", name)
