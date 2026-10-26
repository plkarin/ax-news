"""Pages for search engines and links: server-rendered, one subject each.

The feed itself is drawn in the browser and changes every minute: nothing a
search engine can index. These pages are plain HTML, built here:

  /topics, /topic/<key>, /topic/<key>/<YYYY-MM-DD>   a topic, today and each day
  /digest, /digest/<YYYY-MM-DD>                      the day across topics
  /countries, /country/<cc>, /translated             where the news comes from
  /cve, /cve/<CVE-ID>, /cve/week/<YYYY-Www>          the vulnerabilities
  /feeds, /feeds/<domain>                            the feed catalog

Each story is shown as its title, a short excerpt and a link to its
publisher (/go/<id>): the stories stay theirs. Data are cached a few
minutes per process."""
import html
import re
import time
from datetime import date, datetime, timedelta, timezone

import catalog
import countries
from db import PUBLIC, VISIBLE, _CJK, excerpt

APP_URL = "https://ax-news.com"
_cache: dict = {}


async def cached(key: str, ttl: int, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = await fn()
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (time.time(), value)
    return value


def topic_label(key: str) -> str:
    c = catalog.CATEGORIES.get(key)
    return c["label"] if c else key.replace("_", " ")


def topic_meta(key: str) -> dict:
    c = catalog.public_taxonomy()["categories"].get(key)
    if not c:
        return {"key": key, "label": topic_label(key), "color": "#7c8cff", "art": "default", "domain": None}
    return {"key": key, "label": c[0], "color": c[1], "art": c[2], "domain": c[3]}


async def _origins(pool):
    import tv
    return await tv._origin_maps(pool)


async def stories(pool, where: str, params: list, limit: int = 80, order: str = "a.published_at DESC") -> list[dict]:
    """Public, visible stories matching `where`, ready for a page."""
    cond = list(VISIBLE) + [PUBLIC, where] if where else list(VISIBLE) + [PUBLIC]
    rows = await pool.fetch(f"""
        SELECT a.id, a.title, a.feed_source, a.category, a.published_at, a.url, a.image_url,
               left(a.content_raw, 2000) AS content_raw, a.original_lang, a.user_feed_id
          FROM articles a
         WHERE {' AND '.join(c for c in cond if c)}
         ORDER BY {order}
         LIMIT {int(limit)}""", *params)
    by_title, by_feed = await _origins(pool)
    out = []
    for r in rows:
        text = excerpt(r["content_raw"] or "", 240)
        if r["original_lang"] not in (None, "en") and _CJK.search(text):
            text = ""
        url = r["url"] if re.match(r"^https?://", r["url"] or "", re.I) else ""
        out.append({
            "id": r["id"], "title": html.unescape(r["title"] or ""), "source": r["feed_source"] or "",
            "category": r["category"], "topic": topic_meta(r["category"]),
            "published_at": r["published_at"], "excerpt": text,
            "host": re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*$", r"\1", url)) if url else "",
            "image": r["image_url"] if re.match(r"^https?://", r["image_url"] or "", re.I) else None,
            "lang": r["original_lang"] if r["original_lang"] not in (None, "en") else None,
            "lang_name": catalog.LANG_NAMES.get(r["original_lang"] or "", r["original_lang"]),
            "country": by_feed.get(r["user_feed_id"]) or by_title.get(r["feed_source"] or "") or countries.country(url),
        })
    return out


# ── Topics and days ───────────────────────────────────────────────────────────

async def topics_overview(pool) -> list[dict]:
    async def go():
        rows = await pool.fetch(f"""
            SELECT a.category, count(*) FILTER (WHERE a.published_at > now() - interval '48 hours') AS recent,
                   count(*) AS month
              FROM articles a WHERE {' AND '.join(VISIBLE + [PUBLIC])} GROUP BY 1""")
        out = []
        for r in rows:
            if not r["category"] or r["month"] < 5:
                continue
            m = topic_meta(r["category"])
            out.append({**m, "recent": r["recent"], "month": r["month"]})
        out.sort(key=lambda t: -t["recent"])
        return out
    return await cached("topics", 600, go)


async def topic_page(pool, key: str, day: date | None = None) -> dict | None:
    async def go():
        if day:
            start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            items = await stories(pool, "a.category = $1 AND a.published_at >= $2 AND a.published_at < $3",
                                  [key, start, start + timedelta(days=1)], limit=150)
        else:
            items = await stories(pool, "a.category = $1 AND a.published_at > now() - interval '48 hours'", [key], limit=80)
        days = await topic_days(pool, key)
        if not items and not days:
            return None
        return {"topic": topic_meta(key), "items": items, "days": days, "day": day}
    return await cached(f"topic:{key}:{day}", 300, go)


async def topic_days(pool, key: str) -> list[dict]:
    """The days of the last month with at least three stories on the topic."""
    async def go():
        rows = await pool.fetch(f"""
            SELECT (a.published_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n
              FROM articles a WHERE {' AND '.join(VISIBLE + [PUBLIC])} AND a.category = $1
             GROUP BY 1 HAVING count(*) >= 3 ORDER BY 1 DESC""", key)
        return [{"date": r["d"], "count": r["n"]} for r in rows]
    return await cached(f"days:{key}", 900, go)


async def digest(pool, day: date) -> dict:
    """A day across topics: the busiest topics first, a handful of stories each."""
    async def go():
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        items = await stories(pool, "a.published_at >= $1 AND a.published_at < $2", [start, start + timedelta(days=1)], limit=600)
        groups: dict = {}
        for s in items:
            groups.setdefault(s["category"], []).append(s)
        topics = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:14]
        return {"day": day, "total": len(items), "sources": len({s["source"] for s in items}),
                "topics": [{"topic": topic_meta(k), "count": len(v), "items": v[:6]} for k, v in topics]}
    return await cached(f"digest:{day}", 300 if day >= datetime.now(timezone.utc).date() else 3600, go)


