#!/usr/bin/env bash
# First-time setup of the Homing API on a fresh Ubuntu 24.04 EC2 instance in eu-west-3
# (docs/10-deployment-ops.md). Before running it:
#   1. Point the API's DNS name (A record) at the instance's Elastic IP.
#   2. Put the production settings (server/.env.production) in /etc/homing/homing.env.
# Then run:  sudo bash setup.sh homing-api.crowscap.xyz
set -euo pipefail

DOMAIN="${1:?Usage: sudo bash setup.sh <api domain>}"
REPO=https://github.com/Isreal-Oparanti/Homing.git
HOME_DIR=/opt/homing
UV_VERSION=0.13.6  # the version uv.lock was made with
ENV_FILE=/etc/homing/homing.env

[ -f "$ENV_FILE" ] || { echo "Put the production settings in $ENV_FILE first."; exit 1; }

apt-get update
apt-get install -y --no-install-recommends git curl ffmpeg gnupg ca-certificates   debian-keyring debian-archive-keyring apt-transport-https

# Caddy, from its own apt repository (caddyserver.com/docs/install).
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key   | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt   > /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy

# uv, installed for everyone in /usr/local/bin.
curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh"   | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

# A small instance needs swap to install the dependencies and run both services.
if [ ! -f /swapfile ] && [ "$(free -m | awk '/Mem:/ {print $2}')" -lt 3000 ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

id homing >/dev/null 2>&1   || useradd --system --create-home --home-dir "$HOME_DIR" --shell /usr/sbin/nologin homing
chown root:homing "$ENV_FILE" && chmod 640 "$ENV_FILE"
[ -d "$HOME_DIR/app" ] || sudo -u homing git clone "$REPO" "$HOME_DIR/app"

DEPLOY="$HOME_DIR/app/deploy/ec2"
install -m 644 "$DEPLOY/homing-api.service" "$DEPLOY/homing-worker.service" /etc/systemd/system/
sed "s/API_DOMAIN/$DOMAIN/" "$DEPLOY/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable homing-api homing-worker
bash "$DEPLOY/update.sh"
systemctl reload caddy
echo "Done. From anywhere: curl https://$DOMAIN/api/v1/health"
