"""WebSocket-API des JoAmy-Hubs — bedient ALLE Bausteine unter ihren alten Namen.

Je Baustein (kochbuch/familie/kamera/media) werden vier Kommandos registriert,
deckungsgleich zu den früheren Einzel-Integrationen (die Karten merken keinen
Unterschied):

- ``joamy_<b>/config``       -> me/nutzer/version (+ Baustein-Extras, z. B.
                                rezepte_url/fotos_base beim Kochbuch)
- ``joamy_<b>/store/get``    -> kompletter Store {global, users, version, stabil_id}
- ``joamy_<b>/store/patch``  -> Deep-Merge in users[<me>] (scope me) bzw. global;
                                ``null`` löscht einen Schlüssel
- ``joamy_<b>/subscribe``    -> Push bei jedem Update (Live-Sync zwischen Geräten)

Alle ohne Admin-Pflicht — normale Authentifizierung genügt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.auth.models import User
from homeassistant.components import websocket_api
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    BAUSTEINE,
    CONFIG_EXTRAS,
    DATA_RUNTIMES,
    DOMAIN,
    SAVE_DELAY,
    event_updated,
)

if TYPE_CHECKING:
    from . import BausteinRuntime

ERR_NOT_LOADED = "not_loaded"


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Vier Kommandos je Baustein registrieren (einmal pro HA-Laufzeit)."""
    for baustein in BAUSTEINE:
        for cmd in _baue_kommandos(baustein):
            websocket_api.async_register_command(hass, cmd)


def _get_runtime(hass: HomeAssistant, baustein: str) -> BausteinRuntime | None:
    runtime = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES)
    return runtime.bausteine.get(baustein) if runtime else None


def _stabil_id(hass: HomeAssistant) -> str:
    runtime = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES)
    return runtime.stabil_id if runtime else ""


def _send_not_loaded(connection: websocket_api.ActiveConnection, msg_id: int) -> None:
    connection.send_error(msg_id, ERR_NOT_LOADED, "JoAmy ist nicht geladen.")


def _display_name(user: User) -> str:
    return (user.name or "").strip() or "?"


def _build_initials(users: list[User]) -> dict[str, str]:
    """Initialen je User-ID: erster Buchstabe, bei Kollision zwei Buchstaben."""
    groups: dict[str, list[User]] = {}
    for user in users:
        letter = _display_name(user)[0].upper()
        groups.setdefault(letter, []).append(user)

    initials: dict[str, str] = {}
    for letter, group in groups.items():
        if len(group) == 1:
            initials[group[0].id] = letter
            continue
        for user in group:
            name = _display_name(user)
            initials[user.id] = name[:2].title() if len(name) >= 2 else letter
    return initials


def _cleaned(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _cleaned(v) for k, v in value.items() if v is not None}
    return value


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    """Patch rekursiv in target mergen; Wert ``null`` löscht den Schlüssel."""
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            existing = target.get(key)
            if isinstance(existing, dict):
                _deep_merge(existing, value)
            else:
                target[key] = _cleaned(value)
        else:
            target[key] = value


def _baue_kommandos(baustein: str):
    """Die vier Handler EINES Bausteins bauen (Closures statt Schema-Magie).

    Die Dekoratoren von websocket_api verlangen einen festen type-String —
    darum entstehen die Handler hier programmatisch je Baustein.
    """

    async def config(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        runtime = _get_runtime(hass, baustein)
        if runtime is None:
            _send_not_loaded(connection, msg["id"])
            return

        users = [
            user
            for user in await hass.auth.async_get_users()
            if user.is_active and not user.system_generated
        ]
        users.sort(key=lambda user: (_display_name(user).lower(), user.id))
        initials = _build_initials(users)

        me = connection.user
        connection.send_result(
            msg["id"],
            {
                "me": {
                    "id": me.id,
                    "name": _display_name(me),
                    "initial": initials.get(me.id, _display_name(me)[0].upper()),
                    "admin": me.is_admin,
                },
                "nutzer": [
                    {
                        "id": user.id,
                        "name": _display_name(user),
                        "initial": initials[user.id],
                    }
                    for user in users
                ],
                "version": runtime.data["version"],
                **CONFIG_EXTRAS.get(baustein, {}),
            },
        )

    @callback
    def store_get(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        runtime = _get_runtime(hass, baustein)
        if runtime is None:
            _send_not_loaded(connection, msg["id"])
            return

        connection.send_result(
            msg["id"],
            {
                "global": runtime.data.get("global", {}),
                "users": runtime.data["users"],
                "version": runtime.data["version"],
                "stabil_id": _stabil_id(hass),
            },
        )

    @callback
    def store_patch(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        runtime = _get_runtime(hass, baustein)
        if runtime is None:
            _send_not_loaded(connection, msg["id"])
            return

        patch: dict[str, Any] = msg["data"]
        if msg["scope"] == "me":
            # Identität ist IMMER der verbundene Benutzer.
            target = runtime.data["users"].setdefault(connection.user.id, {})
        else:
            target = runtime.data.setdefault("global", {})

        _deep_merge(target, patch)
        runtime.data["version"] += 1
        runtime.dirty = True
        runtime.store.async_delay_save(lambda: runtime.data, SAVE_DELAY)

        version: int = runtime.data["version"]
        connection.send_result(msg["id"], {"ok": True, "version": version})
        hass.bus.async_fire(event_updated(baustein), {"version": version})

    @callback
    def subscribe(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        @callback
        def _forward(event: Event) -> None:
            connection.send_message(websocket_api.event_message(msg["id"], event.data))

        connection.subscriptions[msg["id"]] = hass.bus.async_listen(
            event_updated(baustein), _forward
        )
        connection.send_result(msg["id"])

    return [
        websocket_api.websocket_command(
            {vol.Required("type"): f"joamy_{baustein}/config"}
        )(websocket_api.async_response(config)),
        websocket_api.websocket_command(
            {vol.Required("type"): f"joamy_{baustein}/store/get"}
        )(store_get),
        websocket_api.websocket_command(
            {
                vol.Required("type"): f"joamy_{baustein}/store/patch",
                vol.Required("scope"): vol.In(("me", "global")),
                vol.Required("data"): dict,
            }
        )(store_patch),
        websocket_api.websocket_command(
            {vol.Required("type"): f"joamy_{baustein}/subscribe"}
        )(subscribe),
    ]
