# Changelog

Every release of AX-NEWS, newest first. Versions follow
[semantic versioning](https://semver.org); each is a git tag and a
[GitHub release](https://github.com/plkarin/ax-news/releases).

## v1.3.5 — 2026-10-27

### Translation
- Argos's hallucinations are refused. For a short headline it sometimes
  writes a page footer instead ("Copyright (c) 2015 SHINSEGAE. All Rights
  Reserved." for a Korean story on solar power), an apology ("I'm sorry."),
  a fragment ("2800mm" for a Chinese title of 22 signs) or the original
  script ("继 展 展"). The translator tries such a title once more as a
  sentence, which mostly works. If it still fails, the story is marked
  failed and stays out of sight, instead of showing a false title.
- The stories translated before these checks go back to translation with
  their original title and text, newest first. That covers 269 footers and
  apologies, and about 4,650 stories of Chinese, Japanese or Korean feeds
  (mostly IT Home) that were read as another language before the script
  check, so that the Vietnamese, Korean or German model wrote nonsense, or
  none did and the title stayed in Chinese.
- The sync no longer erases the language of a translated story whose title
  keeps one CJK sign: that reset predates the translator, and it would have
  sent such stories round in a loop.

### CVE watch
- The title shown for a CVE is the story that stands for it. First, one
  naming it in its title. Then one that is not a list or a column
  ("weekly", "roundup", "digest"…). Then one written in English rather
  than translated, and the first of those. It used to be the latest story
  quoting it, such as "AWS Weekly Roundup" for the PHP flaws.

### Security
- FreshRSS (`/news`) asks for a password of nginx before its own login.
- The v0 TV feed and its sync trigger (`/api/tv/articles`, `/api/tv/sync`)
  are gone, with `TV_TOKEN`: the token was in the public history, so anyone
  could start a sync. nginx answers 410 for both.

### Catalog
- CyberScoop is no longer named "CyberScoop Asia".

### Tests
- A test suite (`tests/`, README, Development), run on a PostgreSQL
  database migrated like a new install.

## v1.3.4 — 2026-10-27

### Duplicates and purge, now on
- `dedup-worker.sh` knows what a duplicate is. It is a later copy, for one
  owner, of the same address: a feed followed under two names, the same
  paper in several arXiv lists, a feed that renews its ids. Or a later copy
  of the same title from the same source within 12 hours. The script used
  to compare titles over all time: it deleted the new issue of a weekly
  column, and it mixed up accounts' own sources with the shared feed. It
  keeps saved stories, and those a note points to. A date in the future
  now becomes the time the story arrived; the story used to be deleted
  (30 a day from AI Times, whose time zone is wrong). Of the stories
  arriving, about one in four was a duplicate.
- `/api/purge` keeps `PURGE_DAYS` days (90 by default, 70 at least)
  instead of 30, which emptied the CVE watch (60 days) and its week pages.
  It keeps saved stories, which used to go with them (ON DELETE CASCADE).
- Both timers are on in a new install (README, Installation).

### FreshRSS at /news
- php-fpm runs again: the AppArmor profile that Ubuntu's apparmor-profiles
  enforces since 22 October named no site (502, then 403).
  `deploy/apparmor/php-fpm.local` holds the rules, and
  `deploy/install-freshrss.sh` installs them.
- nginx serves FreshRSS's themes and scripts from FreshRSS, not from
  `frontend/`, and FreshRSS's base address is its public one,
  `https://<host>/news`. Its redirects no longer lose `/news`.

## v1.3.3 — 2026-10-27

### Breaking CVEs: only news
- A CVE is breaking news only when it is new in three ways. It was
  **published in the last 30 days** (date of the CVE record, or of the NVD),
  so an old CVE a story brings back, such as SMBGhost or ProxyLogon, is not.
  **A story is about it**: one naming at most three CVEs, so a list of a
  month's patches is not. And that story was **published in the last 12
  hours**, so a feed delivering days of stories at once is not. The rest is
  unchanged: first quoted in the last hour, scored 8 or more, on screen for
  an hour.
- The CVE cache keeps each CVE's publication date. Entries from before
  this release are fetched again (NVD and cve.org, at the NVD's public pace).
- A breaking CVE shows the title of the first story about it, not that of
  a list that happens to quote it.

### Posts
- At most **three posts an hour on each network**, the most severe first,
  and an exploited CVE (CISA KEV) first at the same score. The others stay
  on the TV and on `/cve`. On Mastodon one of them is public, the next two
  unlisted.
- Posts give the CVSS rating, **High** (7–8.9) or **Critical** (9–10). The
  TV still marks every breaking CVE CRITICAL. The CVE watch page and its
  RSS feed give the CVSS rating too.

Over the last 60 days, the new rule makes about 73 posts, 1.2 a day; the
old one made 119, with 19 in one hour.

## v1.3.2 — 2026-10-27

- `social-worker.py`: an error on one network no longer stops the run.
  A bad credential, a network down or a refused post is logged; the other
  network still posts, and what was posted is remembered. Before this, a
  Mastodon token holding a non-ASCII character made every run crash before
  Bluesky, and the breaking CVE of 27 October 05:32 UTC went out nowhere.

## v1.3.1 — 2026-10-26

- `social-worker.py` keeps to the rule of infosec.exchange for automated
  accounts. It makes at most one public Mastodon post an hour (24 a day);
  the other breaking CVEs of that hour go out unlisted, so they still reach
  followers. `MASTODON_VISIBILITY=unlisted` makes every post unlisted.
- When one network fails, the worker tries it again on the next run, for as
  long as the CVE is still breaking, without posting again on the other.
- `robots.txt` keeps search engines out of `/news/`, the FreshRSS
  interface.

## v1.3.0 — 2026-10-26

### Found by search engines
- **Pages a search engine can read**, rendered on the server, each with its
  canonical address, title, description and structured data (JSON-LD):
  - every topic, `/topics` and `/topic/<topic>`, and every day of a topic,
    `/topic/<topic>/<date>`, for the last 31 days;
  - a **daily digest**, `/digest` and `/digest/<date>`: the day's top topics
    with their main stories;
  - a page per **CVE**, `/cve/<id>`: its Impacted if, the kind of flaw, its
    severity, CISA KEV, and every story that quotes it; the **CVE watch**,
    `/cve`, and one page per week, `/cve/week/<year>-W<nn>`;
  - news **by country**, `/countries` and `/country/<cc>`, and the stories
    **translated into English**, `/translated`;
  - the **feed catalog** by field, `/feeds` and `/feeds/<field>`, each with its
    OPML;
  - **AX-NEWS for office TVs**, `/tv-screens`, with screenshots of the six
    layouts.
- The home page renders its first 30 stories on the server: a search engine
  reads them without running JavaScript.
- **RSS** for every topic, `/topic/<topic>/feed.xml`, and for the CVE watch,
  `/cve/feed.xml`.
- The sitemap is now an index (`/sitemap.xml`) of real pages: pages, days
  and CVEs. The 5,000 `/?article=` addresses it used to list all pointed to
  the home page, so they are gone. `/news-sitemap.xml` answers 410 Gone.
- `robots.txt` keeps private and redirect pages out (`/account`, `/tv/`,
  `/go/`…), and `/tv/<token>` screens send `X-Robots-Tag: noindex`.
  `llms.txt` is rewritten.
- The footer links the new pages.

### Workers (off by default)
- `seo-worker.py` and the `ax-news-seo` timer, hourly: sends the sitemaps'
  new or changed pages to **IndexNow**, which feeds Bing, Yandex, Seznam and
  Naver. The key comes from `INTERNAL_SYNC_TOKEN` and is served at
  `/<key>.txt`.
- `social-worker.py` and the `ax-news-social` timer, every 5 minutes: posts
  each **breaking CVE** once to Mastodon and/or Bluesky, with its score,
  Impacted if and a link to its page. It needs `MASTODON_BASE_URL` and
  `MASTODON_TOKEN`, or `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD`;
  without them it does nothing.

### Docs
- Screenshots in the README and every screen in
  [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md).

## v1.2.0 — 2026-10-26

### TV
- **Breaking CVEs**: a CVE the shared stories quote for the first time,
  scored 8 or more (CVSS from the NVD, or from its record on cve.org while
  the NVD has not scored it), becomes breaking news for one hour from when
  AX-NEWS first received it. In Spotlight it takes the side column under
  "Up next" — CRITICAL and BREAKING NEWS, its score, title, "Impacted if",
  QR code and the minutes left; several turn every 10 seconds. In the other
  layouts the CVE band shows them, marked BREAKING, for their hour. A CVE
  already quoted in the last 60 days is not new.

## v1.1.0 — 2026-10-26

### TV
- **Impacted if**, in the CVE watch band, left of the QR code: in broad lines,
  which products and versions a vulnerability touches ("PHP < 8.2.35 ·
  < 8.3.36 · < 8.4.27 +1", "Windows 10 1607 < 10.0.14393.9512 and 7 other
  products") and what it takes ("Use after free · over the network · no
  login", "Heap overflow · local access · any logged-in user"). From the
  vendor's own record on cve.org, or the NVD's version ranges when that
  record is unclear; the kind of flaw from its CWE, the conditions from its
  CVSS vector.
- Backgrounds made with Canva for the six themes (aurora, broadcast, paper,
  terminal, clinic, nebula).
- On an account's screen, the QR code of an alert from the account's own
  sources opens (it needed the screen's key).

### Topics
- 39 new illustrations made with Canva, for the fields the catalog added:
  medical breakthroughs, clinical journals, oncology, cardiology,
  neuroscience, infectious disease, public health, genomics, pharma,
  digital health, mental health, science, physics, chemistry, astronomy,
  mathematics, climate, nature, markets, economy, crypto, world, politics,
  law, defense, cars, aviation, film, music, books, design, games, sports,
  football, education, food, travel, open source, data. No topic falls back
  to the default picture any more.

## v1.0.0 — 2026-10-26

The first numbered release: everything since the repository's first
version, in one tested line of history.

### TV screens
- `/tv.html` and per-account screens at `/tv/<token>`, set up in the
  account's "TV screens" tab: topics, shared feeds and/or own sources, pace,
  alerts. Six layouts × six themes, 1080p to 4K, landscape or portrait.
- A QR code at the top left of each story (beside its text, never over its
  title) and the flag of the outlet's country at its top right.
- CVE watch: the 20 most important vulnerabilities of the last 60 days
  (CISA KEV, ransomware, NVD CVSS, coverage, recency), one at a time, each
  with a QR code to its record on cve.org.
- Unattended operation: refresh every two minutes, offline tolerance, reload
  on a new version and nightly, wake lock, hidden cursor, anti burn-in drift,
  night dimming, hourly layout rotation.

### Sources and translation
- A world feed catalog: 844 checked feeds in 11 fields and 28 languages; the
  208 shared tech feeds active, any other followed in one click, shared with
  everyone by an administrator.
- Personal sources: sites, RSS/Atom, YouTube, Reddit, Mastodon, GitHub,
  Hacker News, OPML import/export — private to their account.
- Translation into English of every source in another language (title and
  first paragraphs), not only Chinese, Japanese and Korean titles; looping
  translations rejected.

### Reading
- A new interface: six layouts, a reader panel, saved stories, light and
  dark themes, topic illustrations made with Canva, self-hosted fonts.
- A new brand: a thin AXIOM logo, the ΛX emblem, favicons, link preview.

### Security and operations
- A Content Security Policy with a per-response nonce on every page, an
  SSRF guard on every outside fetch, routes that start work restricted to
  administrators and the timers.
- The deployed systemd units, nginx configuration, schema and installers in
  the repository; a fresh deployment from GitHub works as documented.
- Audio summaries removed.

Upgrading from the repository's first version: apply
`migrations/003_personal_sources.sql` and `migrations/004_catalog_tv.sql`,
`pip install -r backend/requirements.txt`, restart `ax-news-backend`.
