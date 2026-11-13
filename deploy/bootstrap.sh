#!/bin/bash
# Run as root on the instance after the repo is cloned to /opt/otm/app (the CloudFormation user data calls this).
# Creates the virtualenv, installs the app and enables the two IST timers.
set -euo pipefail

APP=/opt/otm/app
VENV=/opt/otm/venv

python3.12 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP/requirements.txt"
"$VENV/bin/pip" install --quiet -e "$APP"
chown -R otm:otm /opt/otm

install -m 644 "$APP"/deploy/systemd/otm-*.service "$APP"/deploy/systemd/otm-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now otm-entry.timer otm-exit.timer
systemctl list-timers 'otm-*' --no-pager

echo
echo "Bootstrap finished."
echo "Next: store the Telegram values in SSM (see deploy/README.md), then test with:"
echo "  sudo -u otm bash -c 'set -a; . /etc/otm/otm.env; set +a; /opt/otm/venv/bin/otm notify-test'"
