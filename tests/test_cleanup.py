"""dedup-worker.sh and the purge (backend/db.py)."""
import os
import subprocess

from conftest import DB, ROOT, add_story, add_user, with_db

import db


def dedup():
    out = subprocess.run(["bash", str(ROOT / "dedup-worker.sh")], env={**os.environ, "DATABASE_URL": DB},
                         capture_output=True, text=True, check=True).stdout
    return out


def test_dedup():
    async def t(pool):
        reader = await add_user(pool)
        first = await add_story(pool, "A paper", url="https://arxiv.org/abs/1", source="arXiv cs.LG", hours_ago=30)
        cross_list = await add_story(pool, "A paper", url="https://arxiv.org/abs/1", source="arXiv cs.AI", hours_ago=29)
        renewed_id = await add_story(pool, "A post (renewed id)", url="https://arxiv.org/abs/1", hours_ago=28)
        private = await add_story(pool, "A paper", url="https://arxiv.org/abs/1", source="arXiv cs.LG", owner=reader)
        saved = await add_story(pool, "A paper", url="https://arxiv.org/abs/1", source="arXiv cs.LG", hours_ago=2)
        await pool.execute("INSERT INTO user_saves (user_id, article_id) VALUES ($1, $2)", reader, saved)
        twice = await add_story(pool, "Same story", url="https://x.org/a", hours_ago=5)
        tracking = await add_story(pool, "Same story", url="https://x.org/a?utm=1", hours_ago=4)
        weekly_1 = await add_story(pool, "Week in review", url="https://x.org/w1", hours_ago=24 * 14)
        weekly_2 = await add_story(pool, "Week in review", url="https://x.org/w2", hours_ago=24 * 7)
        daily = await add_story(pool, "Week in review", url="https://x.org/w3", hours_ago=24 * 7 - 20)
        future = await add_story(pool, "From a wrong time zone", hours_ago=-7, ingested_hours_ago=0.1)

        out = dedup()
        assert "duplicates deleted: 3" in out and "future dates set to arrival: 1" in out
        left = {r["id"] for r in await pool.fetch("SELECT id FROM articles")}
        assert {cross_list, renewed_id, tracking}.isdisjoint(left)
        assert {first, private, saved, twice, weekly_1, weekly_2, daily, future} <= left
        late = await pool.fetchval("SELECT published_at <= now() FROM articles WHERE id = $1", future)
        assert late
        assert "duplicates deleted: 0" in dedup()                  # nothing twice
    with_db(t)


def test_purge():
    async def t(pool):
        reader = await add_user(pool)
        old = await add_story(pool, "Old", hours_ago=24 * 100)
        old_saved = await add_story(pool, "Old but saved", hours_ago=24 * 100)
        old_noted = await add_story(pool, "Old, in a note", hours_ago=24 * 100)
        recent = await add_story(pool, "Recent", hours_ago=24 * 10)
        await pool.execute("INSERT INTO user_saves (user_id, article_id) VALUES ($1, $2)", reader, old_saved)
        note = await pool.fetchval("""INSERT INTO user_knowledge (id, user_id, domain, source_article)
                                      VALUES (1, $1, 'security', $2) RETURNING id""", reader, old_noted)

        assert await db.purge_old(pool, 90) == 2
        left = {r["id"] for r in await pool.fetch("SELECT id FROM articles")}
        assert left == {old_saved, recent}
        assert old not in left and old_noted not in left
        assert await pool.fetchval("SELECT source_article FROM user_knowledge WHERE id = $1", note) is None
    with_db(t)
