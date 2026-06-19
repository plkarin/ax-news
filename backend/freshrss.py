import httpx, re
from datetime import datetime, timezone

BASE = None
USER = None
PASS = None

async def authenticate(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{BASE}/api/greader.php/accounts/ClientLogin",
        data={"Email": USER, "Passwd": PASS}
    )
    m = re.search(r"Auth=(.+)", r.text)
    if not m:
        raise RuntimeError(f"FreshRSS auth failed: {r.text}")
    return m.group(1).strip()

#async def fetch_articles(client: httpx.AsyncClient, token: str, n=100) -> list:
#    r = await client.get(
#        f"{BASE}/api/greader.php/reader/api/0/stream/contents/reading-list",
#        params={"n": n, "output": "json"},
#        headers={"Authorization": f"GoogleLogin auth={token}"}
#    )
#    r.raise_for_status()
#    return r.json().get("items", [])

async def fetch_articles(client: httpx.AsyncClient, token: str, n=500) -> list:
    all_items = []
    continuation = None
    max_pages = 30  # max 5000 articles par sync

    for _ in range(max_pages):
        params = {"n": n, "output": "json"}
        if continuation:
            params["c"] = continuation

        r = await client.get(
            f"{BASE}/api/greader.php/reader/api/0/stream/contents/reading-list",
            params=params,
            headers={"Authorization": f"GoogleLogin auth={token}"}
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_items.extend(items)

        continuation = data.get("continuation")
        if not continuation or len(items) < n:
            break

    return all_items

def extract_image(html: str) -> str | None:
    if not html:
        return None
    m = re.search(r'<img[^>]+src=["\']( https?://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', html, re.I)
    if m:
        return m.group(1)
    return None

def extract_category(item: dict) -> str:
    for tag in item.get("categories", []):
        m = re.search(r"label/([^\"]+)", tag)
        if m:
            return m.group(1)
    stream_id = item.get("origin", {}).get("streamId", "")
    m = re.search(r"label/([^\"]+)", stream_id)
    return m.group(1) if m else ""

def parse_article(item: dict) -> dict:
    content = item.get("summary", {}).get("content", "") or \
              item.get("content", {}).get("content", "")
    pub = item.get("published")
    return {
        "freshrss_id": item.get("id", ""),
        "feed_source":  item.get("origin", {}).get("title", ""),
        "category":     extract_category(item),
        "title":        item.get("title", "Sans titre"),
        "url":          (item.get("canonical") or item.get("alternate") or [{}])[0].get("href", ""),
        "published_at": datetime.fromtimestamp(pub, tz=timezone.utc) if pub else None,
        "content_raw":  content,
        "image_url":    extract_image(content),
    }
