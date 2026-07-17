#!/usr/bin/env sh
# JoAmy Automatiken — Startscript. SUPERVISOR_TOKEN stellt das Add-on-System
# bereit (homeassistant_api: true); damit spricht /app/main.py die Core-WS-API
# unter ws://supervisor/core/websocket.
echo "[joamy] Starte Automatiken …"
exec python3 -u /app/main.py
