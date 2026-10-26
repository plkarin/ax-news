"""The world feed catalog (catalog/feeds.json, built and checked by
tools/catalog/build.py) and the topic taxonomy every page and the TV share
(catalog/taxonomy.json).

The catalog is loaded into feed_catalog at start-up, once per version of the
file. Its active feeds are the shared tech feeds FreshRSS fetches; every
other feed is offered to accounts, which follow it as one of their sources,
or to an admin, who can share it with everyone."""
import hashlib
import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("ax-news")

ROOT = Path(__file__).resolve().parent.parent
CATALOG_FILE = ROOT / "catalog" / "feeds.json"
TAXONOMY = json.loads((ROOT / "catalog" / "taxonomy.json").read_text())
CATEGORIES = {c["key"]: c for c in TAXONOMY["categories"]}
DOMAINS = {d["key"]: d for d in TAXONOMY["domains"]}

LANG_NAMES = {
    "en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "da": "Danish",
    "nb": "Norwegian", "fi": "Finnish", "cs": "Czech", "el": "Greek", "ro": "Romanian",
    "hu": "Hungarian", "uk": "Ukrainian", "ru": "Russian", "tr": "Turkish", "ar": "Arabic",
    "fa": "Persian", "he": "Hebrew", "hi": "Hindi", "id": "Indonesian", "th": "Thai",
    "vi": "Vietnamese", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "sw": "Swahili",
    "ca": "Catalan", "bg": "Bulgarian", "sk": "Slovak", "sl": "Slovenian", "ms": "Malay",
    "bn": "Bengali", "ur": "Urdu", "tl": "Tagalog", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian",
}

# Feed title → language, for the shared FreshRSS feeds that are not in
# English: db.upsert_article sends their stories to translation.
FEED_LANGS: dict[str, str] = {}


def lang_code(code: str | None) -> str | None:
    """langdetect's and Argos's codes, reduced to the catalog's."""
    if not code:
        return None
    code = code.lower()
    return {"zh-cn": "zh", "zh-tw": "zh", "zt": "zh", "no": "nb", "iw": "he"}.get(code, code.split("-")[0])


def argos_languages() -> set[str]:
    """Languages an installed Argos model translates into English. Read from
    the package folders: importing Argos in the web process would cost
    hundreds of megabytes."""
    home = Path(os.environ.get("ARGOS_HOME") or os.environ.get("HOME") or "~").expanduser()
    out = set()
    for meta in (home / ".local" / "share" / "argos-translate" / "packages").glob("*/metadata.json"):
        try:
            m = json.loads(meta.read_text())
            if m.get("to_code") == "en" and m.get("from_code"):
                out.add(lang_code(m["from_code"]))
        except (OSError, ValueError):
            continue
    return out


_argos_cache: dict = {}


def translatable(lang: str | None) -> bool:
    """Whether stories in this language reach English (the site's language)."""
    lang = lang_code(lang) or "en"
    if lang == "en":
        return True
    import time
    if not _argos_cache or time.time() - _argos_cache["at"] > 600:
        _argos_cache.update(at=time.time(), langs=argos_languages())
    return lang in _argos_cache["langs"]


def detect_feed_language(entries) -> str | None:
    """A feed's language from its stories (many titles: steadier than one)."""
    from translation import _script_language
    text = " ".join(((e.get("title") or "") + " " + re.sub(r"<[^>]+>", " ", e.get("summary") or "")[:200])
                    for e in list(entries)[:25])
    script = _script_language(text)
    if script:
        return script
    if len(text.strip()) < 40:
        return None
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0
        return lang_code(detect(text[:4000]))
    except Exception:
        return None


async def sync(pool) -> int:
    """Load catalog/feeds.json into feed_catalog when the file changed.
    Returns the number of feeds written (0 when it had not changed)."""
    try:
        raw = CATALOG_FILE.read_bytes()
    except OSError:
        logger.warning("catalog: %s missing", CATALOG_FILE)
        return 0
    digest = hashlib.sha256(raw).hexdigest()
    try:
        current = await pool.fetchval("SELECT value FROM app_meta WHERE key = 'catalog_sha256'")
    except Exception:
        logger.warning("catalog: migration 004 not applied, catalog not loaded")
        return 0
    if current != digest:
        data = json.loads(raw)
        feeds = data["feeds"]
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE feed_catalog SET listed = false")
                await conn.executemany("""
                    INSERT INTO feed_catalog (url, title, site_url, category, domain, lang, region,
                                              provider, active, items, newest, checked_at, listed, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7, CASE WHEN $8 THEN 'freshrss' ELSE 'catalog' END,
                            $8, $9, $10::timestamptz, $11::timestamptz, true, now())
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title, site_url = EXCLUDED.site_url,
                        category = EXCLUDED.category, domain = EXCLUDED.domain,
                        lang = EXCLUDED.lang, region = EXCLUDED.region,
                        provider = EXCLUDED.provider,
                        active = EXCLUDED.active OR (feed_catalog.provider = 'catalog' AND feed_catalog.active),
                        items = EXCLUDED.items, newest = EXCLUDED.newest,
                        checked_at = EXCLUDED.checked_at, listed = true, updated_at = now()
                """, [(f["url"], f["title"][:200], f.get("site_url"), f["category"], f["domain"],
                       f.get("lang") or "en", f.get("region"), bool(f.get("active")), int(f.get("items") or 0),
                       _ts(f.get("newest")), _ts(data.get("checked_at"))) for f in feeds])
                # A catalog feed is active while its shared row fetches it.
                await conn.execute("""
                    UPDATE feed_catalog c SET active = EXISTS (
                        SELECT 1 FROM user_feeds f WHERE f.catalog_id = c.id AND f.user_id IS NULL AND f.active)
                     WHERE provider = 'catalog'""")
                await conn.execute("""
                    INSERT INTO app_meta (key, value) VALUES ('catalog_sha256', $1)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""", digest)
        logger.info("catalog: %d feeds loaded", len(feeds))
    rows = await pool.fetch("SELECT title, lang FROM feed_catalog WHERE provider = 'freshrss' AND lang <> 'en'")
    FEED_LANGS.clear()
    FEED_LANGS.update({r["title"]: r["lang"] for r in rows})
    return 0 if current == digest else len(json.loads(raw)["feeds"])


def _ts(v):
    from datetime import datetime
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def public_taxonomy() -> dict:
    """What the pages embed: domains, then categories with label, colour and
    illustration."""
    arts = ROOT / "frontend" / "assets" / "img" / "topics"

    def art(name):  # an illustration not made yet: the default one
        return name if (arts / f"{name}.webp").exists() and (arts / f"{name}-sm.webp").exists() else "default"
    return {"domains": TAXONOMY["domains"],
            "categories": {c["key"]: [c["label"], c["color"], art(c["art"]), c["domain"]] for c in TAXONOMY["categories"]}}
