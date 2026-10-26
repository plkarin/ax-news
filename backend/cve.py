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
import html
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
CNA_URL = "https://cveawg.mitre.org/api/cve/"
RECORD_URL = "https://www.cve.org/CVERecord?id="
CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,8}$")
DAYS = 60
LIMIT = 20
TTL = 15 * 60

BREAKING_SCORE = 8.0     # CVSS from which a new CVE is breaking news
BREAKING_SECS = 3600     # how long it stays on screen after we first got it

_kev: dict = {"at": 0.0, "tried": 0.0, "data": {}}
_breaking: dict = {"at": 0.0, "items": []}
_prio: list = []         # CVEs whose scores are wanted first (breaking candidates)
_index: dict = {"at": 0.0, "data": {}}   # CVE → the shared stories quoting it (60 days)
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


# The kind of flaw, in a few words, from its CWE.
CWE = {
    "77": "Command injection", "78": "OS command injection", "79": "Cross-site scripting",
    "89": "SQL injection", "94": "Code injection", "95": "Code injection", "74": "Injection",
    "416": "Use after free", "787": "Memory corruption", "125": "Out-of-bounds read",
    "119": "Memory corruption", "120": "Buffer overflow", "121": "Buffer overflow", "122": "Heap overflow",
    "20": "Improper input validation", "22": "Path traversal", "23": "Path traversal", "59": "Link following",
    "287": "Authentication bypass", "288": "Authentication bypass", "290": "Authentication bypass",
    "306": "Missing authentication", "862": "Missing authorization", "863": "Broken authorization",
    "285": "Broken authorization", "284": "Broken access control", "269": "Privilege escalation",
    "250": "Privilege escalation", "502": "Unsafe deserialization", "918": "Server-side request forgery",
    "352": "Cross-site request forgery", "434": "Unrestricted file upload", "200": "Information disclosure",
    "400": "Denial of service", "770": "Denial of service", "798": "Hard-coded credentials",
    "611": "XML external entity", "1321": "Prototype pollution", "843": "Type confusion",
    "190": "Integer overflow", "476": "NULL pointer dereference", "362": "Race condition",
    "601": "Open redirect", "427": "Untrusted search path", "426": "Untrusted search path",
    "755": "Unhandled exception", "807": "Untrusted input in a security decision", "1336": "Template injection",
    "917": "Expression language injection", "123": "Memory corruption", "415": "Double free",
    "98": "Remote file inclusion", "829": "Remote file inclusion", "73": "File name injection",
    "552": "Exposed files", "668": "Exposed resource", "538": "Exposed files", "295": "Certificate validation flaw",
    "639": "Insecure direct object reference", "915": "Mass assignment", "1188": "Insecure default",
    "532": "Secrets in logs", "319": "Cleartext transmission", "522": "Weak credential protection",
    "613": "Session expiration flaw", "384": "Session fixation", "347": "Signature verification flaw",
}
# Most telling first: what an attacker can do before what went wrong.
_RANK = "94 95 917 1336 98 829 77 78 502 89 74 416 415 787 122 121 120 119 123 125 843 190 476 287 288 290 306 798 862 863 285 269 250 918 434 22 23 59 611 1321 352 79 601 362 427 426 807 755 200 400 770 20 284".split()


def _theme(cwes: list[str], vector: str | None) -> str | None:
    """"Use after free · over the network · no login": what the flaw is and
    what an attacker needs."""
    parts = []
    # The most precise kind: "input validation" or "access control" only
    # when nothing better is said.
    ids = [i for i in (re.sub(r"\D", "", c) for c in cwes) if i in CWE]
    best = min(ids, key=lambda i: _RANK.index(i) if i in _RANK else len(_RANK)) if ids else None
    if best:
        parts.append(CWE[best])
    v = vector or ""
    if "AV:N" in v:
        parts.append("over the network")
    elif "AV:A" in v:
        parts.append("from the local network")
    elif "AV:L" in v:
        parts.append("local access")
    elif "AV:P" in v:
        parts.append("physical access")
    if "PR:N" in v:
        parts.append("no login")
    elif "PR:L" in v:
        parts.append("any logged-in user")
    elif "PR:H" in v:
        parts.append("admin rights")
    if "UI:R" in v or "UI:A" in v or "UI:P" in v:
        parts.append("a user must act")
    return " · ".join(parts) or None


def _ver(v: str | None) -> str:
    v = re.sub(r"\s+", " ", (v or "").replace("\\", "").strip()).split(",")[0].strip()
    return v[:18]


_CLEAN = re.compile(r"^(?:[<≤] )?[\w.+:~-]{1,18}$|^all versions$")


def _short(name: str, n: int = 34) -> str:
    return name if len(name) <= n else name[: n - 1].rstrip() + "…"


