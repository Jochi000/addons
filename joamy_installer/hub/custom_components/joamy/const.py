"""Konstanten des JoAmy-Grundbausteins (Hub).

Der Hub ist die EINE Integration für alle JoAmy-Karten. Warum: Home Assistant
liest die Liste der Custom-Integrationen nur beim Start ein — jede NEUE
Integration bräuchte also einen Neustart. Der Hub wird einmal beim Einrichten
installiert (ein einziger Neustart, wie bei HACS); alle Käufe danach sind nur
noch Dateien in seinem static/-Ordner plus ein Reload im laufenden Betrieb.

Kompatibilitäts-Vertrag (die Karten bleiben UNVERÄNDERT):
- WS-Kommandos heißen weiter ``joamy_<baustein>/config|store/get|store/patch|subscribe``.
- Store-Dateien heißen weiter ``.storage/joamy_<baustein>.store``.
- Static-URLs heißen weiter ``/joamy_<baustein>/static/…`` — der Hub mappt sie
  auf seine Unterordner ``static/<baustein>/``.
"""

from __future__ import annotations

from typing import Any

DOMAIN = "joamy"
VERSION = "0.2.0"

# Alle Bausteine, die der Hub kennt. WS-Kommandos + Stores werden für ALLE
# registriert (ein Store ohne Karte ist leer und harmlos); Static-Pfad und
# Karten-URL gibt es nur für Bausteine, deren Ordner wirklich daliegt.
import os
import re

BAUSTEINE = ("kochbuch", "familie", "kamera", "media", "basics")


def entdecke_bausteine(static_root: str) -> tuple[str, ...]:
    """Bekannte Bausteine + alles, was als Ordner unter static/ liegt.

    Ein Karten-Update darf einen NEUEN Baustein mitbringen, ohne dass der Hub
    selbst aktualisiert (und HA neu gestartet) werden muss: der Installer legt
    nur den Ordner an, der Entry-Reload nimmt ihn hier auf. Nur schlichte
    Ordnernamen zaehlen — nichts anderes darf zum WS-Kommando werden.
    """
    gefunden = list(BAUSTEINE)
    try:
        for name in sorted(os.listdir(static_root)):
            if name in gefunden:
                continue
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", name):
                continue
            if os.path.isdir(os.path.join(static_root, name)):
                gefunden.append(name)
    except OSError:
        pass
    return tuple(gefunden)

# Baustein-eigene Zusatzfelder in der config-Antwort (Vertrag der jeweiligen Karte).
CONFIG_EXTRAS = {
    "kochbuch": {
        "rezepte_url": "/joamy_kochbuch/static/rezepte.json",
        "fotos_base": "/joamy_kochbuch/static/fotos/",
    },
}

STORAGE_VERSION = 1
SAVE_DELAY = 1.0


def static_url_path(baustein: str) -> str:
    return f"/joamy_{baustein}/static"


def storage_key(baustein: str) -> str:
    return f"joamy_{baustein}.store"


def event_updated(baustein: str) -> str:
    return f"joamy_{baustein}_updated"


def card_dateiname(baustein: str) -> str:
    return f"joamy-{baustein}-card.js"


# Schlüssel in hass.data[DOMAIN]
DATA_RUNTIMES = "runtimes"
DATA_WS_REGISTERED = "ws_registered"
DATA_STATIC_REGISTERED = "static_registered"
DATA_CARD_URLS = "card_urls"


def default_store_data() -> dict[str, Any]:
    """Leere Store-Struktur (users[uid] = pro-User-Daten, z. B. Style-Wahl)."""
    return {"users": {}, "version": 0}
