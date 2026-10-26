#!/usr/bin/env python3
"""Tells search engines what changed, through IndexNow (Bing, Yandex, Seznam,
Naver…): the pages of our own sitemaps that are new or have a new lastmod
since the last run. Run by ax-news-seo.timer every hour.

The key proves the site: https://ax-news.com/<key>.txt (backend/main.py),
derived from INTERNAL_SYNC_TOKEN. Google does not take IndexNow: it reads
the sitemaps (declared in robots.txt and in Search Console)."""
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
from dotenv import load_dotenv
load_dotenv(APP / "backend" / ".env")

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("seo-worker")
HOST = os.getenv("APP_URL", "https://ax-news.com").rstrip("/")
LOCAL = os.getenv("AXNEWS_LOCAL_URL", "http://127.0.0.1:8000")
KEY = hashlib.sha256(("ax-news-indexnow:" + (os.getenv("INTERNAL_SYNC_TOKEN") or "dev")).encode()).hexdigest()[:32]


async def sitemap_urls(client) -> dict:
    """{url: lastmod} from our own sitemaps."""
    out = {}
    index = (await client.get(f"{LOCAL}/sitemap.xml")).text
    for sm in re.findall(r"<loc>([^<]+)</loc>", index):
        path = re.sub(r"^https?://[^/]+", "", sm)
        body = (await client.get(LOCAL + path)).text
        for block in re.findall(r"<url>(.*?)</url>", body, re.S):
            loc = re.search(r"<loc>([^<]+)</loc>", block)
            mod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
            if loc:
                out[loc.group(1)] = mod.group(1) if mod else ""
    return out


async def main():
    if not os.getenv("INTERNAL_SYNC_TOKEN"):
        log.info("no INTERNAL_SYNC_TOKEN: no IndexNow key, nothing sent")
        return
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        sent = await pool.fetchval("SELECT value FROM app_meta WHERE key = 'indexnow_sent'")
        sent = json.loads(sent) if sent else {}
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "AX-NEWS seo-worker"}) as client:
            urls = await sitemap_urls(client)
            # Hourly pages (home, topics, digest…) have no lastmod that moves:
            # they are sent once a day.
            import time
            day = time.strftime("%Y-%m-%d")
            fresh = [u for u, m in urls.items() if sent.get(u) != (m or day)]
            if not fresh:
                log.info("nothing new (%d pages known)", len(urls))
                return
            for i in range(0, len(fresh), 5000):
                batch = fresh[i:i + 5000]
                r = await client.post("https://api.indexnow.org/indexnow", json={
                    "host": re.sub(r"^https?://", "", HOST), "key": KEY,
                    "keyLocation": f"{HOST}/{KEY}.txt", "urlList": batch})
                log.info("IndexNow: %d urls → HTTP %s", len(batch), r.status_code)
                if r.status_code not in (200, 202):
                    log.warning("IndexNow refused: %s", r.text[:200])
                    return
                for u in batch:
                    sent[u] = urls[u] or day
        # Forget pages that left the sitemaps.
        sent = {u: m for u, m in sent.items() if u in urls}
        await pool.execute("""INSERT INTO app_meta (key, value) VALUES ('indexnow_sent', $1)
                              ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""", json.dumps(sent))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
