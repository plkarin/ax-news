# AX-NEWS — Global Tech Intelligence Feed

Self-hosted news intelligence portal aggregating and translating tech news from 200+ sources worldwide. Built with FastAPI, PostgreSQL, and a vanilla JS frontend.

Live at [ax-news.com](https://ax-news.com)

## Features

- Real-time news aggregation via **self-hosted FreshRSS** (co-located, 208 feeds)
- Automatic translation (Argos Translate, fully offline, no API costs)
- AI-powered sentiment scoring and entity extraction (static Bayesian model, zero LLM cost)
- Admin-approved user registration + Google OAuth SSO
- Infinite-scroll feed with category filtering and search
- TV dashboard mode for office displays (INFRA-TV)
- AI chat analysis per article (admin only, via Claude Code subprocess — no API key required)
- SEO-optimized: sitemap.xml, news-sitemap.xml, robots.txt, structured data, llms.txt
- A+ SSL Labs rating, hardened CSP, rate limiting

## Stack

- **Backend:** FastAPI + asyncpg + PostgreSQL 16
- **Frontend:** Vanilla JS, no framework, no build step
- **Translation:** Argos Translate (offline, 14 languages)
- **Reverse proxy:** Nginx + HAProxy (TLS termination)
- **RSS aggregator:** FreshRSS (local, PHP 8.3 built-in server on 127.0.0.1:8082)
- **Process management:** systemd services + timers

## Architecture

```
Internet → Cloudflare → HAProxy (TLS) → Nginx → FastAPI (uvicorn, 2 workers)
                                                    ↓
                                              PostgreSQL 16
                                                    ↓
                                    Standalone Argos translation worker
                                         (separate process, MemoryMax=1G)
```

## Setup

### Prerequisites

- Ubuntu 24.04 LTS
- PostgreSQL 16
- Python 3.12
- PHP 8.3 + extensions (installed by `deploy/install-freshrss.sh`)
- Nginx
- Claude Code CLI authenticated (for the AI chat feature — no API key needed for Pro subscribers)

### Installation

Paths are fixed: the units and workers expect the checkout at `/opt/ax-news`,
run as the user `cbrain`.

```bash
sudo git clone https://github.com/plkarin/ax-news.git /opt/ax-news
sudo chown -R cbrain:cbrain /opt/ax-news && cd /opt/ax-news
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt

cp backend/.env.example backend/.env
# Edit backend/.env with your actual credentials (see below)

# Database: an empty PostgreSQL database owned by the application user
psql "$DATABASE_URL" -f migrations/001_schema.sql

# Translation models (about 2.5 GB, downloaded once)
deploy/install-argos-models.sh

sudo mkdir -p /var/log/ax-news && sudo chown cbrain:cbrain /var/log/ax-news
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo cp deploy/nginx/ax-news /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/ax-news /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo systemctl daemon-reload
sudo systemctl enable --now ax-news-backend
sudo systemctl enable --now ax-news-sync.timer ax-news-translate.timer \
  ax-news-dedup.timer ax-news-images.timer

# Install and start local FreshRSS (208 feeds, auto-refresh every 15 min)
sudo FRESHRSS_USER=Pierre FRESHRSS_PASS=yourpassword deploy/install-freshrss.sh
```

### Purge

`ax-news-purge.timer` deletes every article older than 30 days, each Monday
at 03:00. It is not enabled by the installation above: turn it on only once
you want the archive to keep a month, `sudo systemctl enable --now
ax-news-purge.timer`.

## Environment variables

See `backend/.env.example` for required configuration:

- `DATABASE_URL` — PostgreSQL connection, also used by `dedup-worker.sh`
- `HOME` — where the Argos models are installed
- `FRESHRSS_*` — FreshRSS API credentials
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — for Google SSO
- `SMTP_*` — for email verification
- `APP_URL` — public URL of the deployment
- `INTERNAL_SYNC_TOKEN` — sent by the timers from localhost; the routes that
  start work (sync, enrichment, translation, images, purge) accept it, or an
  administrator's session
- `TV_TOKEN` — read-only token of the TV dashboards' feed

## File organisation

```
frontend/          Static assets only: CSS, JS, images, logo, 404.html, 50x.html
                   *.html files are symlinks → ../backend/templates/*.html
backend/templates/ Source of truth for all HTML pages (Jinja2, CSP nonce injection)
```

Nginx routes every `.html` request and `/` to FastAPI (port 8000); it never serves
HTML directly from `frontend/`. The symlinks exist purely so that path references
inside the repo remain consistent — edits must be made in `backend/templates/`.

## License

MIT — see LICENSE file.
