#!/usr/bin/env python3
"""Posts the CVE watch to Mastodon and/or Bluesky, from /api/cve/watch, each
item once, with a link to its page on AX-NEWS. Run by ax-news-social.timer
every 5 minutes. Three kinds of posts:
- a breaking CVE: newly published, scored 8+, first reported in the last
  hour (backend/cve.py);
- a CVE CISA has just added to its catalog of Known Exploited
  Vulnerabilities: exploited in the wild. Not when it was posted as breaking
  in the last 24 hours;
- once a day, at SOCIAL_DIGEST_AT (08:30) in SOCIAL_TZ (Europe/Paris), the
  three CVEs that mattered the day before. SOCIAL_DIGEST_AT=off: none.
  SOCIAL_KEV=0: no KEV posts.

Off until the accounts are set in backend/.env:
  MASTODON_BASE_URL=https://infosec.exchange   MASTODON_TOKEN=…   (scope write:statuses)
  BLUESKY_HANDLE=axnews.bsky.social            BLUESKY_APP_PASSWORD=…   (an app password)

At most PER_HOUR posts an hour on each network, breaking CVEs first, the
most severe first. Mastodon: one of them public (the rule of infosec.exchange
for automated accounts, 24 a day), the others "unlisted", which reaches
followers without the public timelines; the daily post waits for the public
slot. MASTODON_VISIBILITY=unlisted makes every post unlisted.
"""
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
PER_HOUR = 3
DIGEST_HOURS = 3.5      # the daily post's window: 08:30 to 12:00
KEV_AFTER_BREAKING = 24 * 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def rating(b: dict) -> str:
    """The CVSS rating (High 7–8.9, Critical 9–10), not the TV's CRITICAL."""
    sev = b.get("base_severity") or ("CRITICAL" if b["cvss"] >= 9 else "HIGH")
    return f"{sev.title()} {b['cvss']:.1f}"


def _fit(body: str, tail: str, limit: int) -> str:
    if len(body) + len(tail) > limit:
        body = body[: limit - len(tail) - 1].rstrip() + "…"
    return body + tail


def text_for(b: dict, limit: int) -> str:
    """A breaking CVE."""
    sev = rating(b) + (" · exploited" if b.get("kev") else "")
    lines = [f"🚨 Breaking: {b['label']} — {sev}"]
    if b.get("impact"):
        lines.append("Impacted if: " + b["impact"][0])
    if b.get("theme"):
        lines.append(b["theme"])
    return _fit("\n".join(lines), f"\n{HOST}/cve/{b['label']}\n#CVE #infosec", limit)


def kev_text(k: dict, limit: int) -> str:
    """A CVE just added to CISA's KEV catalog."""
    lines = [f"⚠️ Exploited in the wild: {k['label']}"]
    if k.get("name"):
        lines.append(k["name"])
    facts = ["Added to CISA KEV"] + ([rating(k)] if k.get("cvss") is not None else []) \
        + (["used by ransomware"] if k.get("ransomware") else [])
    lines.append(" · ".join(facts))
    if k.get("impact"):
        lines.append("Impacted if: " + k["impact"][0])
    return _fit("\n".join(lines), f"\n{HOST}/cve/{k['label']}\n#CVE #KEV #infosec", limit)


def digest_text(day: dict, limit: int) -> str:
    """The CVEs that mattered on day["date"]: names shortened, then left
    out, until it fits."""
    d = datetime.fromisoformat(day["date"])
    head = f"🛡️ The CVEs that mattered · {d:%A} {d.day} {d:%B}"
    tail = f"\n{HOST}/cve\n#CVE #infosec"

    def line(i, c, width):
        bits = [c["label"]] + ([rating(c)] if c.get("cvss") is not None else []) + (["exploited"] if c.get("kev") else [])
        name = c.get("product") or ""
        if width is not None and len(name) > width:
            name = name[:width - 1].rstrip() + "…" if width else ""
        return f"{i}. " + " · ".join(bits) + (f" — {name}" if name else "")
    for width in (None, 24, 14, 0):
        body = "\n".join([head] + [line(i, c, width) for i, c in enumerate(day["top"], 1)])
        if len(body) + len(tail) <= limit:
            break
    return _fit(body, tail, limit)


def mastodon_on() -> bool:
    return bool(os.getenv("MASTODON_BASE_URL") and os.getenv("MASTODON_TOKEN"))


def bluesky_on() -> bool:
    return bool(os.getenv("BLUESKY_HANDLE") and os.getenv("BLUESKY_APP_PASSWORD"))


async def mastodon(client, key: str, text: str, visibility: str) -> bool:
    base, token = os.getenv("MASTODON_BASE_URL"), os.getenv("MASTODON_TOKEN")
    r = await client.post(f"{base.rstrip('/')}/api/v1/statuses", headers={"Authorization": f"Bearer {token}",
                          "Idempotency-Key": f"ax-news-{key}"},
                          data={"status": text, "visibility": visibility, "language": "en"})
    log.info("mastodon %s (%s) → HTTP %s", key, visibility, r.status_code)
    return r.status_code < 300


