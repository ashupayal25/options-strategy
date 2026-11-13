#!/bin/bash
# Pull the latest code onto the instance and restart the timers.
# Usage on the instance:  sudo bash /opt/otm/app/deploy/update.sh
set -euo pipefail

APP=/opt/otm/app
VENV=/opt/otm/venv
REPO=$(cat /etc/otm/repo_url)
REF=$(cat /etc/otm/repo_ref)
TOKEN_PARAM=$(cat /etc/otm/git_token_param)
REGION=$(grep -E '^AWS_DEFAULT_REGION=' /etc/otm/otm.env | cut -d= -f2)

AUTH_ARGS=()
if [ -n "$TOKEN_PARAM" ]; then
  TOKEN=$(aws ssm get-parameter --name "$TOKEN_PARAM" --with-decryption --query Parameter.Value --output text --region "$REGION")
  HOST=$(echo "$REPO" | sed -E 's#^(https://[^/]+/).*#\1#')
  AUTH_ARGS=(-c "http.$HOST.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)")
fi

cd "$APP"
git -c safe.directory="$APP" "${AUTH_ARGS[@]}" fetch origin "$REF"
git -c safe.directory="$APP" reset --hard FETCH_HEAD   # the server holds no local edits

"$VENV/bin/pip" install --quiet -r requirements.txt
"$VENV/bin/pip" install --quiet -e .
chown -R otm:otm /opt/otm

install -m 644 "$APP"/deploy/systemd/otm-*.service "$APP"/deploy/systemd/otm-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart otm-entry.timer otm-exit.timer
systemctl list-timers 'otm-*' --no-pager
echo "Updated to $(git -c safe.directory="$APP" rev-parse --short HEAD)."
