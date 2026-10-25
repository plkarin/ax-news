#!/usr/bin/env python3
"""One-off: give a picture to the articles of the last 30 days that have
none, from the <img> in their own HTML (freshrss.extract_image). Before
2026-10-25 the extraction never matched, so most articles came in without a
picture. Only sets image_url where it is empty.

    backend/venv/bin/python deploy/backfill-images.py
"""
import asyncio
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP / "backend"))
from dotenv import load_dotenv
load_dotenv(APP / "backend" / ".env")
import asyncpg
import freshrss


async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch("""
        SELECT id, content_raw FROM articles
         WHERE image_url IS NULL AND content_raw ~* '<img'
           AND published_at > NOW() - INTERVAL '30 days'""")
    done = 0
    for r in rows:
        url = freshrss.extract_image(r["content_raw"])
        if url:
            await conn.execute("UPDATE articles SET image_url = $1 WHERE id = $2 AND image_url IS NULL", url, r["id"])
            done += 1
    print(f"{done} of {len(rows)} articles given a picture")
    await conn.close()


asyncio.run(main())