async def bluesky(client, key: str, text: str) -> bool:
    handle, password = os.getenv("BLUESKY_HANDLE"), os.getenv("BLUESKY_APP_PASSWORD")
    s = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                          json={"identifier": handle, "password": password})
    if s.status_code >= 300:
        log.warning("bluesky session: HTTP %s", s.status_code)
        return False
    sess = s.json()
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
              "createdAt": _now().isoformat().replace("+00:00", "Z")}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                          headers={"Authorization": f"Bearer {sess['accessJwt']}"},
                          json={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record})
    log.info("bluesky %s → HTTP %s", key, r.status_code)
    return r.status_code < 300


async def attempt(network, call) -> bool:
    """One network down, or a bad credential, must not stop the other one."""
    try:
        return await call
    except Exception as e:
        log.warning("%s: %s: %s", network, type(e).__name__, str(e)[:200])
        return False


def _digest_window(now: datetime) -> tuple[bool, bool, datetime]:
    """(is it time for the daily post, is its window nearly over, the day it covers)."""
    zone = ZoneInfo(os.getenv("SOCIAL_TZ") or "Europe/Paris")
    local = now.astimezone(zone)
    at = (os.getenv("SOCIAL_DIGEST_AT") or "08:30").strip()
    if at.lower() in ("off", "0", "no", "none"):
        return False, False, local - timedelta(days=1)
    h, m = (int(x) for x in at.split(":"))
    start = local.replace(hour=h, minute=m, second=0, microsecond=0)
    end = start + timedelta(hours=DIGEST_HOURS)
    return start <= local < end, local >= end - timedelta(minutes=15), local - timedelta(days=1)


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
        now = _now()
        digest_time, digest_late, covered = _digest_window(now)
        async with httpx.AsyncClient(timeout=60, headers={"User-Agent": "AX-NEWS social-worker"}) as client:
            r = await client.get(f"{LOCAL}/api/cve/watch",
                                 params={"day": covered.date().isoformat(), "tz": str(covered.tzinfo)})
            r.raise_for_status()
            watch = r.json()

            def room(network: str) -> bool:
                last_hour = sum(1 for v in posts.values() if network in v
                                and (now - datetime.fromisoformat(v[network])).total_seconds() < 3600)
                return last_hour < PER_HOUR

            def recently_breaking(cid: str) -> bool:
                v = posts.get(cid) or {}
                return any((now - datetime.fromisoformat(t)).total_seconds() < KEV_AFTER_BREAKING for t in v.values())

            # (key in the state, texts for Mastodon and Bluesky, a daily post?)
            todo = []
            # The most severe first; exploited in the wild before the others at the same score.
            for b in sorted(watch.get("breaking") or [],
                            key=lambda b: (-b["cvss"], not b.get("kev"), b.get("first_seen") or "")):
                todo.append((b["label"], text_for(b, 500), text_for(b, 300), False))
            # The daily post before CISA's additions, which can wait an hour.
            day = watch.get("day") or {}
            if digest_time and day.get("top"):
                todo.append(("digest:" + day["date"], digest_text(day, 500), digest_text(day, 300), True))

            if os.getenv("SOCIAL_KEV", "1") != "0":
                for k in watch.get("kev_added") or []:
                    key = "kev:" + k["label"]
                    if "skipped" in posts.get(key, {}) or not k.get("ready", True):
                        continue
                    if key not in posts and recently_breaking(k["label"]):
                        posts[key] = {"skipped": now.isoformat()}   # said already, as breaking news
                        continue
                    todo.append((key, kev_text(k, 500), kev_text(k, 300), False))
            for key, long_text, short_text, daily in todo:
                done = posts.setdefault(key, {})
                # A network that failed, or had no room left this hour, is tried
                # again on the next run, while the item is still wanted.
                if mastodon_on() and "mastodon" not in done and room("mastodon"):
                    last = state.get("mastodon_public")
                    hour_free = not last or (now - datetime.fromisoformat(last)).total_seconds() >= 3600
                    visibility = os.getenv("MASTODON_VISIBILITY") or "public"
                    if visibility == "public" and not hour_free:
                        visibility = "unlisted"
                    # The daily post waits for the public slot, until its window nearly closes.
                    if not (daily and visibility == "unlisted" and not os.getenv("MASTODON_VISIBILITY")
                            and not digest_late):
                        if await attempt("mastodon", mastodon(client, key, long_text, visibility)):
                            done["mastodon"] = now.isoformat()
                            if visibility == "public":
                                state["mastodon_public"] = now.isoformat()
                if bluesky_on() and "bluesky" not in done and room("bluesky"):
                    if await attempt("bluesky", bluesky(client, key, short_text)):
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
