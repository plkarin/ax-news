#!/usr/bin/env bash
# Install and configure local FreshRSS instance for AX-NEWS.
# Run as root on Ubuntu 24.04 after backend .env is configured.
set -euo pipefail

FRESHRSS_DIR=/var/www/freshrss
FRESHRSS_USER="${FRESHRSS_USER:-Pierre}"
FRESHRSS_PASS="${FRESHRSS_PASS:-changeme}"
FRESHRSS_PORT="${FRESHRSS_PORT:-8082}"
OPML_FILE="$(dirname "$0")/../ax-news-worldwide.opml"

echo "=== Installing PHP 8.3 ==="
apt-get install -y php8.3 php8.3-fpm php8.3-curl php8.3-mbstring php8.3-xml \
  php8.3-gd php8.3-zip php8.3-sqlite3 php8.3-intl php8.3-bcmath

echo "=== Cloning FreshRSS ==="
if [ -d "$FRESHRSS_DIR" ]; then
  echo "FreshRSS already present at $FRESHRSS_DIR — skipping clone"
else
  git clone --depth 1 --branch latest https://github.com/FreshRSS/FreshRSS.git "$FRESHRSS_DIR"
fi
chown -R www-data:www-data "$FRESHRSS_DIR"
chmod -R 755 "$FRESHRSS_DIR"
chmod -R 775 "$FRESHRSS_DIR/data"

echo "=== Configuring FreshRSS ==="
sudo -u www-data php8.3 "$FRESHRSS_DIR/cli/do-install.php" \
  --default-user "$FRESHRSS_USER" \
  --auth-type form \
  --environment production \
  --base-url "http://127.0.0.1:${FRESHRSS_PORT}" \
  --language en \
  --title "AX-NEWS FreshRSS" \
  --db-type sqlite

sudo -u www-data php8.3 "$FRESHRSS_DIR/cli/reconfigure.php" --api-enabled

echo "=== Creating user $FRESHRSS_USER ==="
sudo -u www-data php8.3 "$FRESHRSS_DIR/cli/create-user.php" \
  --user "$FRESHRSS_USER" \
  --password "$FRESHRSS_PASS" \
  --api-password "$FRESHRSS_PASS" \
  --no-default-feeds

echo "=== Importing OPML ==="
if [ -f "$OPML_FILE" ]; then
  sudo -u www-data php8.3 "$FRESHRSS_DIR/cli/import-for-user.php" \
    --user "$FRESHRSS_USER" \
    --filename "$OPML_FILE"
  echo "OPML imported"
else
  echo "OPML not found at $OPML_FILE — skipping"
fi

echo "=== Installing systemd services ==="
DEPLOY_DIR="$(dirname "$0")/systemd"
cp "$DEPLOY_DIR/freshrss.service"         /etc/systemd/system/
cp "$DEPLOY_DIR/freshrss-refresh.service" /etc/systemd/system/
cp "$DEPLOY_DIR/freshrss-refresh.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now freshrss.service
systemctl enable --now freshrss-refresh.timer

echo "=== Installing nginx vhost ==="
cp "$(dirname "$0")/nginx/freshrss" /etc/nginx/sites-available/freshrss
ln -sf /etc/nginx/sites-available/freshrss /etc/nginx/sites-enabled/freshrss
nginx -t && systemctl reload nginx

echo "=== Updating backend .env ==="
ENV_FILE="$(dirname "$0")/../backend/.env"
if [ -f "$ENV_FILE" ]; then
  sed -i "s|FRESHRSS_BASE_URL=.*|FRESHRSS_BASE_URL=http://127.0.0.1:${FRESHRSS_PORT}|" "$ENV_FILE"
  echo "Updated FRESHRSS_BASE_URL in $ENV_FILE"
fi

echo ""
echo "=== FreshRSS install complete ==="
echo "  API: http://127.0.0.1:${FRESHRSS_PORT}/api/greader.php"
echo "  User: $FRESHRSS_USER"
echo "  Timer: systemctl status freshrss-refresh.timer"
echo ""
echo "Run first feed fetch:"
echo "  sudo -u www-data php8.3 $FRESHRSS_DIR/cli/actualize-user.php --user $FRESHRSS_USER"
