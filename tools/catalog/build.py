"""Checks every feed of catalog/sources/*.txt and writes catalog/feeds.json.

    backend/venv/bin/python -I tools/catalog/build.py [--only FILE] [--keep-dead]

Each line is fetched for real (through the backend's SSRF guard); when an
address is a page rather than a feed, the feed it announces is used. A feed
that answers with no story, or none in the last year, is left out: the
catalog only offers feeds that work today. The shared feeds (active.txt) are
always kept — FreshRSS fetches them, whatever answers here.
"""
import asyncio, json, os, re, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import sources  # noqa: E402

CAT = os.path.join(ROOT, 'catalog')
TAX = json.load(open(os.path.join(CAT, 'taxonomy.json')))
DOMAIN = {c['key']: c['domain'] for c in TAX['categories']}
YEAR = 365 * 86400


def read_sources(only=None):
    rows = []
    for name in sorted(os.listdir(os.path.join(CAT, 'sources'))):
        if not name.endswith('.txt') or (only and name != only):
            continue
        active = name == 'active.txt'
        for n, line in enumerate(open(os.path.join(CAT, 'sources', name)), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) != 6:
                sys.exit(f'{name}:{n}: expected 6 fields, got {len(parts)}')
            cat, lang, region, title, url, site = parts
            if cat not in DOMAIN:
                sys.exit(f'{name}:{n}: unknown category {cat}')
            rows.append(dict(category=cat, domain=DOMAIN[cat], lang=lang, region=region, title=title,
                             url=url, site_url=site or None, active=active, file=name, line=n))
    return rows


def detect_lang(entries):
    from translation import _script_language
    text = ' '.join(((e.get('title') or '') + ' ' + re.sub(r'<[^>]+>', ' ', e.get('summary') or '')[:200])
                    for e in entries[:25])
    script = _script_language(text)
    if script:
        return script
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0
        return detect(text[:4000]) if len(text.strip()) > 40 else None
    except Exception:
        return None


def newest(entries):
    ts = [sources._entry_time(e) for e in entries]
    return max(ts) if ts else None


host_locks = defaultdict(lambda: asyncio.Semaphore(2))


async def check(row, sem):
    async with sem:
        host = urlparse(row['url']).netloc
        async with host_locks[host]:
            t0 = time.time()
            for attempt in (row['url'], row['site_url']):
                if not attempt:
                    continue
                try:
                    found = await asyncio.wait_for(sources.discover(attempt), 40)
                except Exception as e:
                    row['error'] = f'{type(e).__name__}: {str(e)[:120]}'
                    continue
                best = max(found, key=lambda f: f['count'])
                parsed = sources.recent_feed(best['url']) or {}
                entries = parsed.get('entries') or []
                row.update(feed_url=best['url'], items=len(entries), feed_title=best['title'],
                           site_url=row['site_url'] or best.get('site_url'))
                nw = newest(entries)
                row['newest'] = nw.isoformat() if nw else None
                row['detected_lang'] = detect_lang(entries)
                row.pop('error', None)
                break
            row['secs'] = round(time.time() - t0, 1)
            return row


async def main():
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    keep_dead = '--keep-dead' in sys.argv
    rows = read_sources(only)
    seen, uniq = set(), []
    for r in rows:
        k = r['url'].rstrip('/').lower()
        if k in seen:
            print(f"duplicate: {r['file']}:{r['line']} {r['url']}")
            continue
        seen.add(k); uniq.append(r)
    sem = asyncio.Semaphore(16)
    done = 0
    results = []
    for coro in asyncio.as_completed([check(r, sem) for r in uniq]):
        r = await coro; done += 1; results.append(r)
        if done % 50 == 0:
            print(f'{done}/{len(uniq)}', flush=True)
    now = datetime.now(timezone.utc)
    keep, dropped = [], []
    for r in sorted(results, key=lambda r: (r['file'], r['line'])):
        fresh = r.get('newest') and (now - datetime.fromisoformat(r['newest'])).total_seconds() < YEAR
        ok = r.get('items') and fresh
        if r['active'] or ok or keep_dead:
            keep.append(r)
        else:
            dropped.append(r)
    report = os.path.join(CAT, 'build-report.txt')
    with open(report, 'w') as f:
        for r in dropped:
            why = r.get('error') or ('no stories' if not r.get('items') else f"stale since {r.get('newest', '')[:10]}")
            f.write(f"{r['file']}:{r['line']}\t{r['title']}\t{r['url']}\t{why}\n")
        for r in keep:
            if r.get('detected_lang') and r['lang'] not in ('?', r['detected_lang']) and not (
                    r['lang'] in ('zh', 'nb') and r['detected_lang'] in ('zh-cn', 'zh-tw', 'no')):
                f.write(f"LANG {r['file']}:{r['line']}\t{r['title']}\tdeclared {r['lang']}, looks {r['detected_lang']}\n")
    out, urls = [], set()
    # Two lines can lead to one feed (a site and its feed): the active one,
    # or else the first, is kept.
    for r in sorted(keep, key=lambda r: not r['active']):
        u = (r.get('feed_url') or r['url']).rstrip('/').lower()
        if u in urls:
            continue
        urls.add(u)
        lang = r['lang'] if r['lang'] != '?' else (r.get('detected_lang') or 'en')
        lang = {'zh-cn': 'zh', 'zh-tw': 'zh', 'no': 'nb'}.get(lang, lang)
        out.append({k: v for k, v in dict(
            url=r.get('feed_url') or r['url'], title=r['title'], site_url=r.get('site_url'),
            category=r['category'], domain=r['domain'], lang=lang, region=r['region'],
            active=r['active'], items=r.get('items') or 0, newest=r.get('newest'),
        ).items()})
    if not only:
        with open(os.path.join(CAT, 'feeds.json'), 'w') as f:
            json.dump({'checked_at': now.isoformat(timespec='seconds'), 'feeds': out}, f, indent=0, ensure_ascii=False)
    c = Counter(r['domain'] for r in out)
    print(f'kept {len(out)} (active {sum(r["active"] for r in out)}), dropped {len(dropped)} → {report}')
    print(dict(c))

asyncio.run(main())
