#!/usr/bin/env python3
"""Posts each breaking CVE (a new CVE scored 8+, backend/cve.py) to
Mastodon and/or Bluesky, once, with a link to its page on AX-NEWS.
Run by ax-news-social.timer every 5 minutes.

Off until the accounts are set in backend/.env:
  MASTODON_BASE_URL=https://infosec.exchange   MASTODON_TOKEN=…   (scope write:statuses)
  BLUESKY_HANDLE=axnews.bsky.social            BLUESKY_APP_PASSWORD=…   (an app password)

Mastodon: at most one public post an hour (infosec.exchange's rule for
automated accounts, 24 a day); the others of the hour go out "unlisted",
which reaches followers without the public timelines.
MASTODON_VISIBILITY=unlisted makes every post unlisted.
"""
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parent
from dotenv import load_dotenv
load_dotenv(APP / "backend" / ".env")

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("social-worker")
HOST = os.getenv("APP_URL", "https://ax-news.com").rstrip("/")
LOCAL = os.getenv("AXNEWS_LOCAL_URL", "http://127.0.0.1:8000")


def text_for(b: dict, limit: int) -> str:
    sev = f"Critical {b['cvss']:.1f}" + (" · exploited" if b.get("kev") else "")
    lines = [f"🚨 Breaking: {b['label']} — {sev}"]
    if b.get("impact"):
        lines.append("Impacted if: " + b["impact"][0])
    if b.get("theme"):
        lines.append(b["theme"])
    url = f"{HOST}/cve/{b['label']}"
    tail = f"\n{url}\n#CVE #infosec"
    body = "\n".join(lines)
    if len(body) + len(tail) > limit:
        body = body[: limit - len(tail) - 1].rstrip() + "…"
    return body + tail


def mastodon_on() -> bool:
    return bool(os.getenv("MASTODON_BASE_URL") and os.getenv("MASTODON_TOKEN"))


def bluesky_on() -> bool:
    return bool(os.getenv("BLUESKY_HANDLE") and os.getenv("BLUESKY_APP_PASSWORD"))


async def mastodon(client, b, visibility) -> bool:
    base, token = os.getenv("MASTODON_BASE_URL"), os.getenv("MASTODON_TOKEN")
    r = await client.post(f"{base.rstrip('/')}/api/v1/statuses", headers={"Authorization": f"Bearer {token}",
                          "Idempotency-Key": f"ax-news-{b['label']}"},
                          data={"status": text_for(b, 500), "visibility": visibility, "language": "en"})
    log.info("mastodon %s (%s) → HTTP %s", b["label"], visibility, r.status_code)
    return r.status_code < 300


async def bluesky(client, b) -> bool:
    handle, password = os.getenv("BLUESKY_HANDLE"), os.getenv("BLUESKY_APP_PASSWORD")
    s = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                          json={"identifier": handle, "password": password})
    if s.status_code >= 300:
        log.warning("bluesky session: HTTP %s", s.status_code)
        return False
    sess = s.json()
    text = text_for(b, 300)
    # Links and tags are "facets", addressed in UTF-8 bytes.
    facets = []
    raw = text.encode()
    for m in re.finditer(rb"https?://\S+", raw):
        facets.append({"index": {"byteStart": m.start(), "byteEnd": m.end()},
                       "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group().decode()}]})
    for m in re.finditer(rb"#(\w+)", raw):
        facets.append({"index": {"byteStart": m.start(), "byteEnd": m.end()},
                       "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1).decode()}]})
    record = {"$type": "app.bsky.feed.post", "text": text, "langs": ["en"], "facets": facets,
              "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                          headers={"Authorization": f"Bearer {sess['accessJwt']}"},
                          json={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record})
    log.info("bluesky %s → HTTP %s", b["label"], r.status_code)
    return r.status_code < 300


async def main():
    if not (mastodon_on() or bluesky_on()):
        log.info("no Mastodon or Bluesky account set: nothing posted")
        return
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        state = await pool.fetchval("SELECT value FROM app_meta WHERE key = 'social_posted'")
        state = json.loads(state) if state else {}
        if "posts" not in state:
            # v1.3.0 kept {cve: when}, one date for both networks.
            state = {"posts": {k: {"mastodon": v, "bluesky": v} for k, v in state.items()}}
        posts = state["posts"]
        now = datetime.now(timezone.utc)
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "AX-NEWS social-worker"}) as client:
            feed = (await client.get(f"{LOCAL}/api/tv/public/feed")).json()
            for b in feed.get("breaking") or []:
                done = posts.setdefault(b["label"], {})
                # A network that failed is tried again on the next run, while the CVE is still breaking.
                if mastodon_on() and "mastodon" not in done:
                    last = state.get("mastodon_public")
                    hour_free = not last or (now - datetime.fromisoformat(last)).total_seconds() >= 3600
                    visibility = os.getenv("MASTODON_VISIBILITY") or "public"
                    if visibility == "public" and not hour_free:
                        visibility = "unlisted"
                    if await mastodon(client, b, visibility):
                        done["mastodon"] = now.isoformat()
                        if visibility == "public":
                            state["mastodon_public"] = now.isoformat()
                if bluesky_on() and "bluesky" not in done:
                    if await bluesky(client, b):
                        done["bluesky"] = now.isoformat()
        # Remember a week of posts.
        cutoff = now.timestamp() - 7 * 86400
        state["posts"] = {k: v for k, v in posts.items()
                          if v and max(datetime.fromisoformat(t).timestamp() for t in v.values()) > cutoff}
        await pool.execute("""INSERT INTO app_meta (key, value) VALUES ('social_posted', $1)
                              ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""", json.dumps(state))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
