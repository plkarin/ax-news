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

```bash
git clone https://github.com/plkarin/ax-news.git
cd ax-news
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt --break-system-packages

cp backend/.env.example backend/.env
# Edit backend/.env with your actual credentials

sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/
sudo cp deploy/nginx/ax-news /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/ax-news /etc/nginx/sites-enabled/

sudo systemctl daemon-reload
sudo systemctl enable --now ax-news-backend
sudo systemctl enable --now ax-news-sync.timer
sudo systemctl enable --now ax-news-translate.timer
sudo systemctl enable --now ax-news-dedup.timer

# Install and start local FreshRSS (208 feeds, auto-refresh every 15 min)
sudo FRESHRSS_USER=Pierre FRESHRSS_PASS=yourpassword deploy/install-freshrss.sh
```

## Environment variables

See `backend/.env.example` for required configuration:

- `DB_URL` / `DATABASE_URL` — PostgreSQL connection
- `FRESHRSS_*` — FreshRSS API credentials
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — for Google SSO
- `SMTP_*` — for email verification
- `APP_URL` — public URL of the deployment
- `DB_PASSWORD` — used by shell workers (`translate-worker.sh`, `dedup-worker.sh`)

## License

MIT — see LICENSE file.
