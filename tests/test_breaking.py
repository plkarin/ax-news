"""Breaking CVEs (backend/cve.py): new, severe, and news."""
import json
import time
from datetime import datetime, timedelta, timezone

from conftest import add_story, with_db

import cve

NOW = datetime.now(timezone.utc)


def entry(score, severity, published_days_ago):
    return {"at": time.time(), "score": score, "severity": severity, "desc": None, "impact": ["Foo < 1.2"],
            "theme": "Use after free · over the network · no login",
            "published": (NOW - timedelta(days=published_days_ago)).isoformat()}


async def breaking(pool, cache):
    await pool.execute("INSERT INTO app_meta (key, value) VALUES ('nvd_cache', $1)", json.dumps(cache))
    cve._breaking.update(at=0.0, items=[])
    cve._kev["data"] = {}
    return {b["label"]: b for b in await cve.breaking(pool)}


def test_breaking_takes_only_news():
    async def t(pool):
        cache = {
            "CVE-2026-9900001": entry(8.6, "HIGH", 5),
            "CVE-2026-9900002": entry(9.8, "CRITICAL", 90),      # published long ago
            **{f"CVE-2026-990000{i}": entry(9.4, "CRITICAL", 2) for i in range(3, 8)},
            "CVE-2026-9900008": entry(9.0, "CRITICAL", 2),
            "CVE-2026-9900009": entry(8.2, "HIGH", 1),
            "CVE-2026-9900010": entry(6.5, "MEDIUM", 1),         # below 8
        }
        await add_story(pool, "Foo flaw CVE-2026-9900001 patched", hours_ago=1, ingested_hours_ago=0.2)
        await add_story(pool, "Old flaw CVE-2026-9900002 resurfaces", hours_ago=1, ingested_hours_ago=0.2)
        await add_story(pool, "This month's patches", hours_ago=1, ingested_hours_ago=0.3,
                        content=" ".join(f"CVE-2026-990000{i}" for i in range(3, 8)) + " CVE-2026-9900009")
        await add_story(pool, "CVE-2026-9900008 from a feed catching up", hours_ago=72, ingested_hours_ago=0.2)
        await add_story(pool, "Weekly security roundup: CVE-2026-9900009", hours_ago=0.6, ingested_hours_ago=0.2)
        await add_story(pool, "Bar flaw CVE-2026-9900009 exploited", hours_ago=0.5, ingested_hours_ago=0.1)
        await add_story(pool, "Minor CVE-2026-9900010", hours_ago=0.5, ingested_hours_ago=0.1)
        # A CVE already in the news a month ago is not new.
        await add_story(pool, "Earlier: CVE-2026-9900011", hours_ago=24 * 30, ingested_hours_ago=24 * 30)
        await add_story(pool, "Again CVE-2026-9900011", hours_ago=0.5, ingested_hours_ago=0.1)
        cache["CVE-2026-9900011"] = entry(9.9, "CRITICAL", 3)

        got = await breaking(pool, cache)
        assert set(got) == {"CVE-2026-9900001", "CVE-2026-9900009"}
        assert got["CVE-2026-9900001"]["severity"] == "CRITICAL"          # the TV's marking
        assert got["CVE-2026-9900001"]["base_severity"] == "HIGH"         # the CVSS rating
        # The title of the story about it, not the list's nor the roundup's.
        assert got["CVE-2026-9900009"]["title"] == "Bar flaw CVE-2026-9900009 exploited"
    with_db(t)


def test_fetch_keeps_the_publication_date(monkeypatch):
    """The earlier of the NVD's and cve.org's dates goes into the cache."""
    nvd = {"vulnerabilities": [{"cve": {
        "published": "2026-10-21T15:15:40.623",
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 9.2, "baseSeverity": "CRITICAL",
                                                    "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}}]},
        "weaknesses": [{"description": [{"value": "CWE-416"}]}],
        "descriptions": [{"lang": "en", "value": "PHP uses longjmp() for out-of-memory errors."}]}}]}
    record = {"cveMetadata": {"datePublished": "2026-10-20T23:55:26.000Z"},
              "containers": {"cna": {"affected": [{"vendor": "PHP Group", "product": "PHP",
                                                   "versions": [{"version": "8.2.0", "lessThan": "8.2.35",
                                                                 "status": "affected"}]}]}}}

    async def safe_get(url, headers=None):
        return url, 200, {}, json.dumps(nvd if "nvd" in url else record)

    async def no_wait(_):
        return None
    monkeypatch.setattr(cve.sources, "safe_get", safe_get)
    monkeypatch.setattr(cve.asyncio, "sleep", no_wait)

    async def t(pool):
        await cve._fetch_nvd(pool, ["CVE-2026-109618"])
        e = json.loads(await pool.fetchval("SELECT value FROM app_meta WHERE key = 'nvd_cache'"))["CVE-2026-109618"]
        assert e["score"] == 9.2 and e["severity"] == "CRITICAL"
        assert e["published"].startswith("2026-10-20T23:55:26")            # cve.org's, the earlier
        assert e["impact"] and "PHP" in e["impact"][0]
    with_db(t)