async def digest_days(pool) -> list[date]:
    async def go():
        rows = await pool.fetch(f"""
            SELECT (a.published_at AT TIME ZONE 'UTC')::date AS d FROM articles a
             WHERE {' AND '.join(VISIBLE + [PUBLIC])} GROUP BY 1 HAVING count(*) >= 20 ORDER BY 1 DESC""")
        return [r["d"] for r in rows]
    return await cached("digest-days", 900, go)


# ── Countries and translations ────────────────────────────────────────────────

async def _titles_by_country(pool) -> dict:
    by_title, _ = await _origins(pool)
    out: dict = {}
    for title, cc in by_title.items():
        out.setdefault(cc, []).append(title)
    return out


async def countries_overview(pool) -> list[dict]:
    async def go():
        rows = await pool.fetch(f"""
            SELECT a.feed_source, count(*) AS n FROM articles a
             WHERE {' AND '.join(VISIBLE + [PUBLIC])} AND a.published_at > now() - interval '7 days'
             GROUP BY 1""")
        by_title, _ = await _origins(pool)
        counts: dict = {}
        for r in rows:
            cc = by_title.get(r["feed_source"] or "")
            if cc and len(cc) == 2 and cc not in ("EU", "UN"):
                c = counts.setdefault(cc, {"code": cc, "stories": 0, "sources": 0})
                c["stories"] += r["n"]
                c["sources"] += 1
        return sorted(counts.values(), key=lambda c: -c["stories"])
    return await cached("countries", 900, go)


async def country_page(pool, cc: str) -> dict | None:
    async def go():
        titles = (await _titles_by_country(pool)).get(cc)
        if not titles:
            return None
        items = await stories(pool, "a.feed_source = ANY($1::text[]) AND a.published_at > now() - interval '7 days'", [titles], limit=100)
        if not items:
            return None
        return {"code": cc, "items": items, "sources": sorted({s["source"] for s in items}),
                "translated": sum(1 for s in items if s["lang"])}
    return await cached(f"country:{cc}", 600, go)


async def translated_page(pool) -> dict:
    async def go():
        items = await stories(pool, "a.original_lang IS NOT NULL AND a.original_lang <> 'en' AND a.published_at > now() - interval '72 hours'", [], limit=120)
        langs: dict = {}
        for s in items:
            langs[s["lang_name"]] = langs.get(s["lang_name"], 0) + 1
        return {"items": items, "languages": sorted(langs.items(), key=lambda kv: -kv[1])}
    return await cached("translated", 600, go)


# ── Vulnerabilities ───────────────────────────────────────────────────────────

CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,8}$")


async def cve_page(pool, cid: str) -> dict | None:
    import cve
    async def go():
        index = await cve.mention_index(pool)
        m = index.get(cid)
        kev = (await cve._kev_catalog()).get(cid)
        nvd = (await cve._nvd_cache(pool)).get(cid)
        if not m and not kev and not nvd:
            return None
        if not nvd or "impact" not in nvd:
            cve.want(pool, cid)   # its severity and products, at the NVD's pace
        items = []
        if m:
            items = await stories(pool, "a.id = ANY($1::bigint[])", [m["ids"][:40]], limit=40)
        first = m["first"] if m else None
        return {"id": cid, "items": items, "kev": kev, "nvd": nvd or {}, "first": first,
                "latest": m["latest"] if m else None, "sources": m["sources"] if m else 0,
                "stories": m["stories"] if m else 0, "record": cve.RECORD_URL + cid,
                "nvd_url": "https://nvd.nist.gov/vuln/detail/" + cid}
    return await cached(f"cve:{cid}", 600, go)


async def cve_index(pool) -> dict:
    import cve
    async def go():
        index = await cve.mention_index(pool)
        nvd = await cve._nvd_cache(pool)
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent = sorted(((k, v) for k, v in index.items() if v["latest"] and v["latest"] > week_ago),
                        key=lambda kv: kv[1]["latest"], reverse=True)[:120]
        return {"top": await cve.top(pool), "breaking": await cve.breaking(pool),
                "recent": [{"id": k, **v, "score": (nvd.get(k) or {}).get("score"),
                            "severity": (nvd.get(k) or {}).get("severity")} for k, v in recent],
                "total": len(index)}
    return await cached("cve-index", 300, go)