def _ranges_cna(versions: list[dict]) -> list[str]:
    out = []
    for v in versions or []:
        if (v.get("status") or "affected") != "affected" or (v.get("versionType") or "").lower() == "git":
            continue
        if re.fullmatch(r"[0-9a-f]{12,40}", (v.get("lessThan") or v.get("version") or "").strip()):
            continue   # a commit, not a version
        start, lt, le = _ver(v.get("version")), _ver(v.get("lessThan")), _ver(v.get("lessThanOrEqual"))
        if lt:
            r = f"< {lt}"
        elif le:
            r = f"≤ {le}"
        elif start and start not in ("0", "*", "n/a", "unspecified"):
            r = start
        else:
            r = "all versions"
        if r not in out:
            out.append(r)
    return out


def _ranges_cpe(matches: list[dict]) -> dict[str, list[str]]:
    by: dict[str, list[str]] = {}
    for m in matches:
        if not m.get("vulnerable"):
            continue
        parts = (m.get("criteria") or "").split(":")
        if len(parts) < 6:
            continue
        name = parts[4].replace("_", " ").strip()
        name = " ".join(w.upper() if len(w) <= 3 and w.isalpha() and w not in ("for", "and", "the") else w.capitalize() for w in name.split())
        if m.get("versionEndExcluding"):
            r = f"< {_ver(m['versionEndExcluding'])}"
        elif m.get("versionEndIncluding"):
            r = f"≤ {_ver(m['versionEndIncluding'])}"
        elif m.get("versionStartIncluding") or m.get("versionStartExcluding"):
            r = f"≥ {_ver(m.get('versionStartIncluding') or m.get('versionStartExcluding'))}"
        elif parts[5] not in ("*", "-", ""):
            r = _ver(parts[5])
        else:
            r = "all versions"
        lst = by.setdefault(name, [])
        if r not in lst:
            lst.append(r)
    return by


def _impact(cna: dict | None, nvd: dict | None) -> list[str]:
    """Who is affected, in two lines at most: "PHP < 8.2.35 · < 8.3.36 +2".
    The CNA's own record first (its product names read better), else the
    NVD's CPE ranges."""
    products: list[tuple[str, list[str]]] = []
    for a in (cna or {}).get("affected") or []:
        vendor = re.sub(r"[,.]?\s+(Group|Corporation|Corp|Inc|Incorporated|Ltd|Limited|LLC|GmbH|SA|AG|Co|Foundation|Software|Project)\.?$", "",
                        (a.get("vendor") or "").strip(), flags=re.I)
        product = (a.get("product") or "").strip()
        if vendor.lower() in ("n/a", "unknown", ""):
            vendor = ""
        if product.lower() in ("n/a", "unknown"):
            product = ""
        # "PHP Group" + "PHP" → "PHP"; "Citrix NetScaler" + "ADC" → both.
        name = product if vendor and vendor.split()[0].lower() in product.lower() else " ".join(x for x in (vendor, product) if x)
        # Only ranges that read as versions ("< 14.1-73.37", not
        # "< 14.1-73.37 FIPS and NDcPP" or "< log4j-core*").
        r = [x for x in _ranges_cna(a.get("versions")) if _CLEAN.match(x) and re.search(r"\d|all", x)]
        if name and r:
            products.append((_short(name), r))
    named = [w for a in (cna or {}).get("affected") or [] for w in re.findall(r"[a-z0-9]{4,}", f"{a.get('vendor', '')} {a.get('product', '')}".lower())]
    # A vendor's record that lists a product per edition: the NVD's
    # normalised ranges read better.
    if (not products or len(products) > 3) and nvd and nvd.get("configurations"):
        matches = [m for conf in nvd.get("configurations") or [] for node in conf.get("nodes") or [] for m in node.get("cpeMatch") or []]
        cpe = list(_ranges_cpe(matches).items())
        # The vendor's own product first (Log4j before the 140 firmwares
        # that embed it).
        cpe.sort(key=lambda kv: not any(w[:5] in kv[0].lower().replace(" ", "") for w in named))
        products = [(_short(k), v) for k, v in cpe]
    lines = []
    shown = products[:2] if len(products) <= 2 else products[:1]
    for name, ranges in shown:
        exact = [r for r in ranges if not r.startswith(("<", "≤", "≥")) and r != "all versions"]
        if len(exact) > 3 and len(exact) == len(ranges):
            # A long list of exact versions: their span, not the list.
            lines.append(f"{name} {exact[0]} → {exact[-1]} ({len(exact)} versions)")
            continue
        more = f" +{len(ranges) - 3}" if len(ranges) > 3 else ""
        lines.append(f"{name} {' · '.join(ranges[:3])}{more}")
    if len(products) > 2:
        lines.append(f"and {len(products) - 1} other products")
    return lines


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


