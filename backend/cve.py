"""The vulnerabilities that mattered most in the last two months, for the TV
alerts band.

Candidates: every CVE number the shared stories quote in the last 60 days,
and every CVE CISA added to its Known Exploited Vulnerabilities catalog
(KEV) in that time. Ranked by what makes one important: exploited in the
wild (KEV, ransomware), severity (CVSS from the NVD), how many outlets
covered it, how recent. Each links to its official record on cve.org.

Computing it reads two months of stories (seconds): it is done at most every
15 minutes per process, in the background, and served from memory."""
import asyncio
import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone

import sources

logger = logging.getLogger("ax-news")

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId="
RECORD_URL = "https://www.cve.org/CVERecord?id="
CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,8}$")
DAYS = 60
LIMIT = 20
TTL = 15 * 60

_kev: dict = {"at": 0.0, "tried": 0.0, "data": {}}
_top: dict = {}          # scope key → (at, list)
_busy: set = set()
_nvd_running = False


async def _kev_catalog() -> dict:
    """CISA KEV by CVE number, refreshed twice a day (kept if CISA does not answer)."""
    now = time.time()
    if now - _kev["at"] < 12 * 3600 or now - _kev["tried"] < 3600:
        return _kev["data"]
    _kev["tried"] = now
    try:
        _, status, _, body = await sources.safe_get(KEV_URL, {"Accept": "application/json"})
        if status != 200:
            raise sources.SourceError(f"HTTP {status}")
        vulns = json.loads(body).get("vulnerabilities") or []
        _kev.update(at=now, data={v["cveID"].upper(): v for v in vulns if CVE_ID.match(v.get("cveID", "").upper())})
        logger.info("cve: KEV catalog, %d entries", len(_kev["data"]))
    except Exception as e:
        logger.warning("cve: KEV catalog unavailable (%s)", e)
    return _kev["data"]


async def _nvd_cache(pool) -> dict:
    v = await pool.fetchval("SELECT value FROM app_meta WHERE key = 'nvd_cache'")
    try:
        return json.loads(v) if v else {}
    except ValueError:
        return {}


def _severity(cve: dict) -> tuple[float | None, str | None]:
    metrics = cve.get("metrics") or {}
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for m in metrics.get(key) or []:
            data = m.get("cvssData") or {}
            score = data.get("baseScore")
            sev = data.get("baseSeverity") or m.get("baseSeverity")
            if score is not None:
                return float(score), (sev or "").upper() or None
    return None, None