async def cve_week(pool, year: int, week: int) -> dict | None:
    import cve
    async def go():
        start = datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=7)
        index = await cve.mention_index(pool)
        nvd = await cve._nvd_cache(pool)
        kev = await cve._kev_catalog()
        rows = [{"id": k, **v, "score": (nvd.get(k) or {}).get("score"), "severity": (nvd.get(k) or {}).get("severity"),
                 "kev": k in kev, "impact": (nvd.get(k) or {}).get("impact") or []}
                for k, v in index.items() if v["first"] and start <= v["first"] < end]
        if not rows:
            return None
        rows.sort(key=lambda r: (-(r["score"] or 0), -r["sources"]))
        return {"year": year, "week": week, "start": start.date(), "end": (end - timedelta(days=1)).date(), "cves": rows}
    return await cached(f"cve-week:{year}-{week}", 900, go)


# ── Feed catalog ──────────────────────────────────────────────────────────────

async def feeds_domain(pool, domain: str) -> dict | None:
    if domain not in catalog.DOMAINS:
        return None

    async def go():
        rows = await pool.fetch("""SELECT id, url, title, site_url, category, lang, region, active, items, newest
                                     FROM feed_catalog WHERE listed AND domain = $1
                                    ORDER BY category, active DESC, (lang = 'en') DESC, lower(title)""", domain)
        groups: dict = {}
        for r in rows:
            d = dict(r)
            d["country"] = countries.country(d["site_url"] or d["url"], d["title"], d["region"])
            d["lang_name"] = catalog.LANG_NAMES.get(d["lang"], d["lang"])
            groups.setdefault(d["category"], []).append(d)
        return {"domain": catalog.DOMAINS[domain], "groups": [(topic_meta(k), v) for k, v in groups.items()],
                "total": len(rows)}
    return await cached(f"feeds:{domain}", 3600, go)


def opml(title: str, feeds: list[dict]) -> str:
    x = lambda s: (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
             f'  <head><title>{x(title)}</title><ownerName>AX-NEWS</ownerName></head>', '  <body>']
    for f in feeds:
        lines.append(f'    <outline type="rss" text="{x(f["title"])}" title="{x(f["title"])}" xmlUrl="{x(f["url"])}" htmlUrl="{x(f.get("site_url"))}"/>')
    lines += ['  </body>', '</opml>', '']
    return "\n".join(lines)


# ── Feeds out and sitemaps ────────────────────────────────────────────────────

def rss(title: str, link: str, description: str, entries: list[dict]) -> str:
    x = lambda s: html.escape(s or "", quote=False)
    from email.utils import format_datetime
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
           f'<title>{x(title)}</title><link>{x(link)}</link><description>{x(description)}</description>',
           f'<atom:link href="{x(link)}/feed.xml" rel="self" type="application/rss+xml"/>', '<language>en</language>']
    for e in entries:
        when = e.get("date") or datetime.now(timezone.utc)
        out.append(f'<item><title>{x(e["title"])}</title><link>{x(e["link"])}</link><guid isPermaLink="false">{x(e["guid"])}</guid>'
                   f'<pubDate>{format_datetime(when)}</pubDate><description>{x(e.get("description", ""))}</description></item>')
    out.append('</channel></rss>')
    return "\n".join(out)


def urlset(urls: list[tuple]) -> str:
    """urls: (path, lastmod datetime|date|None, changefreq|None)."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, freq in urls:
        out.append("  <url><loc>%s%s</loc>%s%s</url>" % (
            APP_URL, html.escape(path),
            f"<lastmod>{lastmod.isoformat() if hasattr(lastmod, 'isoformat') else lastmod}</lastmod>" if lastmod else "",
            f"<changefreq>{freq}</changefreq>" if freq else ""))
    out.append('</urlset>')
    return "\n".join(out)


# ── Structured data ───────────────────────────────────────────────────────────

def ld_page(kind: str, name: str, path: str, trail: list[tuple], items: list[dict] | None = None,
            extra: dict | None = None) -> dict:
    """schema.org JSON-LD: the page (CollectionPage, WebPage…), its list of
    stories, its breadcrumb."""
    page = {"@type": kind, "@id": APP_URL + path, "url": APP_URL + path, "name": name,
            "isPartOf": {"@type": "WebSite", "name": "AX-NEWS", "url": APP_URL + "/"},
            "inLanguage": "en"}
    if items is not None:
        page["mainEntity"] = {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": s["title"], "url": f"{APP_URL}/go/{s['id']}"}
            for i, s in enumerate(items[:30])]}
    if extra:
        page.update(extra)
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": label, "item": APP_URL + href}
        for i, (label, href) in enumerate(trail)]}
    return {"@context": "https://schema.org", "@graph": [page, crumbs]}
