"""
Personal sources: each account's own feeds.

A source is an RSS or Atom feed, or something that can be turned into one:
a YouTube channel, a subreddit, a Mastodon account, a GitHub repository's
releases, Hacker News, or any website that announces its feed. discover()
turns what the user typed into feeds they can choose from; fetch_source()
reads one and stores its entries as that account's own articles
(articles.owner_user_id), never in the public feed.

Every address here comes from a user, so every request goes through
safe_get(): http and https only, on the usual ports, to a public address
only. The address is checked before each request and after each redirect,
and the connection is pinned to the address that was checked, so a name
that resolves differently a moment later cannot reach this server's own
network. Responses are capped in size and time.
"""
import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
from calendar import timegm
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse, quote

import feedparser
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("ax-news.sources")

UA = "AX-NEWS/2.0 (+https://ax-news.com; personal sources)"
MAX_BYTES = 5_000_000
TIMEOUT = httpx.Timeout(12.0, connect=6.0)
MAX_REDIRECTS = 5
PORTS = {80, 443, 8080, 8443}
MAX_ENTRIES = 100
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json",
              "application/xml", "text/xml")


class SourceError(Exception):
    """Something the user can be told: why this address gives no feed."""


# ── Safe fetching ─────────────────────────────────────────────────────────────

def _allowed_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_global and not a.is_multicast


async def _resolve(host: str, port: int) -> str:
    try:
        ipaddress.ip_address(host)
        raise SourceError("Use the site's name, not its IP address.")
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise SourceError(f"{host}: no such site.")
    ips = sorted({i[4][0] for i in infos})
    if not ips:
        raise SourceError(f"{host}: no such site.")
    if not all(_allowed_ip(ip) for ip in ips):
        raise SourceError(f"{host}: this address is not reachable from here.")
    # IPv4 first: the server's IPv6 route is not guaranteed.
    ips.sort(key=lambda ip: ":" in ip)
    return ips[0]


async def safe_get(url: str, headers: dict | None = None):
    """GET a user-supplied URL. Returns (final_url, status, headers, body)."""
    for _ in range(MAX_REDIRECTS + 1):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise SourceError("Only http:// and https:// addresses can be added.")
        if p.username or p.password:
            raise SourceError("Addresses with a user name or password cannot be added.")
        port = p.port or (443 if p.scheme == "https" else 80)
        if port not in PORTS:
            raise SourceError("This port is not allowed.")
        host = p.hostname.lower()
        ip = await _resolve(host, port)
        netloc = (f"[{ip}]" if ":" in ip else ip) + f":{port}"
        target = urlunparse((p.scheme, netloc, p.path or "/", p.params, p.query, ""))
        h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en,fr;q=0.8",
             "Host": host if p.port in (None, 80, 443) else f"{host}:{p.port}"}
        h.update(headers or {})
        ext = {"sni_hostname": host} if p.scheme == "https" else {}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
                async with c.stream("GET", target, headers=h, extensions=ext) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise SourceError("The answer is too large to be a feed.")
                    return url, r.status_code, {k.lower(): v for k, v in r.headers.items()}, bytes(body)
        except httpx.TimeoutException:
            raise SourceError(f"{host} did not answer in time.")
        except httpx.HTTPError as e:
            raise SourceError(f"{host} could not be reached ({type(e).__name__}).")
    raise SourceError("Too many redirects.")


# ── What the user typed → candidate feed URLs ─────────────────────────────────

def _with_scheme(text: str) -> str:
    return text if re.match(r"^https?://", text, re.I) else "https://" + text


