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


def test_kev_added(monkeypatch):
    """CISA's additions of the last two days, with what the cache knows."""
    asked = []
    monkeypatch.setattr(cve, "want", lambda pool, cid: asked.append(cid))
    today = NOW.date().isoformat()
    old = (NOW - timedelta(days=5)).date().isoformat()
    monkeypatch.setitem(cve._kev, "at", time.time())
    monkeypatch.setitem(cve._kev, "data", {
        "CVE-2026-0001": {"cveID": "CVE-2026-0001", "vendorProject": "Citrix", "product": "NetScaler",
                          "vulnerabilityName": "Citrix NetScaler Improper Input Validation Vulnerability",
                          "dateAdded": today, "knownRansomwareCampaignUse": "Known"},
        "CVE-2019-0002": {"cveID": "CVE-2019-0002", "vendorProject": "Microsoft", "product": "Windows",
                          "vulnerabilityName": "Microsoft Windows Use-After-Free Vulnerability", "dateAdded": today},
        "CVE-2025-0003": {"cveID": "CVE-2025-0003", "vendorProject": "Apple", "product": "iOS", "dateAdded": old},
    })

    async def t(pool):
        await pool.execute("INSERT INTO app_meta (key, value) VALUES ('nvd_cache', $1)",
                           json.dumps({"CVE-2026-0001": entry(9.3, "CRITICAL", 2)}))
        got = {k["label"]: k for k in await cve.kev_added(pool)}
        assert set(got) == {"CVE-2026-0001", "CVE-2019-0002"}          # an old CVE newly exploited counts
        assert got["CVE-2026-0001"]["product"] == "Citrix NetScaler" and got["CVE-2026-0001"]["ransomware"]
        assert got["CVE-2026-0001"]["cvss"] == 9.3 and got["CVE-2019-0002"]["cvss"] is None
        assert got["CVE-2026-0001"]["ready"] and not got["CVE-2019-0002"]["ready"]
        assert asked == ["CVE-2019-0002"]                               # its score is asked for
    with_db(t)


def test_short_names():
    assert cve.short_name({"vendorProject": "Citrix", "product": "NetScaler"}, None) == "Citrix NetScaler"
    assert cve.short_name({"vendorProject": "Cisco", "product": "Cisco IOS XE"}, None) == "Cisco IOS XE"
    assert cve.short_name({"vendorProject": "PHP Group", "product": "PHP"}, None) == "PHP"
    assert cve.short_name(None, {"impact": ["PHP < 8.2.35 · < 8.3.36 · < 8.4.27 +1"]}) == "PHP"
    assert cve.short_name(None, {"impact": ["Windows 10 1607 < 10.0.14393.9512 and 7 other products"]}) == "Windows 10 1607"
    assert cve.short_name(None, None, "A story about a flaw") == "A story about a flaw"


def test_day_top(monkeypatch):
    """A day's CVEs, ranked by exploitation, severity and coverage."""
    monkeypatch.setitem(cve._kev, "at", time.time())
    monkeypatch.setitem(cve._kev, "data", {"CVE-2026-1002": {"cveID": "CVE-2026-1002", "vendorProject": "Citrix",
                                                             "product": "NetScaler", "dateAdded": "2026-10-01"}})
    cve._days.clear()

    async def t(pool):
        await pool.execute("INSERT INTO app_meta (key, value) VALUES ('nvd_cache', $1)", json.dumps({
            "CVE-2026-1001": entry(7.5, "HIGH", 3), "CVE-2026-1002": entry(9.8, "CRITICAL", 3),
            "CVE-2026-1003": entry(9.9, "CRITICAL", 3), "CVE-2026-1004": entry(10.0, "CRITICAL", 3)}))
        for i, source in enumerate(("Outlet A", "Outlet B", "Outlet C")):
            await add_story(pool, f"Widget flaw CVE-2026-1001 ({i})", source=source, hours_ago=5)
        await add_story(pool, "NetScaler flaw CVE-2026-1002 exploited", source="Outlet A", hours_ago=6)
        await add_story(pool, "This month's patches", source="Outlet B", hours_ago=4,
                        content="CVE-2026-1003 CVE-2026-1005 CVE-2026-1006 CVE-2026-1007")
        await add_story(pool, "CVE-2026-1004, a day earlier", source="Outlet C", hours_ago=40)
        start, end = NOW - timedelta(hours=24), NOW
        top = await cve.day_top(pool, start, end)
        assert [c["label"] for c in top] == ["CVE-2026-1002", "CVE-2026-1001"]   # 1003: a list only; 1004: the day before
        assert top[0]["kev"] and top[0]["product"] == "Citrix NetScaler" and top[1]["sources"] == 3
    with_db(t)


def test_impact_of_a_kernel_record():
    """kernel.org's records: affected from a version, fixed per branch."""
    versions = [{"version": "cef401de7be8", "lessThan": "3599e6b3cc1a", "status": "affected", "versionType": "git"},
                {"version": "3.9", "status": "affected"},
                {"version": "0", "lessThan": "3.9", "status": "unaffected", "versionType": "semver"},
                {"version": "5.10.257", "lessThanOrEqual": "5.10.*", "status": "unaffected", "versionType": "semver"},
                {"version": "6.12.91", "lessThanOrEqual": "6.12.*", "status": "unaffected", "versionType": "semver"},
                {"version": "6.18.33", "lessThanOrEqual": "6.18.*", "status": "unaffected", "versionType": "semver"},
                {"version": "7.0.10", "lessThanOrEqual": "7.0.*", "status": "unaffected", "versionType": "semver"},
                {"version": "7.1", "lessThanOrEqual": "*", "status": "unaffected", "versionType": "original_commit_for_fix"}]
    cna = {"affected": [{"vendor": "Linux", "product": "Linux", "defaultStatus": "affected", "versions": versions}]}
    assert cve._impact(cna, None) == ["Linux ≥ 3.9, fixed in 7.1 · 7.0.10 · 6.18.33 +2"]
    assert cve._kernel_stale({"impact": ["Linux 3.9"]}) and not cve._kernel_stale({"impact": cve._impact(cna, None)})
    php = {"affected": [{"vendor": "PHP Group", "product": "PHP", "versions": [
        {"version": "8.2.0", "lessThan": "8.2.35", "status": "affected"},
        {"version": "8.3.0", "lessThan": "8.3.36", "status": "affected"}]}]}
    assert cve._impact(php, None) == ["PHP < 8.2.35 · < 8.3.36"]
