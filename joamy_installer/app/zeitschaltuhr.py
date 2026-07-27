"""JoAmy Zeitschaltuhr — Engine (läuft als Task IM Installer, kein extra Add-on).

Denkmodell: klassische mechanische Zeitschaltuhr. Uhren + Quick-Timer liegen im
GLOBALEN Store des Hub-Bausteins `zeitschaltuhr` (HAs .storage → überlebt
HA-Neustart, Add-on-Neustart und Updates). Die Engine hält eine eigene, dauerhafte
WebSocket zum Core (Supervisor-Proxy), rechnet Schaltpunkte, schaltet, und
schreibt NUR den Zweig `status` zurück (nächster Schaltpunkt, letzter Lauf,
autoritative Timer mit endsAt). Die Karte schreibt NUR `uhren`/`timer_wunsch` —
getrennte Zweige, keine Schreibkonflikte.

Store-Formate: siehe bausteine/ZEITSCHALTUHR-PHASE0-BERICHT.md (Kap. 3).

Leitregeln (Auftrag):
- Bedingungen begrenzen NUR das Einschalten; Ausschalten läuft immer.
- Bedingung nicht erfüllt ⇒ überspringen, KEIN Nachholen. Fehlende person.*-
  Entitäten ⇒ Bedingung neutral (JoAmy-Regel).
- Über Mitternacht: off < on ⇒ off am Folgetag, dem Starttag zugeordnet.
- DST: nicht existente Zeit (Frühjahrslücke) → nächste gültige Minute;
  doppelte Stunde (Herbst) → erste Instanz (fold=0).
- Neustart-Reconciliation: verpasste AUS immer nachholen (24-h-Fenster);
  verpasste EIN nur, wenn das Paar-AUS noch aussteht (= jetzt im Fenster).
  In Downtime abgelaufene Timer: Endaktion nachholen. Nichts bleibt hängen.
- Entität nicht verfügbar: 3 Versuche (10/30/60 s), dann Log + Status.
- Zeitquelle ist INJIZIERBAR (Prüfstand testet DST/Mitternacht ohne echte Uhr).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

LOG = logging.getLogger("joamy.zeitschaltuhr")

BAUSTEIN = "zeitschaltuhr"
TICK_MAX_S = 30           # nie länger schlafen (Weckruf kommt zusätzlich per subscribe)
FEUER_FENSTER_S = 90      # Schaltpunkt gilt bis 90 s nach Soll als "jetzt fällig"
NACHHOL_FENSTER_S = 24 * 3600
RETRY_ABSTAENDE_S = (10, 30, 60)
SCHALTBARE_DOMAINS = ("switch", "light", "input_boolean", "fan")
DATA_DATEI = "/data/zeitschaltuhr.json"


# ======================================================================
# Reine Rechenfunktionen (Zeitquelle wird hereingereicht → Prüfstand)
# ======================================================================

def zs_lokalzeit(zeit_utc: datetime, tz: ZoneInfo) -> datetime:
    return zeit_utc.astimezone(tz)


def zs_zeitpunkt_an_tag(tag: datetime, hh: int, mm: int, tz: ZoneInfo) -> datetime:
    """Konkreter lokaler Zeitpunkt an einem Kalendertag — DST-fest.

    Frühjahrslücke (z. B. 02:30 am Wechseltag existiert nicht): Minute für
    Minute vorwärts bis zur ersten gültigen Zeit. Herbst-Doppelstunde:
    fold=0 = die ERSTE Instanz.
    """
    naiv = datetime(tag.year, tag.month, tag.day, hh, mm)
    for schub in range(0, 121):                     # max 2 h Verschiebung suchen
        kandidat = (naiv + timedelta(minutes=schub)).replace(tzinfo=tz, fold=0)
        # Nicht existente Zeiten normalisiert astimezone auf eine ANDERE
        # Wanduhr-Zeit — Rundreise über UTC entlarvt sie.
        rueck = kandidat.astimezone(ZoneInfo("UTC")).astimezone(tz)
        if (rueck.hour, rueck.minute) == (kandidat.hour, kandidat.minute):
            return kandidat
    return naiv.replace(tzinfo=tz)                  # praktisch unerreichbar


def zs_sonnenzeit(sonne: dict, event: str, offset_min: int, tz: ZoneInfo) -> datetime | None:
    """Nächster Sonnen-Zeitpunkt aus den sun.sun-Attributen (next_rising/next_setting)."""
    schluessel = "next_rising" if event == "sunrise" else "next_setting"
    roh = (sonne or {}).get(schluessel)
    if not roh:
        return None
    try:
        t = datetime.fromisoformat(str(roh).replace("Z", "+00:00"))
        return t.astimezone(tz) + timedelta(minutes=int(offset_min or 0))
    except Exception:
        return None


def zs_punkt_aufloesen(punkt: dict, tag: datetime, sonne: dict, tz: ZoneInfo) -> datetime | None:
    """Ein Schaltpunkt ({type:time,value} | {type:sun,event,offsetMin}) → lokale Zeit am Tag."""
    if not isinstance(punkt, dict):
        return None
    if punkt.get("type") == "sun":
        # Sonnenzeit gilt für den Tag, an dem sie fällt; für die Fensterrechnung
        # nähern wir die Uhrzeit des nächsten Ereignisses an diesem Kalendertag an.
        s = zs_sonnenzeit(sonne, punkt.get("event") or "sunset", punkt.get("offsetMin") or 0, tz)
        if s is None:
            return None
        return zs_zeitpunkt_an_tag(tag, s.hour, s.minute, tz)
    wert = str(punkt.get("value") or "")
    try:
        hh, mm = [int(x) for x in wert.split(":")[:2]]
    except Exception:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return zs_zeitpunkt_an_tag(tag, hh, mm, tz)


def zs_block_ereignisse(block: dict, jetzt: datetime, sonne: dict, tz: ZoneInfo) -> list[tuple[str, datetime]]:
    """Alle Schaltereignisse eines Blocks im Fenster gestern..übermorgen.

    Liefert [('ein'|'aus', lokale_zeit), …]. Tage: 0=Mo..6=So, gelten für den
    STARTTAG; ein Aus vor dem Ein gehört zum Folgetag (über Mitternacht).
    """
    tage = block.get("days") or [0, 1, 2, 3, 4, 5, 6]
    raus: list[tuple[str, datetime]] = []
    for delta in (-1, 0, 1, 2):
        tag = (jetzt + timedelta(days=delta))
        if tag.weekday() not in tage:
            continue
        ein = zs_punkt_aufloesen(block.get("on"), tag, sonne, tz)
        aus = zs_punkt_aufloesen(block.get("off"), tag, sonne, tz)
        if ein is not None:
            raus.append(("ein", ein))
        if aus is not None:
            if ein is not None and aus <= ein:
                aus = zs_zeitpunkt_an_tag(tag + timedelta(days=1), aus.hour, aus.minute, tz)
            raus.append(("aus", aus))
    raus.sort(key=lambda x: x[1])
    return raus


def zs_soll_zustand(uhr: dict, jetzt: datetime, sonne: dict, tz: ZoneInfo) -> bool | None:
    """Reconciliation-Kern: SOLL das Gerät jetzt an sein? None = kein Paar aktiv.

    True nur, wenn jetzt in einem Ein/Aus-Fenster liegt (verpasstes EIN wird
    dann nachgeholt, weil das AUS noch aussteht). False, wenn ein AUS im
    Nachhol-Fenster verpasst wurde. Sonst None (nichts erzwingen).
    """
    if not uhr.get("enabled", True):
        return None
    innen = False
    aus_verpasst = False
    for block in uhr.get("blocks") or []:
        ereignisse = zs_block_ereignisse(block, jetzt, sonne, tz)
        ein_zeit = None
        for art, zeit in ereignisse:
            if art == "ein":
                ein_zeit = zeit
            elif art == "aus":
                if ein_zeit is not None and ein_zeit <= jetzt < zeit:
                    innen = True
                if 0 <= (jetzt - zeit).total_seconds() <= NACHHOL_FENSTER_S:
                    aus_verpasst = True
                ein_zeit = None
        # Block nur mit Aus (Kap. 15.6): aus_verpasst greift oben mit.
    if innen:
        return True
    if aus_verpasst:
        return False
    return None


def zs_naechstes_ereignis(uhr: dict, jetzt: datetime, sonne: dict, tz: ZoneInfo):
    """(art, zeit) des nächsten zukünftigen Schaltpunkts der Uhr — oder None."""
    if not uhr.get("enabled", True):
        return None
    kommende = []
    for block in uhr.get("blocks") or []:
        for art, zeit in zs_block_ereignisse(block, jetzt, sonne, tz):
            if zeit > jetzt:
                kommende.append((art, zeit))
    return min(kommende, key=lambda x: x[1]) if kommende else None


def zs_faellig(uhr: dict, jetzt: datetime, sonne: dict, tz: ZoneInfo, geschaltet: dict) -> list[tuple[str, datetime, str]]:
    """Alle JETZT fälligen Schaltungen (im Feuerfenster, noch nicht gefeuert).

    geschaltet: {schluessel: epoch_s} — ein Ereignis feuert genau einmal.
    Liefert [(art, soll_zeit, schluessel), …].
    """
    raus = []
    for bi, block in enumerate(uhr.get("blocks") or []):
        for art, zeit in zs_block_ereignisse(block, jetzt, sonne, tz):
            alter = (jetzt - zeit).total_seconds()
            if not (0 <= alter <= FEUER_FENSTER_S):
                continue
            schluessel = f"{uhr.get('id')}|{bi}|{art}|{zeit.isoformat()}"
            if schluessel in geschaltet:
                continue
            raus.append((art, zeit, schluessel))
    return raus


# ======================================================================
# Engine
# ======================================================================

class ZeitschaltuhrEngine:
    """Eine dauerhafte WS zum Core; Uhren + Timer aus dem Hub-Store."""

    def __init__(self, session: aiohttp.ClientSession, supervisor_url: str, token: str,
                 zeit_quelle=None):
        self.session = session
        self.ws_url = f"{supervisor_url}/core/websocket"
        self.token = token
        self.zeit_quelle = zeit_quelle or (lambda: datetime.now(ZoneInfo("UTC")))
        self.tz = ZoneInfo("UTC")            # echte Zone kommt aus /api/config
        self.ws = None
        self._id = 0
        self._antworten: dict[int, asyncio.Future] = {}
        self._weck = asyncio.Event()
        self.geschaltet: dict[str, float] = {}   # Ereignis-Schlüssel → epoch (aus /data)
        self.timer: list[dict] = []              # autoritativ (auch in /data gespiegelt)
        self._letzter_status_json = ""

    # ---------- /data-Spiegel (Host-Reboot-Fenster, bevor HA antwortet) ----------
    def _data_lesen(self) -> None:
        try:
            with open(DATA_DATEI, encoding="utf-8") as f:
                d = json.load(f)
            self.geschaltet = {k: float(v) for k, v in (d.get("geschaltet") or {}).items()}
            self.timer = [t for t in (d.get("timer") or []) if isinstance(t, dict)]
        except Exception:
            pass

    def _data_schreiben(self) -> None:
        try:
            tmp = DATA_DATEI + ".neu"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"geschaltet": self.geschaltet, "timer": self.timer}, f)
            os.replace(tmp, DATA_DATEI)          # atomar
        except Exception as e:
            LOG.debug("Zeitschaltuhr: /data-Spiegel nicht schreibbar: %s", e)

    # ---------- WS-Grundverkehr ----------
    async def _frage(self, nutzlast: dict, timeout: float = 15):
        self._id += 1
        mid = self._id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._antworten[mid] = fut
        await self.ws.send_json(dict(nutzlast, id=mid))
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._antworten.pop(mid, None)

    async def _lausche(self) -> None:
        async for msg in self.ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            m = msg.json()
            mid = m.get("id")
            if m.get("type") == "result" and mid in self._antworten:
                fut = self._antworten[mid]
                if not fut.done():
                    if m.get("success"):
                        fut.set_result(m.get("result"))
                    else:
                        fut.set_exception(RuntimeError(str(m.get("error"))))
            elif m.get("type") == "event":
                # Store-Änderung (subscribe) → sofort rechnen.
                self._weck.set()

    async def _verbinden(self) -> bool:
        try:
            self.ws = await self.session.ws_connect(self.ws_url, heartbeat=25)
            while True:
                m = await asyncio.wait_for(self.ws.receive_json(), timeout=20)
                if m.get("type") == "auth_required":
                    await self.ws.send_json({"type": "auth", "access_token": self.token})
                elif m.get("type") == "auth_ok":
                    break
                elif m.get("type") == "auth_invalid":
                    return False
            asyncio.get_running_loop().create_task(self._lausche())
            # Zeitzone der Instanz + Weckruf bei Store-Änderungen
            cfg = await self._frage({"type": "get_config"})
            try:
                self.tz = ZoneInfo(str((cfg or {}).get("time_zone") or "UTC"))
            except Exception:
                self.tz = ZoneInfo("UTC")
            self._id += 1
            await self.ws.send_json({"id": self._id, "type": f"joamy_{BAUSTEIN}/subscribe"})
            return True
        except Exception as e:
            LOG.debug("Zeitschaltuhr: Verbindung fehlgeschlagen: %s", e)
            return False

    # ---------- Store + Zustände ----------
    async def _store(self) -> dict:
        s = await self._frage({"type": f"joamy_{BAUSTEIN}/store/get"})
        return (s or {}).get("global") or {}

    async def _status_schreiben(self, status: dict) -> None:
        als_json = json.dumps(status, sort_keys=True)
        if als_json == self._letzter_status_json:
            return                                        # nur bei Änderung
        await self._frage({"type": f"joamy_{BAUSTEIN}/store/patch", "scope": "global",
                           "data": {"status": status}})
        self._letzter_status_json = als_json

    async def _zustaende(self) -> dict:
        staaten = await self._frage({"type": "get_states"}, timeout=30)
        return {s["entity_id"]: s for s in staaten or [] if isinstance(s, dict) and s.get("entity_id")}

    async def _schalte(self, entity: str, an: bool) -> bool:
        domain = entity.split(".")[0]
        if domain not in SCHALTBARE_DOMAINS:
            return False
        dienst = "turn_on" if an else "turn_off"
        await self._frage({"type": "call_service", "domain": "homeassistant", "service": dienst,
                           "service_data": {"entity_id": entity}})
        return True

    def _bedingung_ok(self, uhr: dict, staaten: dict) -> tuple[bool, str]:
        """Anwesenheit — neutral, wenn keine person.* existiert (JoAmy-Regel)."""
        wunsch = ((uhr.get("conditions") or {}).get("presence")) or "any"
        if wunsch not in ("anyone_home", "nobody_home"):
            return True, ""
        personen = [s for eid, s in staaten.items() if eid.startswith("person.")]
        if not personen:
            return True, ""                              # neutral
        jemand = any(p.get("state") == "home" for p in personen)
        if wunsch == "anyone_home" and not jemand:
            return False, "niemand zu Hause"
        if wunsch == "nobody_home" and jemand:
            return False, "jemand zu Hause"
        return True, ""

    async def _schalte_mit_retry(self, entity: str, an: bool, staaten: dict) -> tuple[bool, str]:
        for versuch, warte in enumerate((0,) + RETRY_ABSTAENDE_S):
            if warte:
                await asyncio.sleep(warte)
                staaten = await self._zustaende()
            st = staaten.get(entity)
            if st is None:
                grund = "Gerät nicht mehr vorhanden"
                continue
            if st.get("state") in ("unavailable", "unknown"):
                grund = "Gerät nicht erreichbar"
                continue
            try:
                await self._schalte(entity, an)
                return True, ""
            except Exception as e:
                grund = f"Dienst fehlgeschlagen: {e}"
        return False, grund

    # ---------- Quick-Timer ----------
    async def _timer_verarbeiten(self, wuensche: list, jetzt_utc: datetime, staaten: dict) -> bool:
        """Karten-Wünsche (start/plus5/abbruch) in autoritative Timer überführen."""
        geaendert = False
        for w in wuensche or []:
            if not isinstance(w, dict):
                continue
            aktion = w.get("aktion") or "start"
            if aktion == "start" and w.get("target"):
                dauer = max(30, int(w.get("dauerSec") or 0))
                # pro Gerät max. EIN Timer — neuer ersetzt alten (Karte fragt vorher)
                self.timer = [t for t in self.timer if t.get("target") != w["target"]]
                self.timer.append({
                    "id": w.get("id") or ("t_" + uuid.uuid4().hex[:10]),
                    "target": w["target"],
                    "startedAt": jetzt_utc.isoformat(),
                    "endsAt": (jetzt_utc + timedelta(seconds=dauer)).isoformat(),
                    "totalDurationSec": dauer,
                    "endAction": w.get("endAction") or "turn_off",
                })
                if w.get("sofortEin"):
                    await self._schalte_mit_retry(w["target"], True, staaten)
                geaendert = True
            elif aktion == "plus5":
                for t in self.timer:
                    if t.get("id") == w.get("id"):
                        t["endsAt"] = (datetime.fromisoformat(t["endsAt"]) + timedelta(minutes=5)).isoformat()
                        t["totalDurationSec"] = int(t.get("totalDurationSec") or 0) + 300
                        geaendert = True
            elif aktion == "abbruch":
                vorher = len(self.timer)
                self.timer = [t for t in self.timer if t.get("id") != w.get("id")]
                geaendert = geaendert or len(self.timer) != vorher
        return geaendert

    async def _timer_ablauf(self, jetzt_utc: datetime, staaten: dict) -> bool:
        """Abgelaufene Timer (auch in Downtime abgelaufene): Endaktion ausführen."""
        geaendert = False
        rest = []
        for t in self.timer:
            try:
                ende = datetime.fromisoformat(t["endsAt"])
            except Exception:
                geaendert = True
                continue
            if jetzt_utc >= ende:
                an = (t.get("endAction") == "turn_on")
                ok, grund = await self._schalte_mit_retry(t["target"], an, staaten)
                LOG.info("Zeitschaltuhr: Timer %s → %s (%s)", t.get("id"),
                         "ein" if an else "aus", "ok" if ok else grund)
                geaendert = True
            else:
                rest.append(t)
        self.timer = rest
        return geaendert

    # ---------- Hauptschleife ----------
    async def laufe(self) -> None:
        self._data_lesen()
        LOG.info("Zeitschaltuhr-Engine startet (persistente Ereignisse: %d, Timer: %d).",
                 len(self.geschaltet), len(self.timer))
        erst_lauf = True
        while True:
            if self.ws is None or self.ws.closed:
                if not await self._verbinden():
                    await asyncio.sleep(10)
                    continue
                erst_lauf = True                         # nach Reconnect: Reconciliation
            try:
                naechste = await self._tick(erst_lauf)
                erst_lauf = False
            except Exception:
                LOG.exception("Zeitschaltuhr-Tick fehlgeschlagen — weiter")
                naechste = TICK_MAX_S
            try:
                await asyncio.wait_for(self._weck.wait(), min(TICK_MAX_S, max(1, naechste)))
            except asyncio.TimeoutError:
                pass
            self._weck.clear()

    async def _tick(self, reconciliation: bool) -> float:
        """Ein Durchlauf; Rückgabe = Sekunden bis zum nächsten interessanten Ereignis."""
        jetzt_utc = self.zeit_quelle()
        g = await self._store()
        uhren = [u for u in (g.get("uhren") or []) if isinstance(u, dict)]
        staaten = await self._zustaende()
        sonne = (staaten.get("sun.sun") or {}).get("attributes") or {}
        jetzt = zs_lokalzeit(jetzt_utc, self.tz)
        dirty = False

        # 1) Timer: Wünsche der Karte übernehmen, Abläufe ausführen
        wuensche = g.get("timer_wunsch") or []
        if wuensche:
            dirty |= await self._timer_verarbeiten(wuensche, jetzt_utc, staaten)
            await self._frage({"type": f"joamy_{BAUSTEIN}/store/patch", "scope": "global",
                               "data": {"timer_wunsch": []}})
        dirty |= await self._timer_ablauf(jetzt_utc, staaten)

        # 2) Reconciliation nach (Neu-)Start: Soll-Zustand herstellen
        status_uhren: dict = {}
        if reconciliation:
            for uhr in uhren:
                soll = zs_soll_zustand(uhr, jetzt, sonne, self.tz)
                if soll is None:
                    continue
                if soll and not self._bedingung_ok(uhr, staaten)[0]:
                    continue                              # EIN bleibt bedingungspflichtig
                ziel = uhr.get("target") or ""
                ist = (staaten.get(ziel) or {}).get("state")
                if ist in ("on", "off") and (ist == "on") != soll:
                    ok, grund = await self._schalte_mit_retry(ziel, soll, staaten)
                    LOG.info("Zeitschaltuhr: Reconciliation %s → %s (%s)", ziel,
                             "ein" if soll else "aus", "ok" if ok else grund)

        # 3) Fällige Schaltungen
        for uhr in uhren:
            if not uhr.get("enabled", True):
                status_uhren[uhr.get("id")] = {"naechster": None, "pausiert": True}
                continue
            for art, soll_zeit, schluessel in zs_faellig(uhr, jetzt, sonne, self.tz, self.geschaltet):
                self.geschaltet[schluessel] = jetzt_utc.timestamp()
                dirty = True
                if art == "ein":
                    ok_b, grund_b = self._bedingung_ok(uhr, staaten)
                    if not ok_b:
                        LOG.info("Zeitschaltuhr: %s EIN übersprungen (%s)", uhr.get("name"), grund_b)
                        status_uhren.setdefault(uhr.get("id"), {})["zuletzt"] = {
                            "wann": jetzt_utc.isoformat(), "ok": True,
                            "grund": f"übersprungen: {grund_b}"}
                        continue
                ok, grund = await self._schalte_mit_retry(uhr.get("target") or "", art == "ein", staaten)
                status_uhren.setdefault(uhr.get("id"), {})["zuletzt"] = {
                    "wann": jetzt_utc.isoformat(), "ok": ok, "grund": grund}
                LOG.info("Zeitschaltuhr: %s → %s (%s)", uhr.get("name") or uhr.get("target"),
                         art, "ok" if ok else grund)

        # 4) Alte Ereignis-Schlüssel ausmisten (48 h) + /data spiegeln
        limit = jetzt_utc.timestamp() - 2 * 86400
        alt = [k for k, v in self.geschaltet.items() if v < limit]
        for k in alt:
            del self.geschaltet[k]
        if dirty or alt:
            self._data_schreiben()

        # 5) Status für die Karte + Schlafdauer bis zum nächsten Ereignis
        naechste_s = float(TICK_MAX_S)
        for uhr in uhren:
            eintrag = status_uhren.setdefault(uhr.get("id"), {})
            ziel = uhr.get("target") or ""
            if ziel not in staaten:
                eintrag["geraet_fehlt"] = True
            n = zs_naechstes_ereignis(uhr, jetzt, sonne, self.tz)
            if n:
                eintrag["naechster"] = {"was": n[0], "wann": n[1].isoformat()}
                naechste_s = min(naechste_s, max(1.0, (n[1] - jetzt).total_seconds()))
            else:
                eintrag.setdefault("naechster", None)
        for t in self.timer:
            try:
                naechste_s = min(naechste_s, max(1.0,
                    (datetime.fromisoformat(t["endsAt"]) - jetzt_utc).total_seconds()))
            except Exception:
                pass
        await self._status_schreiben({
            "uhren": status_uhren,
            "timer": self.timer,
            "engine": {"lebt": True, "tick": jetzt_utc.isoformat()},
        })
        return naechste_s