def candidates(text: str) -> list[tuple[str, str]]:
    """[(kind, url)] to try, most likely first. URLs of the page itself are
    tried as a feed and as a website announcing its feed."""
    t = text.strip()
    if not t:
        return []
    if re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I) and not re.match(r"^https?://", t, re.I):
        raise SourceError("Only http:// and https:// addresses can be added.")
    low = t.lower()
    if low in ("hn", "hacker news", "hackernews") or re.match(r"^(https?://)?news\.ycombinator\.com/?$", low):
        return [("hackernews", "https://hnrss.org/frontpage")]
    m = re.match(r"^(?:https?://)?news\.ycombinator\.com/(newest|best|ask|show|jobs)", low)
    if m:
        return [("hackernews", f"https://hnrss.org/{m.group(1)}")]
    m = re.match(r"^/?r/([A-Za-z0-9_]{2,21})/?$", t) or \
        re.match(r"^(?:https?://)?(?:www\.|old\.|new\.)?reddit\.com/r/([A-Za-z0-9_]{2,21})", t, re.I)
    if m:
        return [("reddit", f"https://www.reddit.com/r/{m.group(1)}/.rss")]
    m = re.match(r"^@([\w.]+)@([\w.-]+\.[a-z]{2,})$", t, re.I)
    if m:
        return [("mastodon", f"https://{m.group(2)}/@{m.group(1)}.rss")]
    m = re.match(r"^(?:https?://)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:$|[?#]|/releases|/tags|/commits)", t, re.I)
    if m:
        return [("github", f"https://github.com/{m.group(1)}/{m.group(2)}/releases.atom")]
    m = re.match(r"^(?:https?://)?(?:www\.|m\.)?youtube\.com/channel/(UC[\w-]{22})", t, re.I)
    if m:
        return [("youtube", f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}")]
    if re.match(r"^(?:https?://)?(?:www\.|m\.)?youtube\.com/(@[\w.-]+|c/[\w.-]+|user/[\w.-]+)", t, re.I) or re.match(r"^@[\w.-]+$", t):
        page = t if not t.startswith("@") else f"https://www.youtube.com/{t}"
        return [("youtube-page", _with_scheme(page))]
    url = _with_scheme(t)
    out = [("feed", url)]
    m = re.match(r"^https?://([\w.-]+\.[a-z]{2,})/@([\w.]+)/?$", url, re.I)
    if m:
        out.insert(0, ("mastodon", f"https://{m.group(1)}/@{m.group(2)}.rss"))
    return out


def _looks_like_feed(headers: dict, body: bytes) -> bool:
    ct = headers.get("content-type", "").split(";")[0].strip().lower()
    head = body[:600].lstrip().lower()
    if ct in FEED_TYPES or ct.endswith("+xml"):
        return True
    return head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head


def _announced_feeds(page_url: str, body: bytes) -> list[str]:
    soup = BeautifulSoup(body[:800_000], "html.parser")
    out = []
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        typ = (link.get("type") or "").lower()
        if "alternate" in rel and ("rss" in typ or "atom" in typ or "feed+json" in typ):
            out.append(urljoin(page_url, link["href"]))
    return list(dict.fromkeys(out))


def _youtube_channel_feed(body: bytes) -> str | None:
    text = body.decode("utf-8", "replace")
    m = re.search(r'href="(https://www\.youtube\.com/feeds/videos\.xml\?channel_id=UC[\w-]{22})"', text) or \
        re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', text)
    if not m:
        return None
    v = m.group(1)
    return v if v.startswith("https://") else f"https://www.youtube.com/feeds/videos.xml?channel_id={v}"


def parse_feed(url: str, body: bytes) -> dict:
    d = feedparser.parse(body)
    if not d.entries and not d.feed.get("title"):
        raise SourceError("This address answers, but not with a feed.")
    return {
        "url": url,
        "title": (d.feed.get("title") or urlparse(url).hostname or url).strip()[:200],
        "site_url": d.feed.get("link") or "",
        "entries": d.entries,
    }


# What discover() just read, kept a few minutes: following a feed right after
# finding it then needs no second request (Reddit answers a quick second one
# with 429).
_recent: dict = {}
RECENT_TTL = 300


def recent_feed(url: str) -> dict | None:
    import time
    hit = _recent.get(url)
    return hit[1] if hit and time.time() - hit[0] < RECENT_TTL else None


def _remember(url: str, parsed: dict):
    import time
    now = time.time()
    for k in [k for k, v in _recent.items() if now - v[0] > RECENT_TTL]:
        _recent.pop(k, None)
    _recent[url] = (now, parsed)


async def _try_feed(url: str) -> dict | None:
    final, status, headers, body = await safe_get(url, {"Accept": ", ".join(FEED_TYPES) + ", text/html;q=0.5"})
    if status >= 400:
        return None
    if _looks_like_feed(headers, body):
        try:
            f = parse_feed(final, body)
            _remember(f["url"], f)
            return f
        except SourceError:
            return None
    return {"html": body, "page": final}


async def discover(text: str) -> list[dict]:
    """Feeds the user may mean by what they typed: [{url, kind, title,
    site_url, count, sample}]. Raises SourceError when there is none."""
    found, tried, last_error = [], set(), None

    async def take(kind: str, url: str, depth: int = 0):
        nonlocal last_error
        if url in tried or len(tried) > 10:
            return
        tried.add(url)
        try:
            r = await _try_feed(url)
        except SourceError as e:
            last_error = e
            return
        if not r:
            return
        if "entries" in r:
            found.append({
                "url": r["url"], "kind": "rss" if kind in ("feed", "website") else kind.replace("-page", ""),
                "title": r["title"], "site_url": r["site_url"], "count": len(r["entries"]),
                "sample": [(e.get("title") or "").strip()[:140] for e in r["entries"][:3]],
            })
            return
        if depth:
            return
        page, html = r["page"], r["html"]
        if kind == "youtube-page":
            feed = _youtube_channel_feed(html)
            if feed:
                await take("youtube", feed, 1)
            return
        announced = _announced_feeds(page, html)
        for f in announced[:4]:
            await take("website", f, 1)
        if not announced:
            base = f"{urlparse(page).scheme}://{urlparse(page).netloc}"
            for path in ("/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml"):
                if found:
                    break
                await take("website", base + path, 1)

    for kind, url in candidates(text):
        await take(kind, url)
        if found:
            break
    if not found:
        if last_error:
            raise last_error
        raise SourceError("No feed found at this address.")
    return found


# ── Entries → articles ────────────────────────────────────────────────────────

def _entry_time(e) -> datetime:
    t = e.get("published_parsed") or e.get("updated_parsed") or e.get("created_parsed")
    if t:
        try:
            dt = datetime.fromtimestamp(timegm(t), tz=timezone.utc)
            now = datetime.now(timezone.utc)
            return min(dt, now)
        except (OverflowError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _entry_image(e) -> str | None:
    for key in ("media_thumbnail", "media_content"):
        for m in e.get(key) or []:
            u = m.get("url")
            if u and (key == "media_thumbnail" or (m.get("medium") == "image" or (m.get("type") or "").startswith("image/"))):
                return u
    for l in e.get("links") or []:
        if l.get("rel") == "enclosure" and (l.get("type") or "").startswith("image/"):
            return l.get("href")
    html = (e.get("content") or [{}])[0].get("value") or e.get("summary") or ""
    m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html, re.I)
    return m.group(1) if m else None


def _entry_html(e) -> str:
    content = (e.get("content") or [{}])[0].get("value") or ""
    return content or e.get("summary") or ""


async def store_entries(pool, feed: dict, entries) -> tuple[int, int]:
    """Insert a source's new entries as its owner's articles. Returns
    (new, total) for the source."""
    from translation import needs_translation
    new = 0
    for e in list(entries)[:MAX_ENTRIES]:
        title = re.sub(r"\s+", " ", (e.get("title") or "").strip())[:500] or "(untitled)"
        link = e.get("link") or ""
        if link and not re.match(r"^[a-z][a-z0-9+.-]*:", link, re.I):
            link = urljoin(feed.get("site_url") or feed["url"], link)
        if not re.match(r"^https?://", link, re.I):
            link = ""  # never a javascript: or data: link
        image = _entry_image(e)
        if image and not re.match(r"^https?://", image, re.I):
            image = None
        guid = e.get("id") or link or title
        key = "src:%d:%s" % (feed["id"], hashlib.sha1(guid.encode("utf-8", "replace")).hexdigest()[:20])
        status = "pending" if needs_translation(title) else "done"
        inserted = await pool.fetchval("""
            INSERT INTO articles
              (freshrss_id, feed_source, category, title, url, published_at,
               content_raw, image_url, translation_status, owner_user_id, user_feed_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (freshrss_id) DO UPDATE
              SET image_url = COALESCE(articles.image_url, EXCLUDED.image_url)
            RETURNING (xmax = 0) AS inserted
        """, key, feed["name"], feed.get("category") or "My_Sources", title, link,
            _entry_time(e), _entry_html(e)[:20000], image, status,
            feed["user_id"], feed["id"])
        new += 1 if inserted else 0
    total = await pool.fetchval(
        "SELECT count(*) FROM articles WHERE user_feed_id = $1", feed["id"])
    return new, total


async def fetch_source(pool, feed: dict) -> dict:
    """Fetch one source now (conditional GET) and store its entries.
    Returns {"ok", "items", "error"} and records the outcome on the source."""
    headers = {"Accept": ", ".join(FEED_TYPES)}
    if feed.get("etag"):
        headers["If-None-Match"] = feed["etag"]
    if feed.get("last_modified"):
        headers["If-Modified-Since"] = feed["last_modified"]
    try:
        final, status, h, body = await safe_get(feed["url"], headers)
        if status == 304:
            await pool.execute("""
                UPDATE user_feeds SET last_fetched_at = now(), last_ok_at = now(),
                       last_error = NULL, error_count = 0 WHERE id = $1""", feed["id"])
            return {"ok": True, "items": feed.get("item_count") or 0, "error": None}
        if status >= 400:
            raise SourceError(f"The feed answered HTTP {status}.")
        parsed = parse_feed(final, body)
        new, items = await store_entries(pool, feed, parsed["entries"])
        await pool.execute("""
            UPDATE user_feeds
               SET last_fetched_at = now(), last_ok_at = now(), last_error = NULL,
                   error_count = 0, item_count = $2, etag = $3, last_modified = $4,
                   site_url = COALESCE(NULLIF($5, ''), site_url)
             WHERE id = $1""", feed["id"], items, h.get("etag"), h.get("last-modified"),
            parsed["site_url"])
        return {"ok": True, "items": items, "new": new, "error": None}
    except SourceError as e:
        msg = str(e)
    except Exception as e:  # a malformed feed must not stop the others
        logger.exception("source %s", feed.get("id"))
        msg = f"Unexpected error ({type(e).__name__})."
    await pool.execute("""
        UPDATE user_feeds SET last_fetched_at = now(), last_error = $2,
               error_count = COALESCE(error_count, 0) + 1 WHERE id = $1""", feed["id"], msg[:300])
    return {"ok": False, "items": feed.get("item_count") or 0, "error": msg}


async def due_sources(pool, limit: int = 200) -> list[dict]:
    """Active sources due for a fetch: every 15 minutes, backing off after
    each consecutive error (30 min, 1 h, … up to 16 h)."""
    rows = await pool.fetch("""
        SELECT * FROM user_feeds
         WHERE active AND kind IS NOT NULL
           AND (last_fetched_at IS NULL
                OR last_fetched_at < now() - make_interval(mins => 15 * power(2, LEAST(COALESCE(error_count, 0), 6))::int))
         ORDER BY last_fetched_at NULLS FIRST
         LIMIT $1""", limit)
    return [dict(r) for r in rows]


# ── OPML ──────────────────────────────────────────────────────────────────────

def opml_outlines(text: str) -> list[dict]:
    soup = BeautifulSoup(text[:2_000_000], "html.parser")
    out = []
    for o in soup.find_all("outline"):
        url = o.get("xmlurl")
        if url:
            out.append({"url": url.strip(), "name": (o.get("title") or o.get("text") or "").strip()[:200]})
    return out


def opml_document(username: str, feeds: list[dict]) -> str:
    def x(s):
        return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
             f'  <head><title>AX-NEWS sources of {x(username)}</title></head>', '  <body>']
    for f in feeds:
        lines.append(f'    <outline type="rss" text="{x(f["name"])}" title="{x(f["name"])}" '
                     f'xmlUrl="{x(f["url"])}" htmlUrl="{x(f.get("site_url"))}"/>')
    lines += ['  </body>', '</opml>', '']
    return "\n".join(lines)
