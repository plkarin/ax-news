"""Storing the sync's items (db.store_shared) and a source's entries
(sources.store_entries): duplicates left out, unchanged rows untouched, and
no number taken from articles_id_seq but by an insert."""
from datetime import datetime, timedelta, timezone

from conftest import add_story, add_user, with_db

import catalog
import db
import sources

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def item(fid, url, title="A story", source="Feed A", hours_ago=1.0, content="<p>Text</p>", image=None):
    return {"freshrss_id": fid, "feed_source": source, "category": "Technology", "title": title, "url": url,
            "published_at": NOW - timedelta(hours=hours_ago), "content_raw": content, "image_url": image}


async def seq(pool):
    return await pool.fetchval("SELECT pg_sequence_last_value('articles_id_seq')")


def test_store_shared():
    async def t(pool):
        batch = [item("f1", "https://x.org/1"), item("f2", "https://x.org/2", "Another story"),
                 item("f3", "https://x.org/1", "A story, cross-listed", "Feed B"),      # same address
                 item("f4", "https://x.org/4", "Another story", hours_ago=3),           # same title within 12 h
                 item("f5", "https://x.org/5", "Another story", hours_ago=24 * 7)]     # a week before: a column
        assert await db.store_shared(pool, batch) == {"inserted": 3, "updated": 0, "duplicates": 2}
        # Of two copies, the first published stays (dedup-worker.sh keeps the first too).
        assert {r["freshrss_id"] for r in await pool.fetch("SELECT freshrss_id FROM articles")} == {"f1", "f4", "f5"}

        # Ten minutes later, the same items: nothing written, no number taken.
        before = await seq(pool)
        xmin = await pool.fetchval("SELECT xmin::text FROM articles WHERE freshrss_id = 'f4'")
        assert await db.store_shared(pool, batch) == {"inserted": 0, "updated": 0, "duplicates": 2}
        assert await seq(pool) == before
        assert await pool.fetchval("SELECT xmin::text FROM articles WHERE freshrss_id = 'f4'") == xmin

        # A feed edits a story: it is updated, still without a new number.
        batch[0] = item("f1", "https://x.org/1", content="<p>Text, corrected</p>", image="https://x.org/1.jpg")
        assert (await db.store_shared(pool, batch))["updated"] == 1
        row = await pool.fetchrow("SELECT content_raw, image_url FROM articles WHERE freshrss_id = 'f1'")
        assert row["content_raw"] == "<p>Text, corrected</p>" and row["image_url"] == "https://x.org/1.jpg"
        assert await seq(pool) == before

        # A translated story keeps its English title and text.
        await pool.execute("""UPDATE articles SET title = 'In English', content_raw = '<p>English</p>',
                              original_title = 'Another story', original_content = '<p>Text</p>',
                              original_lang = 'fr', translation_status = 'done' WHERE freshrss_id = 'f4'""")
        assert (await db.store_shared(pool, batch))["updated"] == 0
        assert await pool.fetchval("SELECT title FROM articles WHERE freshrss_id = 'f4'") == "In English"
    with_db(t)


def test_store_shared_language(monkeypatch):
    monkeypatch.setitem(catalog.FEED_LANGS, "Le Monde", "fr")

    async def t(pool):
        await db.store_shared(pool, [item("f6", "https://lemonde.fr/1", "Un titre", "Le Monde"),
                                     item("f7", "https://x.org/7", "华为发布新品")])
        rows = {r["freshrss_id"]: r for r in await pool.fetch(
            "SELECT freshrss_id, translation_status, original_lang FROM articles")}
        assert (rows["f6"]["translation_status"], rows["f6"]["original_lang"]) == ("pending", "fr")
        assert rows["f7"]["translation_status"] == "pending"
    with_db(t)


def test_store_entries():
    async def t(pool):
        reader = await add_user(pool)
        feed_id = await pool.fetchval("""INSERT INTO user_feeds (freshrss_id, name, url, user_id)
                                         VALUES ('src', 'My blog', 'https://blog.example/feed', $1) RETURNING id""", reader)
        feed = {"id": feed_id, "name": "My blog", "url": "https://blog.example/feed",
                "site_url": "https://blog.example/", "user_id": reader, "lang": None}
        # The shared feed has a story at the same address: another owner, so not a duplicate.
        await add_story(pool, "Shared", url="https://blog.example/3")
        entries = [{"id": "e1", "title": "One", "link": "https://blog.example/1"},
                   {"id": "e2", "title": "Two", "link": "https://blog.example/1"},           # same address
                   {"id": "e3", "title": "Three", "link": "https://blog.example/3"}]
        assert await sources.store_entries(pool, feed, entries) == (2, 2)
        before = await seq(pool)
        assert await sources.store_entries(pool, feed, entries) == (0, 2)              # again: nothing
        assert await seq(pool) == before
        # A picture the entry gained is filled in.
        entries[0]["media_thumbnail"] = [{"url": "https://blog.example/1.jpg"}]
        await sources.store_entries(pool, feed, entries)
        assert await pool.fetchval("SELECT image_url FROM articles WHERE url = 'https://blog.example/1' AND owner_user_id = $1",
                                   reader) == "https://blog.example/1.jpg"
        assert await seq(pool) == before
    with_db(t)
