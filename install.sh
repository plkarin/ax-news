#!/usr/bin/env bash
# AX-NEWS on one machine, with Docker (docs/INSTALL.md):
#
#   curl -fsSL https://raw.githubusercontent.com/plkarin/ax-news/main/install.sh | bash
#   curl -fsSL …/install.sh | bash -s -- --url https://news.example.com --port 127.0.0.1:8080
#   ./install.sh --update
#
# It checks the prerequisites, gets the code (the latest release), writes
# .env with fresh secrets, starts the four containers, applies the
# migrations and creates the first administrator. Run again, it keeps .env,
# the data and the accounts; --update moves to the latest release.
set -euo pipefail

REPO=https://github.com/plkarin/ax-news.git
MIN_COMPOSE=2.20 MIN_RAM_MB=1800 MIN_DISK_GB=8

usage() {
  cat <<'EOF'
Usage: install.sh [options]
  --url URL          the public address (default: http://localhost:PORT)
  --port PORT        the port it answers on (default: 8080); ADDRESS:PORT listens
                     on one address only: 127.0.0.1:8080 behind a reverse proxy
  --admin NAME       the administrator to create, or whose password to reset
                     (default: admin, when there is none yet)
  --languages LIST   translation models: "all" (2.5 GB) or codes such as "ko zh"
  --dir DIR          where the code goes (default: this checkout, else ./ax-news)
  --ref REF          a release (or branch) to install (default: the latest release)
  --update           move to the latest release; .env and the data are kept
  -h, --help         this help
Environment: AXNEWS_ADMIN_PASSWORD, the administrator's password (else a random
one, shown once); other AXNEWS_* variables go into a new .env.
EOF
}

say()  { printf '\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
# Never on the script's own stdin: with curl | bash, that is the script.
compose() { docker compose "$@" </dev/null; }

# The highest vX.Y.Z tag: a release.
latest_tag() {
  local t
  t=$(git -C "$1" tag --list 'v*' | awk '/^v[0-9]+\.[0-9]+\.[0-9]+$/' | sort -V | tail -1)
  [ -n "$t" ] || die "no release (vX.Y.Z tag) in $1."
  echo "$t"
}

# .env from .env.docker.example: fresh secrets, the address and the port,
# and the caller's AXNEWS_* variables.
write_env() {
  local line key val
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) printf '%s\n' "$line"; continue ;; esac
    key=${line%%=*} val=${line#*=}
    case "$key" in
      POSTGRES_PASSWORD|FRESHRSS_PASSWORD|FRESHRSS_API_PASS|INTERNAL_SYNC_TOKEN) val=$(openssl rand -hex 24) ;;
      APP_URL) val=$1 ;;
      AXNEWS_PORT) val=$2 ;;
      AXNEWS_*) val=${!key-$val} ;;
    esac
    printf '%s=%s\n' "$key" "$val"
  done < .env.docker.example
  for key in $(compgen -e | grep -E '^AXNEWS_[A-Z0-9_]+$' || true); do
    case "$key" in AXNEWS_ADMIN_PASSWORD|AXNEWS_PORT) continue ;; esac
    grep -q "^$key=" .env.docker.example || printf '%s=%s\n' "$key" "${!key}"
  done
}

