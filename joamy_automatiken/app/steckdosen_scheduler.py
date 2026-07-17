"""Steckdosen-Scheduler — Zeitpläne mit Bedingungen (JoAmy-Baustein).

Das JoAmy-Dashboard schreibt Schedules in `sensor.steckdosen_schedules.attributes.entries`.
Dieser Baustein liest sie pro Tick, prüft Bedingungen (Tagmodus / Nachtmodus / Anwesenheit)
und schaltet `switch.*` via Service-Call (turn_on / turn_off). Verhalten wie die Vorlage:
ein Schedule feuert MAX 1x pro Tag, bei Bedingungs-Mismatch wird NICHT erneut versucht
(kein sliding window).

Schedule-Eintrag (Format identisch zur Vorlage, trigger-Feld + Event-Trigger):
    {
      "id": "<uuid>",
      "switch_eid": "switch.kueche_steckdose",
      "label": "Frühstück" (optional),
      "trigger": {
        "type": "time" | "tagmodus_on" | "tagmodus_off"
              | "nachtmodus_on" | "nachtmodus_off"
              | "home_arrive" | "all_away",
        "time": "07:00",            # nur bei type=time
        "days": [0,1,2,3,4,5,6],    # nur bei type=time (0=Mo..6=So)
      },
      "action": "turn_on" | "turn_off",
      "conditions": {
        "tagmodus": "on"|"off"|"any",
        "nachtmodus": "on"|"off"|"any",
        "anyone_home": "yes"|"no"|"any"
      },
      "enabled": true
    }

Migration: alte Schedules ohne `trigger`-Feld (mit `time` + `days` direkt) werden
beim Lesen zu `trigger={type:'time', time, days}` normalisiert. Kein Datenverlust.

Event-Trigger-Edges werden pro Tick aus dem letzten Snapshot (`prev_states`) gegen
die aktuellen States im HaClient-Cache berechnet — siehe `compute_event_edges()`.
Ein Listener auf tagmodus/nachtmodus/person.* weckt den Tick sofort, damit Kanten
ohne Poll-Verzögerung verarbeitet werden. Baustein-Start adoptiert die aktuellen
States ohne zu feuern (None → Wert ist KEINE Kante).

Anwesenheit ist generisch: `anyone_home` = irgendeine `person.*`-Entity == 'home'.
Fehlende JoAmy-Helper (input_boolean.tagmodus/nachtmodus) oder fehlende person.*-
Entities beim Kunden ⇒ die betroffene Bedingung wird neutral behandelt (kein Block),
Kanten dafür feuern schlicht nie.

Persistenz (2 Schichten): (1) State-Datei unter /data — das Pendant zur
state.json der Vorlage; überlebt auch den Host-Reboot, bei dem HA-Restart UND
Add-on-Restart zusammen Sensor + RAM wegputzen — und (2) der Status-Sensor
`sensor.joamy_steckdosen_status` als Anzeige + Mirror. Beide tragen `last_fired`
(pro Schedule-ID epoch-s) + `schedules_persisted` (Mirror falls ein HA-Restart
sensor.steckdosen_schedules wegputzt — wird zurückgeschrieben) + `prev_states`
(Kanten-Erkennung über Baustein-Restart hinweg). Beim Start: erst Datei lesen,
Fallback ha.attr() vom Status-Sensor. NUR-BEI-ÄNDERUNG: geschrieben wird nur,
wenn sich der Inhalt tatsächlich geändert hat (oder der Sensor nach einem
HA-Restart fehlt).
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime

LOG = logging.getLogger("joamy.steckdosen")

TICK_SEC = 30
FIRE_WINDOW_SEC = 60   # Schedule darf bis 60s nach Soll-Zeit feuern
SENSOR_ID = "sensor.steckdosen_schedules"
STATUS_SENSOR = "sensor.joamy_steckdosen_status"
# /data ist der persistente Add-on-Speicher (überlebt Host-Reboot) —
# JOAMY_DATA nur als Override für lokale Entwicklung.
DATEI_STATE = os.path.join(os.environ.get("JOAMY_DATA", "/data"),
                           "steckdosen_state.json")

# Condition-Quellen — JoAmy-Helper, legt joamy-helpers.yaml beim Kunden an.
TAGMODUS = "input_boolean.tagmodus"
NACHTMODUS = "input_boolean.nachtmodus"

EVENT_TRIGGER_TYPES = {
    "tagmodus_on", "tagmodus_off",
    "nachtmodus_on", "nachtmodus_off",
    "home_arrive", "all_away",
}


def normalize_schedule(sch: dict) -> dict:
    """Migration alter Schedules ohne trigger-Feld. Idempotent."""
    if isinstance(sch.get("trigger"), dict) and sch["trigger"].get("type"):
        return sch
    sch["trigger"] = {
        "type": "time",
        "time": sch.get("time", "20:00"),
        "days": sch.get("days") or [0, 1, 2, 3, 4, 5, 6],
    }
    return sch


def is_time_due(schedule: dict, now: datetime) -> bool:
    """Prüft NUR die Zeit-Komponente (HH:MM + Wochentag im Fire-Window)."""
    if not schedule.get("enabled"):
        return False
    tr = schedule.get("trigger") or {}
    days = tr.get("days") or schedule.get("days") or []
    if days and now.weekday() not in days:
        return False
    time_str = tr.get("time") or schedule.get("time") or ""
    try:
        hh, mm = [int(x) for x in time_str.split(":")[:2]]
    except Exception:
        return False
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        # Ungültige Zeit (z. B. "25:00") würde now.replace() mit ValueError
        # crashen lassen und damit JEDEN Tick abbrechen — defensiv: nie fällig.
        return False
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff = (now - target).total_seconds()
    return 0 <= diff <= FIRE_WINDOW_SEC


def compute_event_edges(prev: dict, cur: dict) -> dict[str, bool]:
    """Berechnet die Event-Kanten aus prev/cur Snapshot.

    prev/cur sind Dicts mit Keys: 'tagmodus' (str on/off/None), 'nachtmodus'
    (str on/off/None), 'anyone_home' (bool/None).

    Eine Kante ist nur dann True, wenn beide prev und cur einen definierten
    Wert haben und sich der Wert in die erwartete Richtung geändert hat. Beim
    ersten Tick (prev=None) feuert KEINE Kante — wir adoptieren den State.
    """
    edges: dict[str, bool] = {k: False for k in EVENT_TRIGGER_TYPES}
    pt, ct = prev.get("tagmodus"), cur.get("tagmodus")
    if pt in ("on", "off") and ct in ("on", "off") and pt != ct:
        edges["tagmodus_on"]  = (ct == "on")
        edges["tagmodus_off"] = (ct == "off")
    pn, cn = prev.get("nachtmodus"), cur.get("nachtmodus")
    if pn in ("on", "off") and cn in ("on", "off") and pn != cn:
        edges["nachtmodus_on"]  = (cn == "on")
        edges["nachtmodus_off"] = (cn == "off")
    pa, ca = prev.get("anyone_home"), cur.get("anyone_home")
    if isinstance(pa, bool) and isinstance(ca, bool) and pa != ca:
        edges["home_arrive"] = (pa is False and ca is True)
        edges["all_away"]    = (pa is True and ca is False)
    return edges


def is_trigger_due(schedule: dict, now: datetime, edges: dict[str, bool]) -> bool:
    """Dispatcher: Zeit-Trigger → is_time_due, Event-Trigger → edges-Lookup."""
    if not schedule.get("enabled"):
        return False
    tr = schedule.get("trigger") or {}
    ttype = tr.get("type") or "time"
    if ttype == "time":
        return is_time_due(schedule, now)
    if ttype in EVENT_TRIGGER_TYPES:
        return bool(edges.get(ttype))
    return False


def already_fired_today(sid: str, last_fired: dict, now: datetime) -> bool:
    ts = last_fired.get(sid, 0)
    if not ts:
        return False
    try:
        # fromtimestamp MIT im try: ein korrupter Riesen-Timestamp (z. B.
        # manipulierte Sensor-Attribute) darf den Tick nicht crashen.
        last_dt = datetime.fromtimestamp(float(ts))
    except Exception:
        return False
    return last_dt.date() == now.date()


class SteckdosenScheduler:
    def __init__(self, ha, cfg):
        self.ha = ha
        self.cfg = cfg or {}
        self.last_fired: dict[str, float] = {}
        self.schedules_persisted: list[dict] = []
        self.prev_states: dict = {}
        self._weck = asyncio.Event()       # Listener weckt den Tick bei Event-Kanten
        self._letzter_status: str | None = None  # zuletzt geschriebener Status (Diff-Basis)

    # ---- Anwesenheit: generisch über ALLE person.*-Entities des Kunden ----
    def _hat_personen(self) -> bool:
        return any(eid.startswith("person.") for eid in self.ha.states)

    def _anyone_home(self) -> bool:
        """True wenn mindestens eine person.*.state == 'home'."""
        for eid, s in self.ha.states.items():
            if eid.startswith("person.") and (s or {}).get("state") == "home":
                return True
        return False

    # ---- Event-Trigger: state_changed weckt den Tick sofort ----
    async def _on_state(self, eid, neu, alt):
        if eid in (TAGMODUS, NACHTMODUS) or eid.startswith("person."):
            # Nur echte State-Wechsel wecken — person.* feuert state_changed
            # auch bei reinen GPS-Attribut-Updates (sonst Dauer-Ticks).
            if ((neu or {}).get("state")) != ((alt or {}).get("state")):
                self._weck.set()

    # ---- Persistenz: State-Datei in /data + Status-Sensor als Fallback ----
    def _lese_persistenz(self) -> None:
        """Beim Start zurücklesen: primär aus der State-Datei in /data (die
        überlebt auch den Host-Reboot, bei dem HA UND Add-on zusammen neu
        starten — REST-Sensoren sind dann weg), sekundär aus dem Status-Sensor
        (Migration von älteren Ständen / /data unlesbar)."""
        daten: dict = {}
        try:
            with open(DATEI_STATE, encoding="utf-8") as f:
                daten = json.load(f) or {}
        except FileNotFoundError:
            pass
        except Exception:
            LOG.exception("State-Datei %s unlesbar — Fallback Status-Sensor",
                          DATEI_STATE)
        if not daten and STATUS_SENSOR in self.ha.states:
            daten = {
                "last_fired": self.ha.attr(STATUS_SENSOR, "last_fired", {}),
                "schedules_persisted":
                    self.ha.attr(STATUS_SENSOR, "schedules_persisted", []),
                "prev_states": self.ha.attr(STATUS_SENSOR, "prev_states", {}),
            }
        self.last_fired = dict(daten.get("last_fired") or {})
        self.schedules_persisted = list(daten.get("schedules_persisted") or [])
        self.prev_states = dict(daten.get("prev_states") or {})

    def _schreibe_datei_sync(self, kern: dict) -> None:
        """Atomarer State-Datei-Write (tmp + os.replace, wie die Vorlage).
        Läuft via asyncio.to_thread — nie direkt im Event-Loop aufrufen."""
        try:
            os.makedirs(os.path.dirname(DATEI_STATE), exist_ok=True)
            tmp = DATEI_STATE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(kern, f, default=str)
            os.replace(tmp, DATEI_STATE)
        except Exception as e:
            LOG.warning("State-Datei schreiben fehlgeschlagen: %s", e)

    async def _schreibe_status(self, schedules: list[dict]) -> None:
        """State-Datei (/data) + Status-Sensor (Anzeige/Mirror) schreiben.
        NUR-BEI-ÄNDERUNG: identischer Inhalt wird nicht erneut geschrieben —
        außer der Sensor fehlt (HA-Restart hat ihn weggeputzt), dann neu."""
        enabled = sum(1 for s in schedules if s.get("enabled"))
        kern = {
            "schedules_total": len(schedules),
            "schedules_enabled": enabled,
            "last_fired": dict(self.last_fired),
            "prev_states": dict(self.prev_states),
            "schedules_persisted": list(self.schedules_persisted),
        }
        vergleich = json.dumps(kern, sort_keys=True, default=str)
        if vergleich == self._letzter_status and STATUS_SENSOR in self.ha.states:
            return
        attrs = {
            **kern,
            "last_check": datetime.now().isoformat(timespec="seconds"),
            "friendly_name": "JoAmy · Steckdosen-Zeitpläne",
            "icon": "mdi:power-socket-eu",
        }
        # set_state_sync (urllib) und Datei-IO sind blocking → in Threads
        # auslagern, damit der Tick den Event-Loop nie anhält. Datei zuerst:
        # sie ist die verlässlichere Schicht (überlebt Host-Reboot).
        await asyncio.to_thread(self._schreibe_datei_sync, kern)
        await asyncio.to_thread(
            self.ha.set_state_sync, STATUS_SENSOR, f"{enabled} aktiv", attrs)
        self._letzter_status = vergleich

    async def _restore_schedules(self) -> list[dict]:
        """HA-Restart hat sensor.steckdosen_schedules weggeputzt →
        aus dem Mirror zurückschreiben (wie restore_to_ha der Vorlage)."""
        await asyncio.to_thread(
            self.ha.set_state_sync, SENSOR_ID, str(len(self.schedules_persisted)), {
                "entries": self.schedules_persisted,
                "friendly_name": "Steckdosen · Zeitpläne",
                "icon": "mdi:clock-time-five-outline",
            })
        LOG.warning("RESTORE: %d Schedules wiederhergestellt",
                    len(self.schedules_persisted))
        return list(self.schedules_persisted)

    # ---- Bedingungen ----
    def _pruefe_bedingungen(self, cond: dict) -> tuple[bool, str]:
        """Prüft die User-Conditions gegen den Live-State-Cache.
        Fehlende Helper/Entities beim Kunden ⇒ Bedingung neutral (JoAmy-Regel).
        Returns (passed, reason_string)."""
        if not cond:
            return True, "keine Bedingungen"
        # Tagmodus
        tm_want = cond.get("tagmodus", "any")
        if tm_want in ("on", "off"):
            tm = self.ha.state(TAGMODUS)
            if tm is None:
                pass  # Helper fehlt → neutral, nicht blockieren
            elif tm != tm_want:
                return False, f"tagmodus={tm} (erwartet {tm_want})"
        # Nachtmodus
        nm_want = cond.get("nachtmodus", "any")
        if nm_want in ("on", "off"):
            nm = self.ha.state(NACHTMODUS)
            if nm is None:
                pass  # Helper fehlt → neutral
            elif nm != nm_want:
                return False, f"nachtmodus={nm} (erwartet {nm_want})"
        # anyone_home (yes / no / any)
        ah_want = cond.get("anyone_home", "any")
        if ah_want in ("yes", "no"):
            if not self._hat_personen():
                pass  # keine person.*-Entities → neutral
            else:
                anyone = self._anyone_home()
                if ah_want == "yes" and not anyone:
                    return False, "niemand zuhause (erwartet ja)"
                if ah_want == "no" and anyone:
                    return False, "jemand zuhause (erwartet nein)"
        return True, "ok"

    # ---- Hauptschleife ----
    async def laufe(self):
        await self.ha.bereit.wait()
        self._lese_persistenz()
        self.ha.listeners.append(self._on_state)
        LOG.info("Steckdosen-Scheduler gestartet — last_fired: %d, persisted: %d, "
                 "prev_states: %s",
                 len(self.last_fired), len(self.schedules_persisted),
                 self.prev_states or "leer")
        while True:
            try:
                await self._tick()
            except Exception:
                # EIN Fehler darf den Baustein nie beenden.
                LOG.exception("Tick fehlgeschlagen — weiter")
            # Warten bis Weckruf (Event-Kante) oder regulärer Tick.
            try:
                await asyncio.wait_for(self._weck.wait(), TICK_SEC)
            except asyncio.TimeoutError:
                pass
            self._weck.clear()

    async def _tick(self):
        ha = self.ha
        # 0) WS getrennt → State-Cache potenziell stale. Entscheidungen auf
        # stalen Daten (v. a. der Nur-bei-Änderung-Vergleich) könnten Schedules
        # fälschlich als „Ziel schon erreicht" abhaken, ohne dass je ein Call
        # rausging. Tick auslassen — die Vorlage tat bei HA-down auch nichts.
        if not ha.bereit.is_set():
            return
        # 1) Schedules lesen — Sensor weg (HA-Restart) → aus Mirror restaurieren.
        if SENSOR_ID in ha.states:
            schedules = list(ha.attr(SENSOR_ID, "entries", []) or [])
            self.schedules_persisted = list(schedules)
        elif self.schedules_persisted:
            schedules = await self._restore_schedules()
        else:
            schedules = []

        # Migration: alle Schedules normalisieren (trigger-Feld einsetzen falls
        # Legacy). Mutiert in-place, damit auch schedules_persisted die neue
        # Form behält. Nicht-Dict-Müll in entries wird übersprungen (würde
        # sonst jeden Tick mit AttributeError abbrechen); der Mirror behält
        # die Roh-Einträge trotzdem — kein Datenverlust.
        schedules = [normalize_schedule(s) for s in schedules
                     if isinstance(s, dict)]

        # 2) Snapshot der Event-Trigger-relevanten Entities + Edges berechnen.
        # Alles kommt aus dem HaClient-Cache (kein HTTP-Poll pro Schedule).
        # Ohne Event-Schedules sparen wir uns den Snapshot komplett.
        has_event_triggers = any(
            (s.get("trigger") or {}).get("type") in EVENT_TRIGGER_TYPES
            for s in schedules
        )
        if has_event_triggers:
            cur_states = {
                "tagmodus": ha.state(TAGMODUS),
                "nachtmodus": ha.state(NACHTMODUS),
                # Ohne person.*-Entities bleibt anyone_home undefiniert (None)
                # → home_arrive/all_away feuern nie (neutral, JoAmy-Regel).
                "anyone_home": self._anyone_home() if self._hat_personen() else None,
            }
            edges = compute_event_edges(self.prev_states, cur_states)
            if any(edges.values()):
                LOG.info("event-edges: %s (prev=%s cur=%s)",
                         {k: v for k, v in edges.items() if v},
                         self.prev_states, cur_states)
            # prev_states fortschreiben — None-Werte (HA-Glitch / Restart)
            # überschreiben prev NICHT, sonst geht die Kanten-Erkennung
            # nach einem kurzen unavailable-Fenster verloren.
            for k, v in cur_states.items():
                if v is not None:
                    self.prev_states[k] = v
        else:
            edges = {k: False for k in EVENT_TRIGGER_TYPES}

        # 3) Fällige Schedules feuern (max 1x pro Tag, Bedingungen live geprüft).
        now = datetime.now()
        for sch in schedules:
            sid = sch.get("id")
            if not sid:
                continue
            if not is_trigger_due(sch, now, edges):
                continue
            if already_fired_today(sid, self.last_fired, now):
                continue
            ok_cond, why = self._pruefe_bedingungen(sch.get("conditions") or {})
            tr = sch.get("trigger") or {}
            ttype = tr.get("type", "time")
            trig_label = tr.get("time", "") if ttype == "time" else ttype
            if not ok_cond:
                # User-Spec: NICHT als gefeuert markieren, einfach skip.
                # Bei Event-Triggern feuert die Kante diesmal eh nur 1× —
                # ein erneuter Versuch ist nur bei Tagesgrenzen-Wechsel
                # möglich (kein Wiederholversuch innerhalb der Kante).
                LOG.info("Schedule '%s' (%s %s) übersprungen — %s",
                         sid, trig_label, sch.get("action"), why)
                continue
            switch_eid = sch.get("switch_eid")
            action = sch.get("action")
            if switch_eid and action in ("turn_on", "turn_off"):
                # NUR-BEI-ÄNDERUNG: Ist == Soll → kein Service-Call. Der
                # Schedule gilt trotzdem als gefeuert (Ziel-Zustand erreicht).
                soll = "on" if action == "turn_on" else "off"
                if ha.state(switch_eid) == soll:
                    self.last_fired[sid] = now.timestamp()
                    LOG.info("Schedule '%s' (%s): %s ist bereits %s — kein Call",
                             sid, trig_label, switch_eid, soll)
                    continue
                try:
                    await ha.call("switch", action, {"entity_id": switch_eid})
                except Exception as e:
                    LOG.warning("switch.%s %s fehlgeschlagen: %s",
                                action, switch_eid, e)
                    continue  # nicht als gefeuert markieren → Fenster/Tag erlaubt Retry
                self.last_fired[sid] = now.timestamp()
                LOG.info("Schedule '%s' (%s) → switch.%s %s",
                         sid, trig_label, action, switch_eid)

        # 4) Status-Sensor aktualisieren (= Persistenz der last_fired/prev_states).
        await self._schreibe_status(schedules)
