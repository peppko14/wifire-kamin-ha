#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="wifire-kamin.service"
TARGET="/etc/systemd/system/${SERVICE_NAME}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausführen:"
  echo "  sudo $0"
  exit 1
fi

systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
rm -f "${TARGET}"
systemctl daemon-reload

echo "Der systemd-Service wurde entfernt."
echo "Projektdateien und config.py bleiben erhalten."
