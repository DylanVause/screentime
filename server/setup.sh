#!/usr/bin/env bash
# One-time setup script for Ubuntu.
# Run as root (or with sudo).
#
# What it does:
#   1. Installs Python 3, pip, venv, and nginx
#   2. Creates a Python venv and installs dependencies
#   3. Writes a systemd service that runs gunicorn on 127.0.0.1:5000
#   4. Writes an nginx config that reverse-proxies port 80 → 5000
#      (You should add TLS via certbot yourself.)
#   5. Enables and starts both services

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_USER="${SUDO_USER:-www-data}"
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
DB_PATH="${APP_DIR}/screentime.db"
PORT=5000
DOMAIN="${DOMAIN:-localhost}"   # Set DOMAIN=your.domain.com before running

echo "==> Installing system packages…"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx

echo "==> Creating Python venv…"
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"

echo "==> Writing /etc/systemd/system/screentime.service…"
cat > /etc/systemd/system/screentime.service <<EOF
[Unit]
Description=ScreenTime Server
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment=SECRET_KEY=${SECRET_KEY}
Environment=DB_PATH=${DB_PATH}
Environment=PORT=${PORT}
ExecStart=${APP_DIR}/.venv/bin/gunicorn app:app \\
    --bind 127.0.0.1:${PORT} \\
    --workers 2 \\
    --timeout 60 \\
    --access-logfile /var/log/screentime-access.log \\
    --error-logfile  /var/log/screentime-error.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "==> Writing /etc/nginx/sites-available/screentime…"
cat > /etc/nginx/sites-available/screentime <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 10M;

    location / {
        proxy_pass         http://127.0.0.1:${PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/screentime /etc/nginx/sites-enabled/screentime
rm -f /etc/nginx/sites-enabled/default

echo "==> Enabling services…"
systemctl daemon-reload
systemctl enable --now screentime
systemctl reload nginx

echo ""
echo "========================================="
echo " ScreenTime is running!"
echo " Open: http://${DOMAIN}/"
echo " Then visit /setup to create your admin account."
echo ""
echo " SECRET_KEY (save this!): ${SECRET_KEY}"
echo " Add it to the [Service] Environment in:"
echo "   /etc/systemd/system/screentime.service"
echo "   (it was already written there this run)"
echo ""
echo " For HTTPS: sudo apt install certbot python3-certbot-nginx"
echo "            sudo certbot --nginx -d ${DOMAIN}"
echo "========================================="
