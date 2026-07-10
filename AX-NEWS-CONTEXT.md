# AX-NEWS — Operational Context

## §1 Infrastructure

`Internet → Cloudflare → HAProxy (TLS) → Nginx → FastAPI (uvicorn, 2 workers) → PostgreSQL 16`

Server: ax-lab05. Services managed via systemd.

## §2 Key paths

| Path | Purpose |
|------|---------|
| `/opt/ax-news/backend/` | FastAPI application, Jinja2 templates, workers |
| `/opt/ax-news/frontend/` | Static assets (CSS, JS, images). HTML files are symlinks. |
| `/etc/nginx/sites-available/ax-news` | Nginx vhost config |
| `/var/www/freshrss/` | FreshRSS RSS aggregator (PHP 8.3) |

## §3 Request routing (Nginx)

- `*.html` requests and `/` → proxied to FastAPI (port 8000) for CSP nonce injection
- `/api/*` → proxied to FastAPI
- Static assets (`.css`, `.js`, `.png`, `.webp`, etc.) → served directly from `frontend/`
- `/404.html`, `/50x.html` → served statically from `frontend/` (real files, not symlinks)
- `/news*` → FreshRSS (PHP-FPM)

## §4 HTML source of truth

**`backend/templates/` is the authoritative source for all HTML pages.**

FastAPI/Jinja2 serves pages from `backend/templates/` and injects a per-request CSP
nonce (`{{ csp_nonce }}`) into every `<script>` and `<style>` tag.

`frontend/*.html` are **symlinks** pointing to `../backend/templates/*.html`:

```
frontend/index.html   → ../backend/templates/index.html
frontend/login.html   → ../backend/templates/login.html
frontend/admin.html   → ../backend/templates/admin.html
frontend/profile.html → ../backend/templates/profile.html
frontend/tv.html      → ../backend/templates/tv.html
frontend/about.html   → ../backend/templates/about.html
frontend/landing.html → ../backend/templates/landing.html
frontend/privacy.html → ../backend/templates/privacy.html
```

`frontend/404.html` and `frontend/50x.html` remain real files (nginx error pages,
served statically without FastAPI involvement).

**Rule: always edit `backend/templates/X.html`. Never edit `frontend/X.html` directly
(it is a symlink and changes would land in the same file anyway, but the canonical
location is `backend/templates/`).**

This structure was established 2026-07-10 after mobile-cat-bar, site-footer, and
cache-buster changes were accidentally applied only to the frontend/ copies.
