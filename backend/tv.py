"""TV screens: what an unattended screen shows, around the clock.

A screen belongs to an account (tv_screens) and is opened at /tv/<token>,
with no sign-in: the token is its only key. /tv.html is the public screen —
the shared tech feeds — whose layout and theme the address may choose
(?layout=…&theme=…)."""
import re
import secrets

from db import PUBLIC, VISIBLE, _CJK, _json_list, excerpt

LAYOUTS = ("spotlight", "newsroom", "wall", "columns", "headlines", "magazine")
THEMES = ("aurora", "broadcast", "paper", "terminal", "clinic", "nebula")
SCOPES = ("public", "all", "mine")
ALERTS = ("cve", "keywords", "none")

DEFAULT = {
    "layout": "spotlight",
    "theme": "aurora",
    "title": "Tech Intelligence",
    "topics": [],            # categories; none = every topic
    "scope": "public",
    "dwell": 12,             # seconds a story stays on screen
    "hours": 48,             # how old a story may be
    "alerts": "cve",
    "alert_words": [],
    "show_qr": True,
    "show_ticker": True,
    "show_clock": True,
    "rotate_layouts": False, # a different layout every hour
    "night_dim": False,      # dim between 20:00 and 07:00, screen time
}


def new_token() -> str:
    return secrets.token_urlsafe(18)


def clean_config(raw: dict | None, base: dict | None = None) -> dict:
    """A screen's settings, every value checked: they reach a page."""
    c = dict(base or DEFAULT)
    raw = raw or {}

    def pick(key, allowed):
        if raw.get(key) in allowed:
            c[key] = raw[key]

    pick("layout", LAYOUTS)
    pick("theme", THEMES)
    pick("scope", SCOPES)
    pick("alerts", ALERTS)
    if isinstance(raw.get("title"), str):
        c["title"] = re.sub(r"\s+", " ", raw["title"]).strip()[:60] or DEFAULT["title"]
    if isinstance(raw.get("topics"), list):
        c["topics"] = [t for t in raw["topics"] if isinstance(t, str) and re.fullmatch(r"[A-Za-z0-9_]{1,60}", t)][:60]
    if isinstance(raw.get("alert_words"), list):
        c["alert_words"] = [w.strip()[:40] for w in raw["alert_words"] if isinstance(w, str) and w.strip()][:20]
    for key, lo, hi in (("dwell", 6, 60), ("hours", 6, 168)):
        try:
            c[key] = max(lo, min(hi, int(raw.get(key, c[key]))))
        except (TypeError, ValueError):
            pass
    for key in ("show_qr", "show_ticker", "show_clock", "rotate_layouts", "night_dim"):
        if isinstance(raw.get(key), bool):
            c[key] = raw[key]
    return c


def _where(config: dict, owner_id: int, params: list) -> str:
    def arg(v):
        params.append(v)
        return f"${len(params)}"

    cond = [c for c in VISIBLE if "30 days" not in c]
    cond.append(f"a.published_at >= NOW() - make_interval(hours => {arg(int(config['hours']))})")
    uid = arg(owner_id or 0)
    cond.append(f"{uid}::int IS NOT NULL")
    if config["scope"] == "mine" and owner_id:
        cond.append(f"a.owner_user_id = {uid}")
    elif config["scope"] == "all" and owner_id:
        cond.append(f"(a.owner_user_id IS NULL OR a.owner_user_id = {uid})")
    else:
        cond.append(PUBLIC)
    if config["topics"]:
        cond.append(f"a.category = ANY({arg(list(config['topics']))}::text[])")
    return " AND ".join(cond)


async def feed(pool, config: dict, owner_id: int = 0, limit: int = 160) -> dict:
    """The stories a screen cycles through, newest first, no source more than
    a quarter of them (a busy feed would fill the screen), plus its alerts."""
    params: list = []
    where = _where(config, owner_id, params)
    rows = await pool.fetch(f"""
        SELECT a.id, a.title, a.feed_source, a.category, a.published_at, a.image_url, a.url,
               left(a.content_raw, 3000) AS content_raw, a.original_lang, a.entities,
               a.owner_user_id IS NOT NULL AS personal
          FROM articles a
         WHERE {where}
         ORDER BY a.published_at DESC
         LIMIT {int(limit) * 3}""", *params)
    per_source: dict = {}
    cap = max(4, limit // 4)
    stories = []
    for r in rows:
        src = r["feed_source"] or ""
        if per_source.get(src, 0) >= cap:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        text = excerpt(r["content_raw"] or "", 300)
        if r["original_lang"] not in (None, "en") and _CJK.search(text):
            text = ""
        url = r["url"] if re.match(r"^https?://", r["url"] or "", re.I) else ""
        img = r["image_url"] if re.match(r"^https?://", r["image_url"] or "", re.I) else None
        stories.append({
            "id": r["id"], "title": r["title"], "excerpt": text, "source": src,
            "category": r["category"], "published_at": r["published_at"].isoformat() if r["published_at"] else None,
            "image_url": img, "host": re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*$", r"\1", url)) if url else "",
            "lang": r["original_lang"] if r["original_lang"] not in (None, "en") else None,
            "entities": [e.get("name") if isinstance(e, dict) else str(e) for e in _json_list(r["entities"])][:4],
            "personal": r["personal"],
        })
        if len(stories) >= limit:
            break
    counts = await pool.fetchrow(f"""
        SELECT count(*) FILTER (WHERE a.published_at > NOW() - INTERVAL '1 hour') AS hour,
               count(*) FILTER (WHERE a.published_at > NOW() - INTERVAL '24 hours') AS day,
               count(DISTINCT a.feed_source) FILTER (WHERE a.published_at > NOW() - INTERVAL '24 hours') AS sources
          FROM articles a WHERE {where}""", *params)
    return {"stories": stories, "alerts": await alerts(pool, config, owner_id),
            "counts": {k: counts[k] for k in ("hour", "day", "sources")}}


CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)


async def alerts(pool, config: dict, owner_id: int = 0) -> list[dict]:
    """The band across the screen: security advisories (a CVE number in the
    story), or stories with one of the screen's words."""
    if config["alerts"] == "none" or (config["alerts"] == "keywords" and not config["alert_words"]):
        return []
    params: list = []
    where = _where({**config, "hours": min(int(config["hours"]), 72)}, owner_id, params)
    if config["alerts"] == "cve":
        where += " AND (a.title ~* 'CVE-[0-9]{4}-[0-9]{4,}' OR left(a.content_raw, 4000) ~* 'CVE-[0-9]{4}-[0-9]{4,}')"
    else:
        ors = []
        for w in config["alert_words"]:
            params.append("%" + w.replace("%", r"\%").replace("_", r"\_") + "%")
            ors.append(f"a.title ILIKE ${len(params)}")
        where += " AND (" + " OR ".join(ors) + ")"
    rows = await pool.fetch(f"""
        SELECT a.id, a.title, a.feed_source, a.published_at, left(a.content_raw, 4000) AS content_raw
          FROM articles a WHERE {where} ORDER BY a.published_at DESC LIMIT 20""", *params)
    out = []
    for r in rows:
        if config["alerts"] == "cve":
            ids = list(dict.fromkeys(m.upper() for m in CVE.findall((r["title"] or "") + " " + (r["content_raw"] or ""))))[:3]
            label = " · ".join(ids)
        else:
            label = next((w for w in config["alert_words"] if w.lower() in (r["title"] or "").lower()), "")
        out.append({"id": r["id"], "title": r["title"], "source": r["feed_source"], "label": label,
                    "published_at": r["published_at"].isoformat() if r["published_at"] else None})
    return out
