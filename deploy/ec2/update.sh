#!/usr/bin/env bash
# Deploy what's on main: pull, install, restart (docs/10-deployment-ops.md).
# Run on the instance:  sudo bash /opt/homing/app/deploy/ec2/update.sh
set -euo pipefail

APP=/opt/homing/app
sudo -u homing git -C "$APP" pull --ff-only
sudo -u homing bash -c "cd $APP/server && UV_CACHE_DIR=/opt/homing/.cache/uv uv sync --frozen --no-dev"
# The search model (about 120 MB) is downloaded once, now, not on someone's first search.
sudo -u homing bash -c "cd $APP/server && .venv/bin/python -c 'from app.search.embed import get_embedder; get_embedder()'"
install -m 644 "$APP/deploy/ec2/homing-api.service" "$APP/deploy/ec2/homing-worker.service"   /etc/systemd/system/
systemctl daemon-reload

# The API runs the migrations before it starts, then the worker restarts on the new code.
systemctl restart homing-api
systemctl restart homing-worker
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null; then
    echo "API is up on $(sudo -u homing git -C "$APP" log -1 --format='%h %s')."
    exit 0
  fi
  sleep 1
done
echo "The API didn't come up. See: journalctl -u homing-api -n 50"
exit 1
