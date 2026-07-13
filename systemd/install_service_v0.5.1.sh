#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="wifire-kamin.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CURRENT_USER="${SUDO_USER:-$USER}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausführen:"
  echo "  sudo ${SCRIPT_DIR}/install_service_v0.5.1.sh"
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/mqtt_discovery.py" ]]; then
  echo "mqtt_discovery.py wurde nicht gefunden:"
  echo "  ${PROJECT_DIR}/mqtt_discovery.py"
  exit 1
fi

if [[ -x "${PROJECT_DIR}/venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/venv/bin/python"
elif [[ -x "${PROJECT_DIR}/../venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/../venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
  echo "Keine geeignete Python-Installation gefunden."
  echo "Erstelle zuerst eine virtuelle Umgebung:"
  echo "  python3 -m venv venv"
  echo "  source venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

TEMPLATE="${SCRIPT_DIR}/wifire-kamin.service.template"
TARGET="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "Service-Vorlage fehlt:"
  echo "  ${TEMPLATE}"
  exit 1
fi

sed \
  -e "s|@USER@|${CURRENT_USER}|g" \
  -e "s|@PROJECT_DIR@|${PROJECT_DIR}|g" \
  -e "s|@PYTHON@|${PYTHON_BIN}|g" \
  "${TEMPLATE}" > "${TARGET}"

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo
echo "Service installiert:"
echo "  Benutzer:     ${CURRENT_USER}"
echo "  Projektpfad:  ${PROJECT_DIR}"
echo "  Python:       ${PYTHON_BIN}"
echo
systemctl status "${SERVICE_NAME}" --no-pager -l
