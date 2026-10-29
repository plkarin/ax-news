"""social-worker.py with fake networks: nothing leaves the machine."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import DB, ROOT, with_db

PARIS_0900 = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)      # 09:00 in Paris (UTC+1)


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB or "postgresql:///unused")
    for k, v in {"MASTODON_BASE_URL": "https://example.invalid", "MASTODON_TOKEN": "fake",
                 "BLUESKY_HANDLE": "fake", "BLUESKY_APP_PASSWORD": "fake",
                 "SOCIAL_TZ": "Europe/Paris", "SOCIAL_DIGEST_AT": "08:30"}.items():
        monkeypatch.setenv(k, v)
    for k in ("MASTODON_VISIBILITY", "SOCIAL_KEV"):
        monkeypatch.delenv(k, raising=False)
    spec = importlib.util.spec_from_file_location("social_worker", ROOT / "social-worker.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    sw.calls, sw.fail, sw.watch, sw.asked = [], set(), {}, []
    sw.clock = [datetime(2026, 10, 29, 16, 0, tzinfo=timezone.utc)]       # 17:00 in Paris: no daily post

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            sw.asked.append((url, params))

            class R:
                def raise_for_status(self_): pass
                def json(self_): return sw.watch
            return R()

    async def mastodon(client, key, text, visibility):
        sw.calls.append(("mastodon", key, visibility))
        if "mastodon-raises" in sw.fail:
            "Bearer <jeton copié>".encode("ascii")       # what a bad token did
        return "mastodon" not in sw.fail

    async def bluesky(client, key, text):
        assert len(text) <= 300, text
        sw.calls.append(("bluesky", key))
        return "bluesky" not in sw.fail

    monkeypatch.setattr(sw.httpx, "AsyncClient", Client)
    monkeypatch.setattr(sw, "_now", lambda: sw.clock[0])
    sw.mastodon, sw.bluesky = mastodon, bluesky
    return sw


def cve(n, cvss=9.1, kev=False):
    return {"label": f"CVE-2026-{n:05d}", "cvss": cvss, "kev": kev, "impact": ["Foo < 1.2"], "theme": "x",
            "first_seen": f"2026-10-27T08:{n % 60:02d}:00+00:00"}


def kev(n, cvss=8.8, added="2026-10-29", ransomware=False):
    return {"label": f"CVE-2026-{n:05d}", "kev": True, "kev_added": added, "cvss": cvss, "base_severity": "HIGH",
            "name": "Citrix NetScaler Improper Input Validation Vulnerability", "product": "Citrix NetScaler",
            "ransomware": ransomware, "impact": ["NetScaler ADC < 14.1-43.56"], "theme": "x"}


async def run(sw, breaking=(), kev_added=(), top=(), day="2026-10-28"):
    sw.watch = {"breaking": list(breaking), "kev_added": list(kev_added), "day": {"date": day, "top": list(top)}}
    sw.calls[:] = []
    await sw.main()
    return list(sw.calls)


async def age(pool, sw, minutes):
    """Moves the clock `minutes` forward."""
    sw.clock[0] += timedelta(minutes=minutes)


def test_order_public_slot_and_three_an_hour(worker):
    async def t(pool):
        # The v1.3.0 state ({cve: date}) is taken over: an old post counts as done.
        old = (worker.clock[0] - timedelta(hours=2)).isoformat()
        await pool.execute("INSERT INTO app_meta (key, value) VALUES ('social_posted', $1)",
                           json.dumps({"CVE-2026-00099": old}))
        calls = await run(worker, [cve(2, 8.6), cve(1, 9.8), {"label": "CVE-2026-00099", "cvss": 8.5}])
        assert calls == [("mastodon", "CVE-2026-00001", "public"), ("bluesky", "CVE-2026-00001"),
                         ("mastodon", "CVE-2026-00002", "unlisted"), ("bluesky", "CVE-2026-00002")]
        assert worker.asked[0][1] == {"day": "2026-10-28", "tz": "Europe/Paris"}
        # The third of the hour goes, the fourth waits.
        calls = await run(worker, [cve(1), cve(2), cve(3, 8.2), cve(4, 8.1)])
        assert calls == [("mastodon", "CVE-2026-00003", "unlisted"), ("bluesky", "CVE-2026-00003")]
        # An hour later: room again, and the public slot.
        await age(pool, worker, 61)
        calls = await run(worker, [cve(4, 8.1)])
        assert calls == [("mastodon", "CVE-2026-00004", "public"), ("bluesky", "CVE-2026-00004")]
        # Same score: exploited first.
        await age(pool, worker, 61)
        calls = await run(worker, [cve(5, 9.0), cve(6, 9.0, kev=True)])
        assert [c[1] for c in calls if c[0] == "bluesky"] == ["CVE-2026-00006", "CVE-2026-00005"]
    with_db(t)


def test_one_network_down_does_not_stop_the_other(worker):
    async def t(pool):
        worker.fail.add("mastodon-raises")
        calls = await run(worker, [cve(7)])
        assert calls == [("mastodon", "CVE-2026-00007", "public"), ("bluesky", "CVE-2026-00007")]
        worker.fail.clear()
        calls = await run(worker, [cve(7)])                 # Mastodon again, Bluesky not twice
        assert calls == [("mastodon", "CVE-2026-00007", "public")]
    with_db(t)


def test_unlisted_everywhere(worker, monkeypatch):
    monkeypatch.setenv("MASTODON_VISIBILITY", "unlisted")

    async def t(pool):
        calls = await run(worker, [cve(8)])
        assert calls[0] == ("mastodon", "CVE-2026-00008", "unlisted")
    with_db(t)


def test_kev_additions(worker):
    async def t(pool):
        # A breaking CVE an hour ago is not posted again when CISA adds it.
        calls = await run(worker, [cve(20)])
        await age(pool, worker, 61)
        calls = await run(worker, [], [kev(20), kev(21), kev(22, ransomware=True)])
        assert calls == [("mastodon", "kev:CVE-2026-00021", "public"), ("bluesky", "kev:CVE-2026-00021"),
                         ("mastodon", "kev:CVE-2026-00022", "unlisted"), ("bluesky", "kev:CVE-2026-00022")]
        assert await run(worker, [], [kev(20), kev(21), kev(22)]) == []      # each once
        # Not ready (its score being read): waits.
        await age(pool, worker, 61)
        assert await run(worker, [], [{**kev(25), "ready": False}]) == []
        calls = await run(worker, [], [kev(25)])
        assert calls[1] == ("bluesky", "kev:CVE-2026-00025")
    with_db(t)


def test_kev_off(worker, monkeypatch):
    monkeypatch.setenv("SOCIAL_KEV", "0")

    async def t(pool):
        assert await run(worker, [], [kev(23)]) == []
    with_db(t)


def test_daily_post(worker):
    top = [{"label": "CVE-2026-88771", "cvss": 9.3, "base_severity": "CRITICAL", "kev": True,
            "product": "Citrix NetScaler", "sources": 5},
           {"label": "CVE-2026-86950", "cvss": 8.8, "base_severity": "HIGH", "kev": True,
            "product": "Apple Multiple Products", "sources": 4},
           {"label": "CVE-2026-109618", "cvss": 9.2, "base_severity": "CRITICAL", "kev": False,
            "product": "PHP", "sources": 3}]

    async def t(pool):
        # 17:00 in Paris: not its time.
        assert await run(worker, top=top) == []
        # 09:00 the next morning, after a breaking CVE took the public slot at 08:50:
        # Bluesky now, Mastodon once the public slot is free.
        worker.clock[0] = PARIS_0900 - timedelta(minutes=10)
        await run(worker, [cve(30)], top=[])
        worker.clock[0] = PARIS_0900
        calls = await run(worker, top=top, day="2026-10-28")
        assert calls == [("bluesky", "digest:2026-10-28")]
        await age(pool, worker, 55)                         # 09:55: the public slot is free
        calls = await run(worker, top=top, day="2026-10-28")
        assert calls == [("mastodon", "digest:2026-10-28", "public")]
        assert await run(worker, top=top, day="2026-10-28") == []           # once a day
        # 13:00: the window is over; nothing for a day without a post.
        worker.clock[0] = PARIS_0900 + timedelta(hours=4)
        assert await run(worker, top=top, day="2026-10-29") == []
    with_db(t)


def test_texts(worker):
    b = {"label": "CVE-2026-80097", "cvss": 8.6, "base_severity": "HIGH", "kev": True,
         "impact": ["Microsoft Authenticator for Andro… < 6.2606.4246"],
         "theme": "Authentication bypass · local access · no login · a user must act"}
    text = worker.text_for(b, 300)
    assert text.startswith("🚨 Breaking: CVE-2026-80097 — High 8.6 · exploited\n")
    assert text.endswith("https://ax-news.com/cve/CVE-2026-80097\n#CVE #infosec") and len(text) <= 300
    assert worker.rating({"cvss": 9.8}) == "Critical 9.8" and worker.rating({"cvss": 8.1}) == "High 8.1"

    k = worker.kev_text(kev(24, ransomware=True), 300)
    assert k.startswith("⚠️ Exploited in the wild: CVE-2026-00024\nCitrix NetScaler Improper Input Validation")
    assert "Added to CISA KEV · High 8.8 · used by ransomware" in k and k.endswith("#CVE #KEV #infosec")

    day = {"date": "2026-10-28", "top": [
        {"label": "CVE-2026-88771", "cvss": 9.3, "base_severity": "CRITICAL", "kev": True, "product": "Citrix NetScaler"},
        {"label": "CVE-2026-86950", "cvss": 8.8, "base_severity": "HIGH", "kev": True,
         "product": "Apple Multiple Products, with a very long name indeed"},
        {"label": "CVE-2026-109618", "cvss": None, "kev": False, "product": "PHP"}]}
    long_text, short_text = worker.digest_text(day, 500), worker.digest_text(day, 300)
    assert long_text.startswith("🛡️ The CVEs that mattered · Wednesday 28 October\n"
                                "1. CVE-2026-88771 · Critical 9.3 · exploited — Citrix NetScaler\n")
    assert "3. CVE-2026-109618 — PHP" in long_text and long_text.endswith("https://ax-news.com/cve\n#CVE #infosec")
    assert len(short_text) <= 300 and short_text.endswith("#CVE #infosec")
