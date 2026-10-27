"""social-worker.py with fake networks: nothing leaves the machine."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import DB, ROOT, with_db


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB or "postgresql:///unused")
    for k, v in {"MASTODON_BASE_URL": "https://example.invalid", "MASTODON_TOKEN": "fake",
                 "BLUESKY_HANDLE": "fake", "BLUESKY_APP_PASSWORD": "fake"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("MASTODON_VISIBILITY", raising=False)
    spec = importlib.util.spec_from_file_location("social_worker", ROOT / "social-worker.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    sw.calls, sw.fail, sw.feed = [], set(), []

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            class R:
                def json(self_): return {"breaking": sw.feed}
            return R()

    async def mastodon(client, b, visibility):
        sw.calls.append(("mastodon", b["label"], visibility))
        if "mastodon-raises" in sw.fail:
            "Bearer <jeton copié>".encode("ascii")       # what a bad token did
        return "mastodon" not in sw.fail

    async def bluesky(client, b):
        sw.calls.append(("bluesky", b["label"]))
        return "bluesky" not in sw.fail

    monkeypatch.setattr(sw.httpx, "AsyncClient", Client)
    sw.mastodon, sw.bluesky = mastodon, bluesky
    return sw


def cve(n, cvss=9.1, kev=False):
    return {"label": f"CVE-2026-{n:05d}", "cvss": cvss, "kev": kev, "impact": ["Foo < 1.2"], "theme": "x",
            "first_seen": f"2026-10-27T08:{n % 60:02d}:00+00:00"}


async def run(sw, feed):
    sw.feed, sw.calls[:] = feed, []
    await sw.main()
    return list(sw.calls)


async def age(pool, minutes):
    """Moves every remembered post `minutes` into the past."""
    s = json.loads(await pool.fetchval("SELECT value FROM app_meta WHERE key = 'social_posted'"))
    back = lambda t: (datetime.fromisoformat(t) - timedelta(minutes=minutes)).isoformat()
    s["posts"] = {k: {n: back(t) for n, t in v.items()} for k, v in s["posts"].items()}
    if "mastodon_public" in s:
        s["mastodon_public"] = back(s["mastodon_public"])
    await pool.execute("UPDATE app_meta SET value = $1 WHERE key = 'social_posted'", json.dumps(s))


def test_order_public_slot_and_three_an_hour(worker):
    async def t(pool):
        # The v1.3.0 state ({cve: date}) is taken over: an old post counts as done.
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await pool.execute("INSERT INTO app_meta (key, value) VALUES ('social_posted', $1)",
                           json.dumps({"CVE-2026-00099": old}))
        calls = await run(worker, [cve(2, 8.6), cve(1, 9.8), {"label": "CVE-2026-00099", "cvss": 8.5}])
        assert calls == [("mastodon", "CVE-2026-00001", "public"), ("bluesky", "CVE-2026-00001"),
                         ("mastodon", "CVE-2026-00002", "unlisted"), ("bluesky", "CVE-2026-00002")]
        # The third of the hour goes, the fourth waits.
        calls = await run(worker, [cve(1), cve(2), cve(3, 8.2), cve(4, 8.1)])
        assert calls == [("mastodon", "CVE-2026-00003", "unlisted"), ("bluesky", "CVE-2026-00003")]
        # An hour later: room again, and the public slot.
        await age(pool, 61)
        calls = await run(worker, [cve(4, 8.1)])
        assert calls == [("mastodon", "CVE-2026-00004", "public"), ("bluesky", "CVE-2026-00004")]
        # Same score: exploited first.
        await age(pool, 61)
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


def test_text(worker):
    b = {"label": "CVE-2026-80097", "cvss": 8.6, "base_severity": "HIGH", "kev": True,
         "impact": ["Microsoft Authenticator for Andro… < 6.2606.4246"],
         "theme": "Authentication bypass · local access · no login · a user must act"}
    text = worker.text_for(b, 300)
    assert text.startswith("🚨 Breaking: CVE-2026-80097 — High 8.6 · exploited\n")
    assert text.endswith("https://ax-news.com/cve/CVE-2026-80097\n#CVE #infosec") and len(text) <= 300
    assert worker.rating({"cvss": 9.8}) == "Critical 9.8" and worker.rating({"cvss": 8.1}) == "High 8.1"
