#!/usr/bin/env bash
# Entfernt den systemd-Dienst. Programm, Konfiguration und Daten bleiben.
set -u
PORT="${1:-8022}"
[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo starten."; exit 1; }

systemctl disable --now xrechnung 2>/dev/null || true
rm -f /etc/systemd/system/xrechnung.service
systemctl daemon-reload

if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --remove-port="$PORT"/tcp >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
fi

echo "Dienst entfernt. Konfiguration unter config/ und Daten unter data/ sind unberuehrt."
echo "Das Dienstkonto 'xrechnung' bleibt bestehen - bei Bedarf: userdel xrechnung"
