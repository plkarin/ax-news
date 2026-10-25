#!/usr/bin/env python3
"""Personal sources worker: fetches every account's due sources
(backend/sources.py) and stores their entries as that account's articles.
Run by ax-news-sources.timer every 5 minutes; a source is due every 15
minutes, less often after errors. Runs never overlap (a oneshot unit)."""
import asyncio
import logging
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP / "backend"))

from dotenv import load_dotenv
load_dotenv(APP / "backend" / ".env")

import asyncpg
import sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("sources-worker")
logging.getLogger("httpx").setLevel(logging.WARNING)
CONCURRENCY = 4


async def main():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=CONCURRENCY + 1)
    try:
        due = await sources.due_sources(pool)
        if not due:
            log.info("no source due")
            return
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(feed):
            async with sem:
                r = await asyncio.wait_for(sources.fetch_source(pool, feed), 60)
                log.info("source %s (%s): %s", feed["id"], feed["name"][:40],
                         f"{r.get('new', 0)} new, {r['items']} in all" if r["ok"] else r["error"])
                return r["ok"]

        results = await asyncio.gather(*(one(f) for f in due), return_exceptions=True)
        ok = sum(1 for r in results if r is True)
        log.info("%d sources fetched, %d failed", ok, len(results) - ok)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