def _cna_score(containers: dict) -> tuple[float | None, str | None, str | None]:
    """A score from the CVE record itself — the CNA's, or CISA's ADP — for a
    CVE the NVD has not scored yet (often the first days)."""
    blocks = [containers.get("cna") or {}] + list(containers.get("adp") or [])
    for b in blocks:
        for m in b.get("metrics") or []:
            for key in ("cvssV3_1", "cvssV4_0", "cvssV3_0", "cvssV2_0"):
                d = m.get(key) or {}
                if d.get("baseScore") is not None:
                    return float(d["baseScore"]), (d.get("baseSeverity") or "").upper() or None, d.get("vectorString")
    return None, None, None


def _vector(cve: dict) -> str | None:
    metrics = cve.get("metrics") or {}
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
        for m in metrics.get(key) or []:
            if (m.get("cvssData") or {}).get("vectorString"):
                return m["cvssData"]["vectorString"]
    return None


async def _fetch_nvd(pool, ids: list[str]):
    """CVSS scores from the NVD for the leading candidates, at its public
    pace (5 requests per 30 seconds), into app_meta for every process."""
    global _nvd_running
    if _nvd_running:
        return
    _nvd_running = True
    queue = list(ids)
    try:
        while queue or _prio:
            urgent = bool(_prio)
            cid = _prio.pop(0) if urgent else queue.pop(0)
            cache = await _nvd_cache(pool)
            hit = cache.get(cid)
            # A breaking candidate without a score is asked again every 15
            # minutes; the others once a day, or every three days once scored.
            ttl = (900 if urgent else 86400) if not hit or hit.get("score") is None else 3 * 86400
            if hit and "impact" in hit and time.time() - hit.get("at", 0) < ttl:
                continue
            entry = {"at": time.time(), "score": None, "severity": None, "desc": None, "impact": [], "theme": None}
            nvd_cve, cwes, vector = None, [], None
            try:
                _, status, _, body = await sources.safe_get(NVD_URL + cid, {"Accept": "application/json"})
                if status == 200:
                    vulns = json.loads(body).get("vulnerabilities") or []
                    if vulns:
                        c = nvd_cve = vulns[0].get("cve") or {}
                        entry["score"], entry["severity"] = _severity(c)
                        vector = _vector(c)
                        cwes = [d.get("value", "") for w in c.get("weaknesses") or [] for d in w.get("description") or []]
                        d = next((x.get("value") for x in c.get("descriptions") or [] if x.get("lang") == "en"), "") or ""
                        entry["desc"] = re.split(r"(?<=[.!?])\s", d.strip(), 1)[0][:200] or None
                elif status in (403, 429):
                    break   # slowed down by the NVD: next round
            except Exception as e:
                logger.info("cve: NVD %s: %s", cid, e)
            # The CNA's record (cve.org): product names and versions as the
            # vendor wrote them, and its CWE when the NVD has none yet.
            cna = None
            try:
                _, status, _, body = await sources.safe_get(CNA_URL + cid, {"Accept": "application/json"})
                if status == 200:
                    containers = json.loads(body).get("containers") or {}
                    cna = containers.get("cna") or {}
                    if entry["score"] is None:
                        entry["score"], entry["severity"], v = _cna_score(containers)
                        vector = vector or v
                    if not cwes:
                        cwes = [d.get("cweId") or d.get("description", "") for p in cna.get("problemTypes") or []
                                for d in p.get("descriptions") or []]
            except Exception as e:
                logger.info("cve: cve.org %s: %s", cid, e)
            entry["impact"] = _impact(cna, nvd_cve)
            entry["theme"] = _theme(cwes, vector)
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
               bool_and(per.roundup) AS only_roundups,
               (array_agg(m.id ORDER BY m.published_at DESC))[1:60] AS ids,
               min(m.published_at) AS first
          FROM m JOIN per USING (id)
         GROUP BY m.cve""", owner_id or 0)
    if scope == "public":
        # Every CVE the shared stories quote: the pages /cve/<id> and the sitemap.
        _index.update(at=time.time(), data={r["cve"]: {
            "ids": list(r["ids"] or []), "stories": r["stories"], "sources": r["sources"],
            "first": r["first"], "latest": r["latest"], "title": r["title"]} for r in rows})
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
            "id": r["article_id"], "label": cid, "cves": [cid], "title": html.unescape(text)[:240],
            "source": r["source"] or ("CISA KEV" if k else ""), "stories": r["stories"], "sources": r["sources"],
            "published_at": last.isoformat(), "kev": bool(k), "kev_added": k.get("dateAdded") if k else None,
            "ransomware": ransom, "cvss": score, "severity": n.get("severity"),
            "impact": n.get("impact") or [], "theme": n.get("theme"),
            "record": RECORD_URL + cid, "_rank": rank,
        })
    out.sort(key=lambda x: x["_rank"], reverse=True)
    top = out[:LIMIT]
    for x in top:
        x.pop("_rank")
    # Scores for the leading candidates, for the next rounds.
    asyncio.create_task(_fetch_nvd(pool, [x["label"] for x in out[:40]]))
    return top


async def _first_seen(pool) -> dict:
    v = await pool.fetchval("SELECT value FROM app_meta WHERE key = 'cve_first_seen'")
    try:
        return json.loads(v) if v else {}
    except ValueError:
        return {}


async def breaking(pool) -> list[dict]:
    """New and severe: a CVE the shared stories quote for the first time in
    the last hour, scored 8 or more. Each stays an hour from when we first
    got it ("until")."""
    now = datetime.now(timezone.utc)
    if time.time() - _breaking["at"] < 90:
        return [x for x in _breaking["items"] if datetime.fromisoformat(x["until"]) > now]
    _breaking["at"] = time.time()
    try:
        rows = await pool.fetch("""
            SELECT upper('CVE-' || x[1]) AS cve, min(a.ingested_at) AS first,
                   (array_agg(a.id ORDER BY a.ingested_at))[1] AS article_id,
                   (array_agg(a.title ORDER BY a.ingested_at))[1] AS title,
                   (array_agg(a.feed_source ORDER BY a.ingested_at))[1] AS source,
                   count(DISTINCT a.feed_source) AS sources
              FROM articles a,
                   LATERAL regexp_matches(a.title || ' ' || left(coalesce(a.content_raw, ''), 6000),
                                          'CVE-([0-9]{4}-[0-9]{4,8})', 'gi') x
             WHERE a.ingested_at > now() - make_interval(secs => $1)
               AND a.owner_user_id IS NULL
               AND (a.title ~* 'CVE-[0-9]' OR a.content_raw ~* 'CVE-[0-9]')
             GROUP BY 1""", BREAKING_SECS + 900)
        seen = await _first_seen(pool)
        changed = False
        for r in rows:
            if r["cve"] in seen:
                continue
            # First time we get it, or an old one quoted again?
            older = await pool.fetchval("""
                SELECT 1 FROM articles
                 WHERE ingested_at < $1 AND ingested_at > now() - interval '60 days'
                   AND owner_user_id IS NULL
                   AND (title ILIKE $2 OR content_raw ILIKE $2) LIMIT 1""", r["first"], f"%{r['cve']}%")
            seen[r["cve"]] = {"first": r["first"].isoformat(), "new": not older}
            changed = True
        if changed:
            limit = (now - timedelta(days=3)).isoformat()
            seen = {k: v for k, v in seen.items() if v["first"] > limit}
            await pool.execute("""INSERT INTO app_meta (key, value) VALUES ('cve_first_seen', $1)
                                  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                               json.dumps(seen))
        nvd = await _nvd_cache(pool)
        kev = _kev["data"]
        items = []
        for r in rows:
            first = datetime.fromisoformat(seen[r["cve"]]["first"])
            if not seen[r["cve"]]["new"] or now - first > timedelta(seconds=BREAKING_SECS):
                continue
            n = nvd.get(r["cve"])
            if not n or n.get("score") is None:
                if r["cve"] not in _prio:
                    _prio.append(r["cve"])
                continue
            if n["score"] < BREAKING_SCORE:
                continue
            k = kev.get(r["cve"])
            items.append({
                "id": r["article_id"], "label": r["cve"], "cves": [r["cve"]],
                "title": html.unescape(r["title"] or "")[:240], "source": r["source"], "sources": r["sources"],
                "cvss": n["score"], "severity": "CRITICAL", "impact": n.get("impact") or [], "theme": n.get("theme"),
                "kev": bool(k), "first_seen": first.isoformat(),
                "until": (first + timedelta(seconds=BREAKING_SECS)).isoformat(), "record": RECORD_URL + r["cve"],
            })
        items.sort(key=lambda x: (-x["cvss"], x["first_seen"]))
        _breaking["items"] = items
        if _prio:
            asyncio.create_task(_fetch_nvd(pool, []))
    except Exception:
        logger.exception("cve: breaking failed")
    return [x for x in _breaking["items"] if datetime.fromisoformat(x["until"]) > now]


async def mention_index(pool) -> dict:
    """CVE → {ids, stories, sources, first, latest} over the last 60 days."""
    if not _index["data"] or time.time() - _index["at"] > TTL:
        await top(pool)
        if not _index["data"]:
            # top() served a stale list while it recomputes: wait for it once.
            await _compute(pool, 0, "public")
    return _index["data"]


def want(pool, cid: str):
    """Fetch this CVE's severity and products soon (a page asked for it)."""
    if cid not in _prio and len(_prio) < 300:
        _prio.append(cid)
    if not _nvd_running:
        asyncio.create_task(_fetch_nvd(pool, []))


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