main() {
  local DIR="" URL="" PORT="" ADMIN="" LANGS="" UPDATE=0 REF=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --url|--port|--admin|--languages|--dir|--ref)
        [ $# -ge 2 ] || die "$1 needs a value."
        case "$1" in
          --url) URL=${2%/} ;; --port) PORT=$2 ;; --admin) ADMIN=$2 ;;
          --languages) LANGS=$2 ;; --dir) DIR=$2 ;; --ref) REF=$2 ;;
        esac
        shift 2 ;;
      --update) UPDATE=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) usage >&2; die "unknown option: $1" ;;
    esac
  done
  [ -z "$URL" ] || [[ "$URL" =~ ^https?://[^[:space:]]+$ ]] || die "--url: an address such as https://news.example.com"
  [ -z "$PORT" ] || { [[ "$PORT" =~ ^([0-9.]+:)?[0-9]{1,5}$ ]] && [ "${PORT##*:}" -ge 1 ] && [ "${PORT##*:}" -le 65535 ]; } \
    || die "--port: a port (8080), or ADDRESS:PORT (127.0.0.1:8080)"
  [ -z "$LANGS" ] || [[ "$LANGS" =~ ^(all|[a-z]{2,3}( [a-z]{2,3})*)$ ]] || die '--languages: "all", or codes such as "ko zh"'
  [ -z "$ADMIN" ] || [[ "$ADMIN" =~ ^[A-Za-z0-9._@-]{1,64}$ ]] || die "--admin: letters, digits and . _ @ - only"
  [ -z "${AXNEWS_ADMIN_PASSWORD:-}" ] || [ ${#AXNEWS_ADMIN_PASSWORD} -ge 8 ] || die "AXNEWS_ADMIN_PASSWORD: 8 characters at least."

  # ── Prerequisites ──────────────────────────────────────────────────────────
  say "Checking the prerequisites"
  [ "$(uname -s)" = Linux ] || die "AX-NEWS installs on Linux (on Windows: in WSL2)."
  case "$(uname -m)" in
    x86_64|amd64) ;;
    aarch64|arm64) warn "ARM64 should work, but only x86_64 is tested." ;;
    *) die "unsupported processor: $(uname -m) (x86_64 or ARM64)." ;;
  esac
  local c
  for c in git curl openssl docker; do
    command -v "$c" >/dev/null || die "$c is missing (docs/INSTALL.md, Prerequisites)."
  done
  docker info >/dev/null 2>&1 \
    || die "Docker does not answer: is it running, and may $(id -un) use it (the docker group)? docs/INSTALL.md, Prerequisites."
  local v
  v=$(docker compose version --short 2>/dev/null | sed 's/^v//') && [ -n "$v" ] \
    || die "the Docker Compose plugin is missing: docker compose, $MIN_COMPOSE or later (docker-compose v1 will not do)."
  [ "$(printf '%s\n%s\n' "$MIN_COMPOSE" "$v" | sort -V | head -1)" = "$MIN_COMPOSE" ] \
    || die "Docker Compose $v is too old: $MIN_COMPOSE or later."
  local ram_mb free_kb need root
  ram_mb=$(( $(awk '/^MemTotal/ {print $2}' /proc/meminfo) / 1024 ))
  [ "$ram_mb" -ge "$MIN_RAM_MB" ] || die "${ram_mb} MB of memory: AX-NEWS needs 2 GB."
  [ "$ram_mb" -ge 3700 ] || warn "${ram_mb} MB of memory: it runs, but 4 GB is advised, and needed to translate."
  root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null) || root=/var/lib/docker
  free_kb=$(df -Pk "$root" 2>/dev/null | awk 'NR==2 {print $4}') || free_kb=""
  [ -n "$free_kb" ] || free_kb=$(df -Pk / | awk 'NR==2 {print $4}')
  need=0                                        # GB: the images once, the models
  docker image inspect ax-news:local >/dev/null 2>&1 || need=$MIN_DISK_GB
  [ -z "$LANGS" ] || need=$(( need + 3 ))
  [ $(( free_kb / 1048576 )) -ge "$need" ] \
    || die "$(( free_kb / 1048576 )) GB free for Docker ($root): ${need} GB needed."

  # ── The code ───────────────────────────────────────────────────────────────
  if [ -z "$DIR" ]; then
    local here
    here=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd) || here=""
    if [ -n "$here" ] && [ -f "$here/deploy/docker/scheduler.py" ] && [ -e "$here/.git" ]; then DIR=$here
    else DIR=$PWD/ax-news; fi
  fi
  local release
  if [ -e "$DIR/.git" ]; then
    [ -f "$DIR/deploy/docker/scheduler.py" ] || die "$DIR is not a checkout of AX-NEWS: choose another --dir."
    if [ "$UPDATE" = 1 ] || [ -n "$REF" ]; then
      [ -z "$(git -C "$DIR" status --porcelain --untracked-files=no)" ] \
        || die "$DIR has local changes (git -C $DIR status): commit or stash them first."
      say "Updating the code"
      git -C "$DIR" fetch --quiet --tags origin
      if [ -n "$REF" ]; then git -C "$DIR" checkout --quiet "$REF"
      elif git -C "$DIR" symbolic-ref -q HEAD >/dev/null; then git -C "$DIR" pull --quiet --ff-only
      else release=$(latest_tag "$DIR"); git -C "$DIR" checkout --quiet "$release"; fi
    fi
  else
    [ ! -e "$DIR" ] || [ -z "$(ls -A "$DIR")" ] || die "$DIR exists and is not a checkout of AX-NEWS: choose another --dir."
    say "Getting AX-NEWS into $DIR"
    git clone --quiet "$REPO" "$DIR"
    release=${REF:-$(latest_tag "$DIR")}
    git -C "$DIR" checkout --quiet "$release"
  fi
  cd "$DIR" || die "cannot enter $DIR."
  DIR=$PWD
  [ -f install.sh ] || warn "this release has no install.sh: update it by hand (docs/INSTALL.md, Install with Docker by hand)."
  local version
  version=$(git describe --tags --always 2>/dev/null || echo unknown)
  say "AX-NEWS $version in $DIR"

  # ── .env ───────────────────────────────────────────────────────────────────
  local host=127.0.0.1 port
  if [ ! -f .env ]; then
    for v in ax-news_db ax-news_freshrss; do
      if docker volume inspect "$v" >/dev/null 2>&1; then
        die "the data of an earlier install is here (Docker volume $v), but not its .env: put that .env back in $DIR, or delete the data first (docs/INSTALL.md, Troubleshooting)."
      fi
    done
    PORT=${PORT:-8080}
    port=${PORT##*:}
    case "$PORT" in *:*) host=${PORT%:*} ;; esac
    URL=${URL:-http://localhost:$port}
    if timeout 5 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null; then
      die "port $port is taken: choose another with --port."
    fi
    say "Writing .env: fresh secrets, APP_URL=$URL"
    (umask 077 && write_env "$URL" "$PORT" > .env)
  else
    [ -z "$URL$PORT" ] || warn ".env is kept: change APP_URL or AXNEWS_PORT in it, then run ./install.sh again."
    PORT=$(sed -n 's/^AXNEWS_PORT=//p' .env | tail -1)
    PORT=${PORT:-8080}
    port=${PORT##*:}
    case "$PORT" in *:*) host=${PORT%:*} ;; esac
    URL=$(sed -n 's/^APP_URL=//p' .env | tail -1)
  fi

  # ── The containers, the database ───────────────────────────────────────────
  say "Building and starting the containers (the first time: 5 to 15 minutes)"
  compose up -d --build --wait --wait-timeout 900 \
    || die "the containers did not start: see docker compose -f $DIR/docker-compose.yml logs --tail 50"
  say "Applying the migrations"
  local m
  for m in migrations/0*.sql; do
    case "$m" in */001_*|*/002_*) continue ;; esac   # 001: the first start (initdb.sh); 002: removed features
    compose exec -T -e PGOPTIONS='-c client_min_messages=warning' db \
      psql -q -v ON_ERROR_STOP=1 -U ax_news -d ax_news -f "/$m" >/dev/null
  done

  # ── The administrator ──────────────────────────────────────────────────────
  local admins password="" shown=0
  admins=$(compose exec -T db psql -tAq -U ax_news -d ax_news -c "SELECT count(*) FROM users WHERE is_admin")
  if [ -n "$ADMIN" ] || [ "$admins" = 0 ]; then
    ADMIN=${ADMIN:-admin}
    password=${AXNEWS_ADMIN_PASSWORD:-}
    if [ -z "$password" ]; then
      password=$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | cut -c1-20)
      shown=1
    fi
    say "The administrator: $ADMIN"
    AXNEWS_ADMIN_PASSWORD=$password compose exec -T -e AXNEWS_ADMIN_PASSWORD backend python tools/create_admin.py "$ADMIN"
  fi

  # ── Translation models ─────────────────────────────────────────────────────
  if [ -n "$LANGS" ]; then
    say "Installing the translation models: $LANGS"
    if [ "$LANGS" = all ]; then compose exec -T worker deploy/install-argos-models.sh
    else compose exec -T worker deploy/install-argos-models.sh $LANGS; fi   # one code per argument
  fi

  # ── Done ───────────────────────────────────────────────────────────────────
  curl -fsS -o /dev/null "http://$host:$port/api/health" || die "the site does not answer on $host:$port."
  local here_url=$host
  case "$host" in 127.0.0.1|0.0.0.0) here_url=localhost ;; esac
  echo
  say "AX-NEWS $version is running: $URL"
  [ "$URL" = "http://$here_url:$port" ] || echo "    on this machine: http://$here_url:$port"
  if [ "$shown" = 1 ]; then
    echo "    administrator: $ADMIN    password: $password    (shown this once)"
  elif [ -n "$password" ]; then
    echo "    administrator: $ADMIN    password: the one in AXNEWS_ADMIN_PASSWORD"
  fi
  cat <<EOF
    stories:     FreshRSS subscribes to the ~200 shared feeds, then fetches them every 15 minutes;
                 the first stories come in within half an hour: docker compose logs -f worker
    translation: stories in other languages wait for their models: ./install.sh --languages all
    https:       a reverse proxy in front, APP_URL set to the public address: docs/INSTALL.md
    all commands from $DIR; your secrets are in .env there.
EOF
}

main "$@"
