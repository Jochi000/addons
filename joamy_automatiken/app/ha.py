"""JoAmy Automatiken — geteilter HA-WebSocket-Client (Add-on-Umgebung).

Verbindet sich über den Supervisor-Proxy (ws://supervisor/core/websocket,
Auth via SUPERVISOR_TOKEN). Bietet den Daemons genau das, was Joachims
Original-Architektur nutzt: get_states-Cache, state_changed-Events,
call_service, set_state (REST) — plus Auto-Reconnect mit Backoff.
"""
import asyncio
import json
import logging
import os
import urllib.request

LOG = logging.getLogger("joamy.ha")

WS_URL = os.environ.get("JOAMY_WS_URL", "ws://supervisor/core/websocket")
REST_URL = os.environ.get("JOAMY_REST_URL", "http://supervisor/core/api")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


class HaClient:
    def __init__(self):
        self.states = {}           # entity_id -> state-dict
        self.listeners = []        # async callbacks(entity_id, new_state, old_state)
        self._ws = None
        self._id = 0
        self._pending = {}
        self.bereit = asyncio.Event()

    async def verbinde_dauerhaft(self):
        """Endlosschleife: verbinden, lauschen, bei Abbruch mit Backoff neu."""
        import websockets
        backoff = 1
        while True:
            try:
                async with websockets.connect(WS_URL, max_size=16 * 1024 * 1024) as ws:
                    self._ws = ws
                    await self._auth(ws)
                    await self._initial(ws)
                    backoff = 1
                    self.bereit.set()
                    await self._lausche(ws)
            except Exception as e:
                LOG.warning("WS-Verbindung verloren: %s — neu in %ss", e, backoff)
            self.bereit.clear()
            self._ws = None
            for f in self._pending.values():
                if not f.done():
                    f.set_exception(ConnectionError("WS weg"))
            self._pending.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _auth(self, ws):
        msg = json.loads(await ws.recv())
        if msg.get("type") == "auth_required":
            await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
            msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_ok":
            raise ConnectionError(f"Auth fehlgeschlagen: {msg}")

    async def _initial(self, ws):
        states = await self._frage_roh(ws, {"type": "get_states"})
        self.states = {s["entity_id"]: s for s in states}
        await self._frage_roh(ws, {"type": "subscribe_events", "event_type": "state_changed"})
        LOG.info("verbunden — %d States", len(self.states))

    async def _frage_roh(self, ws, payload):
        self._id += 1
        mid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        await ws.send(json.dumps({**payload, "id": mid}))
        # Antworten werden hier inline gelesen, bis unsere id kommt (nur beim
        # Setup benutzt — im Betrieb übernimmt _lausche das Routing).
        while not fut.done():
            msg = json.loads(await ws.recv())
            self._route(msg)
        return await fut

    def _route(self, msg):
        t = msg.get("type")
        if t == "result":
            fut = self._pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                if msg.get("success"):
                    fut.set_result(msg.get("result"))
                else:
                    fut.set_exception(RuntimeError(str(msg.get("error"))))
        elif t == "event":
            data = (msg.get("event") or {}).get("data") or {}
            eid = data.get("entity_id")
            if not eid:
                return
            neu, alt = data.get("new_state"), data.get("old_state")
            if neu is None:
                self.states.pop(eid, None)
            else:
                self.states[eid] = neu
            for cb in self.listeners:
                try:
                    asyncio.get_event_loop().create_task(cb(eid, neu, alt))
                except Exception:
                    LOG.exception("Listener-Fehler %s", eid)

    async def _lausche(self, ws):
        async for roh in ws:
            self._route(json.loads(roh))

    # ---- API für die Daemons ----
    def state(self, eid):
        s = self.states.get(eid)
        return s.get("state") if s else None

    def attr(self, eid, name, default=None):
        s = self.states.get(eid)
        return (s.get("attributes") or {}).get(name, default) if s else default

    async def frage(self, typ, **extra):
        """Beliebiges WS-Kommando (z. B. lovelace/config)."""
        if not self._ws:
            raise ConnectionError("nicht verbunden")
        self._id += 1
        mid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send(json.dumps({"id": mid, "type": typ, **extra}))
        return await asyncio.wait_for(fut, 15)

    async def call(self, domain, service, data=None):
        """Service-Call. NUR-BEI-ÄNDERUNG-Prüfung machen die Daemons selbst
        (Pflicht-Regel aus der Original-Architektur)."""
        if not self._ws:
            raise ConnectionError("nicht verbunden")
        self._id += 1
        mid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send(json.dumps({
            "id": mid, "type": "call_service",
            "domain": domain, "service": service,
            "service_data": data or {},
        }))
        return await asyncio.wait_for(fut, 15)

    def set_state_sync(self, eid, state, attributes=None):
        """Sensor-Zustand per REST setzen (für Status-Sensoren der Daemons).
        Synchron + best effort — wie in der Original-Architektur."""
        try:
            req = urllib.request.Request(
                f"{REST_URL}/states/{eid}", method="POST",
                data=json.dumps({"state": str(state), "attributes": attributes or {}}).encode(),
                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:
            LOG.warning("set_state %s fehlgeschlagen: %s", eid, e)


def lade_automatiken_config():
    """Liest /config/www/joamy/joamy-automatiken.json (vom Wizard erzeugt)."""
    pfad = os.environ.get("JOAMY_CONFIG", "/config/www/joamy/joamy-automatiken.json")
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        LOG.warning("Keine joamy-automatiken.json unter %s — nichts zu tun.", pfad)
        return {}
    except Exception:
        LOG.exception("joamy-automatiken.json unlesbar")
        return {}
