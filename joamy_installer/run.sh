#!/usr/bin/with-contenv sh
# JoAmy Installer — Startscript. WICHTIG: with-contenv! Ohne reicht s6 die
# Container-Umgebung (v. a. SUPERVISOR_TOKEN) NICHT an den Prozess durch —
# jeder Core-/Supervisor-Aufruf endet dann mit 401, obwohl docker-exec-Tests
# im selben Container funktionieren. SUPERVISOR_TOKEN stellt das Add-on-System
# bereit (homeassistant_api: true); damit spricht /app/main.py die Core-API
# unter http://supervisor/core/api (HA-Version, Config-Flow, Neustart).
# WICHTIG: `map: homeassistant_config` mountet den HA-Config-Ordner im
# Container unter /homeassistant (NICHT /config) — ohne diese Variable
# schriebe die App ins vergängliche Container-Dateisystem.
export CONFIG_DIR=/homeassistant
echo "[joamy] Starte Installer …"
exec python3 -u /app/main.py