async def _fetch_nvd(pool, ids: list[str]):
    """CVSS scores from the NVD for the leading candidates, at its public
    pace (5 requests per 30 seconds), into app_meta for every process."""
    global _nvd_running
    if _nvd_running:
        return
    _nvd_running = True
    try:
        for cid in ids:
            cache = await _nvd_cache(pool)
            hit = cache.get(cid)
            if hit and time.time() - hit.get("at", 0) < (3 * 86400 if hit.get("score") is not None else 86400):
                continue
            entry = {"at": time.time(), "score": None, "severity": None, "desc": None}
            try:
                _, status, _, body = await sources.safe_get(NVD_URL + cid, {"Accept": "application/json"})
                if status == 200:
                    vulns = json.loads(body).get("vulnerabilities") or []
                    if vulns:
                        c = vulns[0].get("cve") or {}
                        entry["score"], entry["severity"] = _severity(c)
                        d = next((x.get("value") for x in c.get("descriptions") or [] if x.get("lang") == "en"), "") or ""
                        entry["desc"] = re.split(r"(?<=[.!?])\s", d.strip(), 1)[0][:200] or None
                elif status in (403, 429):
                    break   # slowed down by the NVD: next round
            except Exception as e:
                logger.info("cve: NVD %s: %s", cid, e)
            cache = await _nvd_cache(pool)
            cache[cid] = entry
            if len(cache) > 400:   # the oldest go
                cache = dict(sorted(cache.items(), key=lambda kv: kv[1].get("at", 0))[-400:])
            await pool.execute("""INSERT INTO app_meta (key, value) VALUES ('nvd_cache', $1)
                                  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                               json.dumps(cache))
            await asyncio.sleep(6.5)
    finally:
        _nvd_running = False


async def _compute(pool, owner_id: int, scope: str) -> list[dict]:
    if scope == "mine" and owner_id:
        who = "a.owner_user_id = $1"
    elif scope == "all" and owner_id:
        who = "(a.owner_user_id IS NULL OR a.owner_user_id = $1)"
    else:
        who = "a.owner_user_id IS NULL AND $1::int IS NOT NULL"
    # A story quoting more than three CVEs is a round-up ("September's
    # CVE landscape"): it counts, but its title does not name the flaw.
    rows = await pool.fetch(f"""
        WITH m AS (
            SELECT a.id, a.title, a.feed_source, a.published_at, upper('CVE-' || x[1]) AS cve
              FROM articles a,
                   LATERAL regexp_matches(a.title || ' ' || left(coalesce(a.content_raw, ''), 6000),
                                          'CVE-([0-9]{{4}}-[0-9]{{4,8}})', 'gi') x
             WHERE a.published_at > now() - make_interval(days => {DAYS})
               AND a.published_at <= now()
               AND {who}
               AND (a.translation_status = 'done' OR a.original_lang = 'en')
               AND (a.title ~* 'CVE-[0-9]' OR a.content_raw ~* 'CVE-[0-9]')
        ), per AS (SELECT id, count(DISTINCT cve) > 3 AS roundup FROM m GROUP BY id)
        SELECT m.cve,
               count(DISTINCT m.id) AS stories,
               count(DISTINCT m.feed_source) AS sources,
               max(m.published_at) AS latest,
               (array_agg(m.id ORDER BY per.roundup, m.published_at DESC))[1] AS article_id,
               (array_agg(m.title ORDER BY per.roundup, m.published_at DESC))[1] AS title,
               (array_agg(m.feed_source ORDER BY per.roundup, m.published_at DESC))[1] AS source,
               bool_and(per.roundup) AS only_roundups
          FROM m JOIN per USING (id)
         GROUP BY m.cve""", owner_id or 0)
    kev = await _kev_catalog()
    nvd = await _nvd_cache(pool)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=DAYS)).date().isoformat()
    found = {r["cve"]: dict(r) for r in rows}
    for cid, k in kev.items():
        if (k.get("dateAdded") or "") >= since and cid not in found:
            found[cid] = {"cve": cid, "stories": 0, "sources": 0, "latest": None, "article_id": None,
                          "title": None, "source": None, "only_roundups": True}
    out = []
    for cid, r in found.items():
        k = kev.get(cid)
        n = nvd.get(cid) or {}
        added = None
        if k and k.get("dateAdded"):
            try:
                added = datetime.fromisoformat(k["dateAdded"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        last = max([d for d in (r["latest"], added) if d] or [now - timedelta(days=DAYS)])
        age = max(0.0, (now - last).total_seconds() / 86400)
        score = n.get("score")
        ransom = bool(k and (k.get("knownRansomwareCampaignUse") or "").lower() == "known")
        rank = (50 if k else 0) + (10 if ransom else 0) \
            + (35 if score and score >= 9 else 20 if score and score >= 7 else 5 if score and score >= 4 else 0) \
            + 6 * min(r["sources"], 15) + min(r["stories"], 30) + 30 * math.exp(-age / 14)
        # The flaw's official name (KEV), else a story about it, else the
        # NVD's description.
        if k and k.get("vulnerabilityName"):
            text = k["vulnerabilityName"]
        elif r["title"] and not r["only_roundups"]:
            text = r["title"]
        else:
            text = n.get("desc") or r["title"] or ""
        out.append({
            "id": r["article_id"], "label": cid, "cves": [cid], "title": text[:240],
            "source": r["source"] or ("CISA KEV" if k else ""), "stories": r["stories"], "sources": r["sources"],
            "published_at": last.isoformat(), "kev": bool(k), "kev_added": k.get("dateAdded") if k else None,
            "ransomware": ransom, "cvss": score, "severity": n.get("severity"),
            "record": RECORD_URL + cid, "_rank": rank,
        })
    out.sort(key=lambda x: x["_rank"], reverse=True)
    top = out[:LIMIT]
    for x in top:
        x.pop("_rank")
    # Scores for the leading candidates, for the next rounds.
    asyncio.create_task(_fetch_nvd(pool, [x["label"] for x in out[:40]]))
    return top


async def top(pool, owner_id: int = 0, scope: str = "public") -> list[dict]:
    key = f"{scope}:{owner_id if scope != 'public' else 0}"
    hit = _top.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]

    async def refresh():
        _busy.add(key)
        try:
            _top[key] = (time.time(), await _compute(pool, owner_id, scope))
        except Exception:
            logger.exception("cve: ranking failed")
        finally:
            _busy.discard(key)

    if hit:                       # stale: served while it is redone
        if key not in _busy:
            asyncio.create_task(refresh())
        return hit[1]
    await refresh()
    return (_top.get(key) or (0, []))[1]
