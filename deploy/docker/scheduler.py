#!/usr/bin/env python3
"""The Docker worker: the work of the systemd timers (deploy/systemd), each
job in its own loop, so that a long translation run does not hold back the
social worker. At its first start it also subscribes FreshRSS to the shared
feeds (catalog/sources/active.txt), when it follows none:
AXNEWS_IMPORT_FEEDS=0 leaves FreshRSS as it is."""
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

APP = Path(__file__).resolve().parents[2]
BACKEND = os.getenv("AXNEWS_LOCAL_URL", "http://backend:8000")
FRESHRSS = os.getenv("FRESHRSS_BASE_URL", "http://freshrss").rstrip("/") + "/api/greader.php"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("scheduler")


def backend(method: str, path: str):
    def job():
        r = httpx.request(method, BACKEND + path, timeout=1800,
                          headers={"X-Internal-Token": os.environ.get("INTERNAL_SYNC_TOKEN", "")})
        return f"HTTP {r.status_code} {r.text[:160]}"
    return job


def script(*cmd: str):
    def job():
        p = subprocess.run([*cmd], cwd=APP, capture_output=True, text=True, timeout=3600)
        out = (p.stdout + p.stderr).strip().splitlines()
        return f"exit {p.returncode}" + (f": {out[-1][:160]}" if out else "")
    return job


# name, every (seconds), the work: deploy/systemd/*.timer and *.service.
JOBS = [
    ("sync", 600, backend("POST", "/api/tv/refresh")),
    ("sources", 300, script(sys.executable, "sources-worker.py")),
    ("translate", 600, script(sys.executable, "translate-standalone.py")),
    ("images", 3600, backend("POST", "/api/fetch-images?limit=120")),
    ("dedup", 3600, script("bash", "dedup-worker.sh")),
    ("purge", 7 * 86400, backend("DELETE", "/api/purge")),
    ("social", 300, script(sys.executable, "social-worker.py")),
]
if os.getenv("AXNEWS_INDEXNOW") == "1":
    JOBS.append(("seo", 3600, script(sys.executable, "seo-worker.py")))


def loop(name: str, every: int, job, delay: float):
    time.sleep(delay)
    while True:
        start = time.monotonic()
        try:
            log.info("%s: %s", name, job())
        except Exception as e:
            log.warning("%s: %s: %s", name, type(e).__name__, str(e)[:200])
        time.sleep(max(30.0, every - (time.monotonic() - start)))


def import_feeds():
    """Subscribes FreshRSS to the shared feeds, with the catalog's titles
    and categories (the stories' sources and topics), if it follows none."""
    if os.getenv("AXNEWS_IMPORT_FEEDS", "1") == "0":
        return
    user, password = os.getenv("FRESHRSS_USER", "axnews"), os.environ.get("FRESHRSS_API_PASS", "")
    with httpx.Client(timeout=60) as c:
        for _ in range(60):                      # FreshRSS installs itself on its first start
            try:
                r = c.post(FRESHRSS + "/accounts/ClientLogin", data={"Email": user, "Passwd": password})
                if r.status_code == 200 and "Auth=" in r.text:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(10)
        else:
            log.warning("freshrss: no login after 10 minutes; feeds not imported")
            return
        h = {"Authorization": "GoogleLogin auth=" + dict(l.split("=", 1) for l in r.text.splitlines() if "=" in l)["Auth"]}
        if c.get(FRESHRSS + "/reader/api/0/subscription/list?output=json", headers=h).json().get("subscriptions"):
            return
        feeds = [l.split("|") for l in (APP / "catalog" / "sources" / "active.txt").read_text().splitlines()
                 if l.strip() and not l.startswith("#") and l.count("|") >= 4]
        token = c.get(FRESHRSS + "/reader/api/0/token", headers=h).text.strip()
        done = 0
        for category, _lang, _region, title, url, *_ in feeds:
            try:
                q = c.post(FRESHRSS + "/reader/api/0/subscription/quickadd", headers=h,
                           data={"quickadd": url.strip(), "T": token}).json()
                sid = q.get("streamId")
                if sid:
                    c.post(FRESHRSS + "/reader/api/0/subscription/edit", headers=h, data={
                        "ac": "edit", "s": sid, "t": title.strip(), "a": f"user/-/label/{category.strip()}", "T": token})
                    done += 1
            except (httpx.HTTPError, ValueError) as e:
                log.warning("freshrss: %s: %s", url.strip(), e)
        log.info("freshrss: subscribed to %d of %d shared feeds", done, len(feeds))


if __name__ == "__main__":
    threading.Thread(target=import_feeds, daemon=True).start()
    for i, (name, every, job) in enumerate(JOBS):
        threading.Thread(target=loop, args=(name, every, job, 20 + 15 * i), daemon=True).start()
    while True:
        time.sleep(3600)
