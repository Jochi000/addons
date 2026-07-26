"""JoAmy-Grundbaustein (Hub): liefert ALLE gekauften JoAmy-Karten aus.

Warum ein Hub: Home Assistant entdeckt neue Custom-Integrationen nur beim
Start. Mit dem Hub gibt es genau EINEN Neustart — beim Einrichten. Jeder Kauf
danach legt nur Dateien in static/<baustein>/ ab; ein reload_config_entry im
laufenden Betrieb registriert die neue Karte (Static-Pfad + extra_js_url).

Der Hub erfüllt die bestehenden Verträge der Karten 1:1:
- Static:  /joamy_<baustein>/static/…  →  <hub>/static/<baustein>/…
- Store:   .storage/joamy_<baustein>.store  (Alt-Daten bleiben gültig)
- WS:      joamy_<baustein>/config|store/get|store/patch|subscribe
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    BAUSTEINE,
    DATA_CARD_URLS,
    DATA_RUNTIMES,
    DATA_STATIC_REGISTERED,
    DATA_WS_REGISTERED,
    DOMAIN,
    STORAGE_VERSION,
    card_dateiname,
    default_store_data,
    static_url_path,
    storage_key,
)
from .websocket_api import async_register_websocket_commands

type JoamyConfigEntry = ConfigEntry[dict[str, Any]]


@dataclass
class BausteinRuntime:
    """Laufzeit-Daten EINES Bausteins (Store + Änderungszähler)."""

    store: Store[dict[str, Any]]
    data: dict[str, Any]
    dirty: bool = False


@dataclass
class JoamyRuntime:
    """Laufzeit-Daten des Hubs: ein BausteinRuntime je Baustein + Zuhause-Kennung."""

    bausteine: dict[str, BausteinRuntime] = field(default_factory=dict)
    # Stabile Kennung DIESES Zuhauses (Hash der HA-Instanz-ID). Die Karten
    # schicken sie bei der Lizenz-Aktivierung mit, damit ein neu angelegter
    # Karten-Speicher nicht fälschlich als Zweitinstallation gilt. Die ROHE
    # Instanz-ID verlässt Home Assistant nie.
    stabil_id: str = ""


def _static_dir(baustein: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", baustein)


async def async_setup_entry(hass: HomeAssistant, entry: JoamyConfigEntry) -> bool:
    """Hub aufsetzen: Stores laden, Static-Pfade + Karten registrieren."""
    runtime = JoamyRuntime()

    for baustein in BAUSTEINE:
        store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, storage_key(baustein))
        data = await store.async_load()
        if not isinstance(data, dict):
            data = default_store_data()
        if not isinstance(data.get("users"), dict):
            data["users"] = {}
        if not isinstance(data.get("version"), int):
            data["version"] = 0
        runtime.bausteine[baustein] = BausteinRuntime(store=store, data=data)

    # Fällt das aus irgendeinem Grund aus, läuft der Hub OHNE Kennung weiter
    # (die Karten verhalten sich dann wie früher) — er darf daran nie scheitern.
    try:
        from homeassistant.helpers import instance_id as ha_instance_id

        roh = await ha_instance_id.async_get(hass)
        runtime.stabil_id = hashlib.sha256(
            f"{roh}|joamy.install.v1".encode()
        ).hexdigest()[:32]
    except Exception:  # noqa: BLE001 - Kennung ist Komfort, kein Muss
        runtime.stabil_id = ""

    domain_data: dict[str, Any] = hass.data.setdefault(DOMAIN, {})
    domain_data[DATA_RUNTIMES] = runtime
    entry.runtime_data = runtime.bausteine

    if not domain_data.get(DATA_WS_REGISTERED):
        async_register_websocket_commands(hass)
        domain_data[DATA_WS_REGISTERED] = True

    # Static-Pfade: nur für Bausteine, deren Ordner wirklich daliegt. Ein
    # Pfad lässt sich nicht doppelt registrieren → einmal pro HA-Laufzeit
    # merken; NEUE Bausteine kommen per Reload dazu (Ordner entsteht → Pfad).
    registriert: set[str] = domain_data.setdefault(DATA_STATIC_REGISTERED, set())
    vorhanden = await hass.async_add_executor_job(
        lambda: [b for b in BAUSTEINE if os.path.isdir(_static_dir(b))]
    )
    neu = [b for b in vorhanden if b not in registriert]
    if neu:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(static_url_path(b), _static_dir(b), True) for b in neu]
        )
        registriert.update(neu)

    # Karten automatisch laden — Cache-Bust INHALTSBASIERT (?v=<sha1>), damit
    # ein Karten-Update nach dem Reload sicher frisch aus dem Netz kommt.
    alte_urls: list[str] = domain_data.get(DATA_CARD_URLS) or []
    for url in alte_urls:
        remove_extra_js_url(hass, url)
    urls = await hass.async_add_executor_job(_karten_urls, vorhanden)
    for url in urls:
        add_extra_js_url(hass, url)
    domain_data[DATA_CARD_URLS] = urls

    return True


def _karten_urls(bausteine: list[str]) -> list[str]:
    """URL je vorhandener Karte, mit Inhalts-Hash (Blocking-IO → Executor)."""
    urls: list[str] = []
    for baustein in bausteine:
        pfad = os.path.join(_static_dir(baustein), card_dateiname(baustein))
        try:
            with open(pfad, "rb") as f:
                h = hashlib.sha1(f.read()).hexdigest()[:12]
        except OSError:
            continue  # Ordner ohne Karte (z. B. nur Fonts) → nichts laden
        urls.append(f"{static_url_path(baustein)}/{card_dateiname(baustein)}?v={h}")
    return urls


async def async_unload_entry(hass: HomeAssistant, entry: JoamyConfigEntry) -> bool:
    """Beim Entladen (auch Teil jedes Reloads): Karten-URLs austragen, Stores sichern."""
    domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})
    for url in domain_data.get(DATA_CARD_URLS) or []:
        remove_extra_js_url(hass, url)
    domain_data[DATA_CARD_URLS] = []

    runtime: JoamyRuntime | None = domain_data.get(DATA_RUNTIMES)
    if runtime:
        for brt in runtime.bausteine.values():
            if brt.dirty:
                await brt.store.async_save(brt.data)
                brt.dirty = False
    domain_data.pop(DATA_RUNTIMES, None)
    return True
