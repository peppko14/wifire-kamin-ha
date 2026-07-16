#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="wifire-kamin.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CURRENT_USER="${SUDO_USER:-$USER}"
CURRENT_GROUP="$(id -gn "${CURRENT_USER}")"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausführen:"
  echo "  sudo ${SCRIPT_DIR}/install_service_v0.12.4.sh"
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/mqtt_discovery.py" ]]; then
  echo "mqtt_discovery.py wurde nicht gefunden:"
  echo "  ${PROJECT_DIR}/mqtt_discovery.py"
  exit 1
fi

CONFIG_FILE="${PROJECT_DIR}/config.py"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Private Konfiguration wurde nicht gefunden:"
  echo "  ${CONFIG_FILE}"
  echo "Erstelle sie zuerst aus config.example.py."
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
  echo "  python3 -m pip install --require-hashes --only-binary=:all: \\"
  echo "    -r requirements.lock"
  exit 1
fi

TEMPLATE="${SCRIPT_DIR}/wifire-kamin.service.template"
TARGET="/etc/systemd/system/${SERVICE_NAME}"
BACKUP="${TARGET}.backup"
DATA_DIR="${PROJECT_DIR}/data"

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "Service-Vorlage fehlt:"
  echo "  ${TEMPLATE}"
  exit 1
fi

install -d \
  -m 0700 \
  -o "${CURRENT_USER}" \
  -g "${CURRENT_GROUP}" \
  "${DATA_DIR}"

chown "${CURRENT_USER}:${CURRENT_GROUP}" "${CONFIG_FILE}"
chmod 0600 "${CONFIG_FILE}"

TEMP_TARGET="$(mktemp /tmp/wifire-kamin.XXXXXX.service)"
cleanup() {
  rm -f "${TEMP_TARGET}"
}
trap cleanup EXIT

sed \
  -e "s|@USER@|${CURRENT_USER}|g" \
  -e "s|@PROJECT_DIR@|${PROJECT_DIR}|g" \
  -e "s|@PYTHON@|${PYTHON_BIN}|g" \
  "${TEMPLATE}" > "${TEMP_TARGET}"

echo "Prüfe die gerenderte systemd-Unit ..."
systemd-analyze verify "${TEMP_TARGET}"

if [[ -f "${TARGET}" ]]; then
  cp --preserve=mode,ownership,timestamps "${TARGET}" "${BACKUP}"
fi

install -m 0644 "${TEMP_TARGET}" "${TARGET}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo
echo "Service installiert und gehärtet:"
echo "  Benutzer:       ${CURRENT_USER}"
echo "  Projektpfad:    ${PROJECT_DIR}"
echo "  Python:         ${PYTHON_BIN}"
echo "  Schreibpfad:    ${DATA_DIR}"
echo "  config.py:      Modus 600"
if [[ -f "${BACKUP}" ]]; then
  echo "  Vorige Unit:    ${BACKUP}"
fi
echo
systemctl status "${SERVICE_NAME}" --no-pager -l
echo
systemd-analyze security "${SERVICE_NAME}" --no-pager || true
