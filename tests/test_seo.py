"""What search engines read (backend/seo.py): valid XML and JSON-LD."""
import json
from datetime import date, datetime, timezone

from defusedxml import minidom

import seo


def test_rss_is_valid_and_escaped():
    out = seo.rss("AX-NEWS <CVE> watch", "https://ax-news.com/cve", "Flaws & fixes",
                  [{"title": "PHP < 8.2.35 & friends", "link": "https://ax-news.com/cve/CVE-2026-109618",
                    "guid": "CVE-2026-109618", "date": datetime(2026, 10, 27, tzinfo=timezone.utc)}])
    doc = minidom.parseString(out.encode())
    items = doc.getElementsByTagName("item")
    assert len(items) == 1
    assert items[0].getElementsByTagName("title")[0].firstChild.data == "PHP < 8.2.35 & friends"
    assert "Tue, 27 Oct 2026" in items[0].getElementsByTagName("pubDate")[0].firstChild.data


def test_sitemap_is_valid():
    out = seo.urlset([("/topic/Cybersecurity", date(2026, 10, 27), "hourly"), ("/cve?a=1&b=2", None, None)])
    locs = [n.firstChild.data for n in minidom.parseString(out.encode()).getElementsByTagName("loc")]
    assert locs == [seo.APP_URL + "/topic/Cybersecurity", seo.APP_URL + "/cve?a=1&b=2"]


def test_opml_is_valid():
    out = seo.opml("Technology", [{"title": 'A "quoted" & <odd> feed', "url": "https://x.org/feed?a=1&b=2",
                                   "site_url": "https://x.org/"}])
    o = minidom.parseString(out.encode()).getElementsByTagName("outline")[0]
    assert o.getAttribute("text") == 'A "quoted" & <odd> feed' and o.getAttribute("xmlUrl") == "https://x.org/feed?a=1&b=2"


def test_json_ld():
    ld = seo.ld_page("CollectionPage", "Cybersecurity news", "/topic/Cybersecurity",
                     [("AX-NEWS", "/"), ("Topics", "/topics"), ("Cybersecurity", "/topic/Cybersecurity")],
                     items=[{"id": 7, "title": "A story"}])
    json.dumps(ld)
    page, crumbs = ld["@graph"]
    assert page["@type"] == "CollectionPage" and page["url"].endswith("/topic/Cybersecurity")
    assert page["mainEntity"]["itemListElement"][0]["url"].endswith("/go/7")
    assert [c["position"] for c in crumbs["itemListElement"]] == [1, 2, 3]


def test_day_pages_that_never_were_or_are_gone():
    today = date(2026, 11, 9)
    assert seo.parse_day("2026-11-09", today) == (today, 200)
    assert seo.parse_day("2026-10-10", today) == (date(2026, 10, 10), 200)        # 30 days: still kept
    assert seo.parse_day("2026-10-09", today) == (None, 410)                      # older: gone
    assert seo.parse_day("2026-11-10", today) == (None, 404)                      # the future
    assert seo.parse_day("2026-02-30", today) == (None, 404)
    assert seo.parse_day("20261012", today) == (None, 404)                        # only the canonical form


def test_every_template_parses():
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader
    folder = Path(seo.__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(folder))
    for t in folder.glob("*.html"):
        env.get_template(t.name)


def test_a_quiet_topic_shows_its_latest_stories():
    from conftest import add_story, with_db

    async def t(pool):
        seo._cache.clear()
        await add_story(pool, "Four days old", hours_ago=96)
        data = await seo.topic_page(pool, "Cybersecurity")
        assert not data["recent"] and [s["title"] for s in data["items"]] == ["Four days old"]

        seo._cache.clear()
        await add_story(pool, "An hour old", hours_ago=1)
        data = await seo.topic_page(pool, "Cybersecurity")
        assert data["recent"] and [s["title"] for s in data["items"]] == ["An hour old"]

        seo._cache.clear()
        await pool.execute("UPDATE articles SET published_at = now() - interval '40 days'")
        assert await seo.topic_page(pool, "Cybersecurity") is None                # nothing left: a 404
    with_db(t)
