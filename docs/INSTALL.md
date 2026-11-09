# Installing AX-NEWS

AX-NEWS runs on one machine. The quickest way is the script, with Docker:
it checks the prerequisites, gets the latest release, writes the
configuration with fresh secrets, starts the containers and creates your
administrator account. Without Docker, AX-NEWS installs like the production
of ax-news.com: systemd, nginx, PostgreSQL ([Install without Docker](#install-without-docker)).

- [Prerequisites](#prerequisites)
- [Install with the script](#install-with-the-script)
- [After the install](#after-the-install)
- [HTTPS and a public address](#https-and-a-public-address)
- [Day to day with Docker](#day-to-day-with-docker)
- [Install with Docker by hand](#install-with-docker-by-hand)
- [Install without Docker](#install-without-docker)
- [Configuration](#configuration)
- [Operations without Docker](#operations-without-docker)
- [Troubleshooting](#troubleshooting)

## Prerequisites

| | Needed | Notes |
|---|---|---|
| System | Linux on x86_64 | Ubuntu 24.04 or later, Debian 12 or later, or any distribution Docker runs on; Windows in WSL2. ARM64 should work but is not tested. |
| Docker | Docker Engine and the **Compose plugin 2.20 or later** | `docker compose version` answers, and the account that installs may use Docker (the `docker` group). |
| Tools | `git`, `curl`, `openssl` | |
| Memory | 2 GB | 4 GB advised, and needed to translate: the translation alone takes up to 1 GB. A new install uses some 350 MB. |
| Disk | 8 GB free for Docker | The images take 2.2 GB; the database reaches about 1 GB with 90 days of stories, where the purge holds it; all the translation models, 3 GB more. |
| Network | Outbound HTTPS | The feeds, their pictures, NVD and CISA for the CVE watch; to build the image, Docker Hub, PyPI and download.pytorch.org. |
| Port | One free port | 8080 unless you choose another. |

Docker on **Ubuntu 24.04 or later**:

```bash
sudo apt install -y docker.io docker-compose-v2 git curl openssl
sudo usermod -aG docker "$USER"      # then log out and in again
```

Ubuntu's `docker-compose` package is Compose v1 (`docker-compose`, with a
hyphen): AX-NEWS needs the v2 plugin, `docker compose`. On other
distributions, install Docker's own packages:
[docs.docker.com/engine/install](https://docs.docker.com/engine/install/).

## Install with the script

```bash
curl -fsSL https://raw.githubusercontent.com/plkarin/ax-news/main/install.sh | bash
```

Or, to read the script before running it:

```bash
git clone https://github.com/plkarin/ax-news.git && cd ax-news
less install.sh
./install.sh
```

The script:

1. checks the prerequisites above, and says what is missing;
2. gets the latest release into `./ax-news`, or uses the checkout it runs
   from;
3. writes `.env` from `.env.docker.example`, readable by its owner only:
   random secrets for the database, FreshRSS and the internal token, the
   address and the port;
4. builds the image and starts four containers — PostgreSQL, FreshRSS, the
   backend, which serves the site, and the worker, which does the
   background work — and waits until they are healthy. The first build
   downloads the Python packages and takes a few minutes;
5. applies the database migrations;
6. creates the administrator `admin` with a random password, shown once at
   the end;
7. with `--languages`, installs translation models.

Run again, it keeps `.env`, the data and the accounts, creates an
administrator only when there is none, and leaves the site running: only
`--update` and `--ref` build a new image and restart the backend and the
worker.

| Option | | Default |
|---|---|---|
| `--url URL` | The public address: links, QR codes, the `Secure` flag of the session cookie. | `http://localhost:PORT` |
| `--port PORT` | The port on this machine. `ADDRESS:PORT` listens on one address only: `127.0.0.1:8080` behind a reverse proxy. | `8080`, on every address |
| `--admin NAME` | An administrator to create, or whose password to reset. | `admin`, when there is none |
| `--languages LIST` | Translation models: `all` (13 languages, about 2.5 GB) or codes, such as `"ko zh"`. | none |
| `--dir DIR` | Where the code goes. | the checkout it runs from, else `./ax-news` |
| `--ref REF` | A release (`v1.4.1`) or a branch. | the latest release |
| `--update` | Moves to the latest release (on a branch: its last commit), rebuilds, applies the new migrations. | |

| Variable | |
|---|---|
| `AXNEWS_ADMIN_PASSWORD` | The administrator's password, instead of a random one; 8 characters at least. |
| `AXNEWS_*` | Written into a new `.env`: `AXNEWS_IMPORT_FEEDS=0` leaves FreshRSS without the shared feeds, `AXNEWS_INDEXNOW=1` tells search engines about new pages. |

With `curl … | bash`, the options follow `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/plkarin/ax-news/main/install.sh \
  | bash -s -- --url https://news.example.com --port 127.0.0.1:8080 --languages "ko zh"
```

## After the install

- **Sign in** at the address the script shows (`/login.html`), with the
  administrator it created. The admin console is at `/admin.html`.
- **Stories.** On its first start, the worker subscribes FreshRSS to the
  shared feeds of `catalog/sources/active.txt`, about 200 of them. FreshRSS
  fetches them every 15 minutes, and the worker brings them into the
  database every 10: the first stories appear within half an hour. Follow
  it with `docker compose logs -f worker`: `freshrss: subscribed to … shared
  feeds`, then `sync: HTTP 200 …`.
- **Accounts.** Sign-up is closed. An administrator opens accounts in the
  admin console, and `./install.sh --admin NAME` makes another
  administrator. Once Google sign-in is set up (`GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`), a Google account waits for an administrator's
  approval.
- **Translation.** A story in a language other than English shows once it
  is translated into English, offline, by Argos Translate. Two of the
  shared feeds are in Korean and Chinese: `./install.sh --languages "ko zh"`.
  `--languages all` installs the 13 most common languages of the catalog
  (Arabic, Chinese, Dutch, French, German, Italian, Japanese, Korean,
  Portuguese, Russian, Spanish, Turkish, Vietnamese), about 2.5 GB,
  downloaded once into a volume. Others:
  `docker compose exec worker deploy/install-argos-models.sh pl sv da nb fi cs el ro hu uk he fa hi id th`.
- **The rest of `.env`**: mail (`SMTP_*`), Google sign-in, the Mastodon and
  Bluesky accounts of the CVE watch, the time zone
  ([Configuration](#configuration)). After a change, `docker compose up -d`
  starts the containers again with it.

## HTTPS and a public address

AX-NEWS answers in plain HTTP on its port. For a public address, put a
reverse proxy in front of it, on the same machine:

1. Install with the public address, and the port kept to this machine:
   ```bash
   ./install.sh --url https://news.example.com --port 127.0.0.1:8080
   ```
   On an existing install, set `APP_URL=https://news.example.com` and
   `AXNEWS_PORT=127.0.0.1:8080` in `.env`, then `docker compose up -d`.
2. Send the proxy to `127.0.0.1:8080`. [Caddy](https://caddyserver.com)
   gets the certificate by itself; in `/etc/caddy/Caddyfile`:
   ```
   news.example.com {
       reverse_proxy 127.0.0.1:8080
   }
   ```
   nginx, with a certificate from certbot:
   ```nginx
   server {
       listen 443 ssl;
       server_name news.example.com;
       ssl_certificate     /etc/letsencrypt/live/news.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/news.example.com/privkey.pem;
       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

Docker publishes a port past the firewall (ufw's rules do not apply to it):
without `127.0.0.1:`, the port is open to the network. With an `https://`
address, the session cookie only travels over HTTPS: sign in through that
address.

## Day to day with Docker

From the install directory:

| | |
|---|---|
| State | `docker compose ps` |
| Logs | `docker compose logs -f worker` (the background work), `docker compose logs -f backend` |
| Stop, start | `docker compose stop`, `docker compose start`. The containers start with the machine, unless stopped. |
| Update | `./install.sh --update`: the latest release; `.env` and the data are kept. |
| Go back | `./install.sh --ref v1.4.1`. Migrations only add, so an earlier release still reads the database. (`install.sh` exists from v1.4.1 on.) |
| Back up | `docker compose exec -T db pg_dump -Fc -U ax_news ax_news > ax-news-$(date +%F).dump`, and keep `.env` with it. |
| Restore | `docker compose stop backend worker`, then `docker compose exec -T db pg_restore --clean --if-exists -U ax_news -d ax_news < ax-news-….dump`, then `docker compose start backend worker`. |
| Uninstall | `docker compose down` removes the containers and keeps the data; `docker compose down -v` deletes the data too — the database, FreshRSS, the models — and `docker image rm ax-news:local` the image. |

The stories and the accounts are in the database. FreshRSS keeps its
subscriptions in its own volume; a new install subscribes it to the shared
feeds again.

## Install with Docker by hand

What the script does, step by step:

```bash
git clone https://github.com/plkarin/ax-news.git && cd ax-news
git checkout v1.4.2
cp .env.docker.example .env && chmod 600 .env
# in .env: the four secrets (openssl rand -hex 24 for each), APP_URL, AXNEWS_PORT
docker compose up -d --build --wait
docker compose exec backend python tools/create_admin.py <name>       # asks for a password
docker compose exec worker deploy/install-argos-models.sh ko zh       # optional: translation models
```

The database applies the migrations on its first start only
(`deploy/docker/initdb.sh`). When an update brings a new one, apply it:
`docker compose exec -T db psql -U ax_news -d ax_news -f /migrations/<file>.sql`
(`migrations/` is mounted in the container). FreshRSS's own interface is not
published; add a port to its service in `docker-compose.yml` to reach it.

## Install without Docker

Ubuntu 24.04 with PostgreSQL 16, Python 3.12, nginx and PHP 8.3 (for
FreshRSS). The units expect the checkout at `/opt/ax-news`, run as the
user `cbrain`: for another account, change `User=` in
`deploy/systemd/*.service`.

```bash
sudo git clone https://github.com/plkarin/ax-news.git /opt/ax-news
sudo chown -R cbrain:cbrain /opt/ax-news && cd /opt/ax-news
git checkout v1.4.2
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt

cp backend/.env.example backend/.env          # then fill it in: see Configuration

# Database: an empty PostgreSQL database owned by the application user
psql "$DATABASE_URL" -f migrations/001_schema.sql
psql "$DATABASE_URL" -f migrations/003_personal_sources.sql
psql "$DATABASE_URL" -f migrations/004_catalog_tv.sql
psql "$DATABASE_URL" -f migrations/005_articles_lookups.sql
backend/venv/bin/python tools/create_admin.py <name>   # the first administrator account

# Translation models into English: about 2.5 GB for the 13 default languages, downloaded once
deploy/install-argos-models.sh

sudo mkdir -p /var/log/ax-news && sudo chown cbrain:cbrain /var/log/ax-news
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo cp deploy/nginx/ax-news /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/ax-news /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo systemctl daemon-reload
sudo systemctl enable --now ax-news-backend
sudo systemctl enable --now ax-news-sync.timer ax-news-translate.timer \
  ax-news-images.timer ax-news-sources.timer ax-news-dedup.timer ax-news-purge.timer

# FreshRSS and its 208 feeds; its interface at https://<host>/news
sudo FRESHRSS_USER=<user> FRESHRSS_PASS=<password> deploy/install-freshrss.sh
```

Ubuntu's `apparmor-profiles` confines php-fpm without naming any site, which
leaves `/news` in 502 or 403: `deploy/install-freshrss.sh` installs
`deploy/apparmor/php-fpm.local` as `/etc/apparmor.d/local/php-fpm`. It lets
php-fpm tell systemd it is ready and read FreshRSS, and write only its data.

(`migrations/002_audio_columns.sql` belongs to the audio summaries, removed
before v1.0.0: a new database does not need it.)

## Configuration

With Docker, `.env` (template: `.env.docker.example`, which `install.sh`
fills in). Without, `backend/.env` (template: `backend/.env.example`).

| Variable | Use |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (Docker sets it) |
| `POSTGRES_PASSWORD` | Docker: the database's password. It is set at the database's first start; changing it later in `.env` does not change the database's. |
| `FRESHRSS_PASSWORD` | Docker: the password of FreshRSS's user, for its interface |
| `AXNEWS_PORT` | Docker: the published port, or `ADDRESS:PORT` (`127.0.0.1:8080`) |
| `TZ` | Docker: the containers' time zone |
| `AXNEWS_INDEXNOW` | Docker: `1` runs `seo-worker.py` hourly (IndexNow); only for a public `APP_URL` |
| `AXNEWS_IMPORT_FEEDS` | Docker: `0`, the worker does not subscribe FreshRSS to the shared feeds |
| `HOME` | Without Docker: where the Argos models are installed (`/opt/ax-news/.argos-home`) |
| `FRESHRSS_BASE_URL`, `FRESHRSS_USER`, `FRESHRSS_API_PASS` | The FreshRSS API |
| `APP_URL` | Public address (links, QR codes, cookies' `Secure` flag) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in |
| `SMTP_*` | Mail (address verification) |
| `INTERNAL_SYNC_TOKEN` | Sent by the timers from localhost to start work (sync, images, purge); `openssl rand -hex 32` |
| `MAX_SOURCES_PER_USER` | Own sources per account (default 150) |
| `PURGE_DAYS` | Days of stories kept by `ax-news-purge` (default 90, at least 70: the CVE watch reads 60 days, its week pages nine weeks); saved stories are kept |
| `MASTODON_BASE_URL`, `MASTODON_TOKEN` | Account `social-worker.py` posts breaking CVEs to (token scope `write:statuses`); empty: no post |
| `MASTODON_VISIBILITY` | `public` (default): one public post an hour at most, the next two of the hour `unlisted`; `unlisted`: all of them |
| `SOCIAL_DIGEST_AT`, `SOCIAL_TZ` | When the daily post goes out (default `08:30`, `Europe/Paris`; window until 12:00); `SOCIAL_DIGEST_AT=off`: no daily post |
| `SOCIAL_KEV` | `0`: no post for CISA's KEV additions (default `1`) |
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | Same on Bluesky, with an app password; empty: no post |
| `AXNEWS_LOCAL_URL` | Where the workers reach the backend (default `http://127.0.0.1:8000`; Docker sets it) |

## Operations without Docker

| Timer | Runs | Enabled by default |
|---|---|---|
| `ax-news-sync` | FreshRSS → database, every 10 min | yes |
| `ax-news-translate` | Translation, 8 min of work every 10 min | yes |
| `ax-news-sources` | Accounts' and shared catalog sources, every 5 min | yes |
| `ax-news-images` | Pictures for stories without one, hourly | yes |
| `freshrss-refresh` | FreshRSS fetches its feeds, every 15 min | yes |
| `ax-news-seo` | IndexNow: the sitemaps' new pages to Bing and others, hourly | no — enable once the site is verified |
| `ax-news-social` | The CVE watch to Mastodon/Bluesky (breaking CVEs, KEV additions, a daily post), every 5 min | no — enable once an account is set |
| `ax-news-dedup` | Removes duplicates, hourly: a later copy of the same address, or of the same title from the same source within 12 hours; dates in the future become the arrival time | yes |
| `ax-news-purge` | Deletes stories older than `PURGE_DAYS` (90), except saved ones, Mondays 03:00 | yes |

With Docker, the worker does the same work (`deploy/docker/scheduler.py`):
the social posts start as soon as an account is set in `.env`, IndexNow
with `AXNEWS_INDEXNOW=1`.

**Update** to a release: `git fetch --tags origin && git checkout vX.Y.Z`,
then `backend/venv/bin/pip install -r backend/requirements.txt`, the new
`migrations/` files if any (they are additive), and
`sudo systemctl restart ax-news-backend`. Back up first:
`pg_dump -Fc "$DATABASE_URL" -f ax-news-$(date +%F).dump`.
**Roll back**: check out the previous tag and restart; migrations never
remove what an older release reads.

**FreshRSS** (`/news`) is behind a password of nginx, before its own login:
user `freshrss`, password in `/etc/nginx/ax-news-freshrss.htpasswd` (hashed).
Set one with `printf 'freshrss:%s\n' "$(openssl passwd -6)" | sudo tee
/etc/nginx/ax-news-freshrss.htpasswd`, then `sudo systemctl reload nginx`.

**Search engines**: declare `https://<your address>/sitemap.xml` in Google
Search Console and Bing Webmaster Tools. IndexNow needs no account: its key
is derived from `INTERNAL_SYNC_TOKEN` and served at `/<key>.txt`.

**More languages**: `deploy/install-argos-models.sh pl sv da nb fi cs el ro hu uk he fa hi id th`
installs the models the catalog's other languages need; their feeds then
become available.

## Troubleshooting

| What you see | What to do |
|---|---|
| `Docker does not answer` | Start Docker (`sudo systemctl enable --now docker`), or join the `docker` group (`sudo usermod -aG docker "$USER"`) and log in again. |
| `the Docker Compose plugin is missing` | Ubuntu: `sudo apt install docker-compose-v2`; elsewhere, Docker's packages. `docker-compose` v1 will not do. |
| `port 8080 is taken` | `./install.sh --port 8081` |
| `the containers did not start` | `docker compose ps`, then `docker compose logs backend` (or `db`, `freshrss`). |
| No stories after an hour | `docker compose logs worker \| grep -E 'freshrss\|sync'`: the FreshRSS login, the subscriptions, the syncs. |
| A forgotten password | `./install.sh --admin <name>`: a new random password. |
| Signing in does not hold | `APP_URL` starts with `https://` and the page is open over `http://`: use the `https://` address. |
| `the data of an earlier install is here, but not its .env` | Put that `.env` back. To start afresh instead, remove the old containers and data: `docker rm -f $(docker ps -aq --filter label=com.docker.compose.project=ax-news)`, then `docker volume rm ax-news_db ax-news_freshrss`. |
