"""JoAmy Automatiken — Baustein „Licht-Automatik" (HelligkeitsRegler).

Generalisierte, bewusst reduzierte Portierung von Joachims
helligkeit_regler/run.py (3746 Zeilen). Übernommen wurde die KERN-Mechanik:

  (a) Präsenz → Licht-an mit Lux-Hysterese (an unter `lux_an_unter`,
      aus erst über `lux_aus_ueber`, dazwischen letzte Entscheidung halten)
  (b) Abschalt-Verzögerung `aus_nach_s` nach Präsenz-Ende (Pending-Timer,
      Präsenz-Rückkehr bricht ihn ab)
  (c) Manual-Override: schaltet der Bewohner von Hand, pausiert die
      Automatik für die Zone (`sperre_min`, Default 30 min). Eigene
      Service-Calls werden 6 s lang NICHT als fremd gewertet — richtungs-
      genau: nur Events, deren NEUER Zustand einem eigenen Call der letzten
      6 s entspricht, gelten als spätes Eigen-Echo. Ein on/off-Wechsel
      ENTGEGEN allem, was der Daemon zuletzt wollte, ist IMMER Bedienung
      (Vorlage-Fix 2026-05-09: sonst verschluckt das Fenster „User schaltet
      sofort wieder aus" und die Automatik kämpft endlos gegen den User).
      Zusätzlich gilt „Zustand == Erwartung" immer als Eigen-Echo, auch
      nach Ablauf des Fensters (langsame Aktoren).
  (d) OVERRIDE-LIFECYCLE (Pflicht): Flanke off→on von input_boolean.tagmodus
      oder input_boolean.nachtmodus löscht ALLE Sperren. Nachtmodus-Flanke
      schaltet zusätzlich alle zugeordneten Lichter aus; solange Nachtmodus
      aktiv ist, schaltet die Automatik nichts EIN. Fehlt ein Helper beim
      Kunden, wird die Bedingung neutral behandelt (kein Nachtmodus,
      keine Flanken).
  (e) 90-s-Grace nach Start UND nach jedem WS-Reconnect: in dem Fenster
      werden Licht-Events NICHT als manuelle Eingriffe gewertet
      (HA-Restart-Replay-Falle der Vorlage — der Recorder spielt beim
      Neustart alle States mit frischem last_updated neu ein).

BEWUSST NICHT portiert: Szenen/Cluster, Wandtaster, Sun-Curve, Nachtlicht-
Sonderpfade, Lüftungsmodus, Cross-Room-Aggregation, die _config/_overrides/
_presence_stats-Sensor-Familie. Statt vieler Sensoren gibt es genau EINEN
Status-Sensor `sensor.joamy_licht_status` mit attributes.zonen — er dient
gleichzeitig als Restart-Persistenz für die Override-Sperren.

Konfiguration (joamy-automatiken.json → "helligkeit"):
  { "aktiv": true,
    "sperre_min": 30,                       # optional, global
    "zonen": [ { "id": "flur", "name": "Flur",
                 "lights":   ["light.flur"],
                 "presence": ["binary_sensor.flur_motion"],
                 "lux": "sensor.flur_lux" | null,
                 "lux_an_unter": 30,
                 "aus_nach_s": 180 } ] }
"""
import asyncio
import logging
import time

LOG = logging.getLogger("joamy.helligkeit")

STATUS_SENSOR = "sensor.joamy_licht_status"
TAGMODUS_HELPER = "input_boolean.tagmodus"       # legt joamy-helpers.yaml an
NACHTMODUS_HELPER = "input_boolean.nachtmodus"   # legt joamy-helpers.yaml an

# Zeitfenster nach eigenem Service-Call, in dem State-Änderungen desselben
# Lichts als Eigen-Echo gelten (Vorlage: Self-Override-Bug — doppeltes
# turn_on innerhalb 6 s wurde als „manuell" gewertet).
EIGEN_FENSTER_MS = 6_000

# Grace nach Start/Reconnect: HA spielt nach einem Neustart alle States in
# Wellen über ~30-60 s neu ein (Recorder-Replay). Ohne dieses Fenster würde
# jeder Replay-Event als Handbedienung gewertet → False-Lock aller Zonen.
RECONNECT_GRACE_MS = 90_000

# Anti-Spam wie in der Vorlage: max. 1 Befehl pro Licht / 5 s. Schützt gegen
# Fire-Loops solange der Aktor den neuen Zustand noch nicht zurückgemeldet hat.
ACTION_COOLDOWN_MS = 5_000

TICK_S = 30                # Sicherheits-Tick (Events treiben zusätzlich)
SPERRE_MIN_DEFAULT = 30    # Override-Sperrdauer wenn nicht konfiguriert
LUX_AUS_FAKTOR = 2.0       # lux_aus_ueber-Default = Faktor × lux_an_unter


def jetzt_ms() -> int:
    return int(time.time() * 1000)


class HelligkeitsRegler:
    """Präsenzgesteuerte Licht-Automatik pro Zone, event-getrieben mit
    30-s-Sicherheits-Tick. Ein Fehler in einem Tick beendet den Baustein nie."""

    def __init__(self, ha, cfg):
        self.ha = ha
        sperre_global = self._int(cfg.get("sperre_min"), SPERRE_MIN_DEFAULT)

        # --- Zonen-Konfiguration normalisieren (Wizard kann JSON-null liefern:
        # Schlüssel existiert mit Wert None → .get(k, default) greift NICHT,
        # deshalb die defensiven _int/_float-Helfer wie in der Vorlage) ---
        self.zonen = []
        for z in (cfg.get("zonen") or []):
            zid = str(z.get("id") or "").strip()
            lights = [l for l in (z.get("lights") or []) if l]
            presence = [p for p in (z.get("presence") or []) if p]
            if not zid or not lights:
                LOG.warning("Zone ohne id/lights übersprungen: %r", z)
                continue
            if not presence:
                # Ohne Präsenz-Sensor würde die Zone dauerhaft „aus" wollen
                # und dem Kunden brennende Lichter abschalten → lieber inaktiv.
                LOG.warning("Zone %s hat keine presence-Sensoren — inaktiv.", zid)
                continue
            an_unter = self._float(z.get("lux_an_unter"), 30.0)
            self.zonen.append({
                "id": zid,
                "name": str(z.get("name") or zid),
                "lights": lights,
                "presence": presence,
                "lux": z.get("lux") or None,
                "lux_an_unter": an_unter,
                # Hysterese-Oberkante: optional konfigurierbar, sonst Faktor.
                "lux_aus_ueber": self._float(z.get("lux_aus_ueber"),
                                             an_unter * LUX_AUS_FAKTOR),
                "aus_nach_s": self._int(z.get("aus_nach_s"), 180),
                "sperre_min": self._int(z.get("sperre_min"), sperre_global),
            })

        # --- Laufzeit-Zustand pro Zone ---
        # will: letzter durchgesetzter Wunsch ("an"/"aus"/None=unbekannt)
        # aus_pending_ms: Start des Abschalt-Timers (None = kein Pending)
        # hyst_an: letzte Lux-Hysterese-Entscheidung (Zwischenband hält sie)
        self._zust = {z["id"]: {"will": None, "aus_pending_ms": None,
                                "hyst_an": False} for z in self.zonen}

        # Override-Sperren: {zone_id: {"bis_ms": int, "grund": str}} —
        # werden im Status-Sensor gespiegelt und beim Start zurückgelesen.
        self._overrides = {}

        # Eigen-Aktions-Tracking (Muster der Vorlage, reduziert):
        # _eigen[eid]   = {"on"/"off": ts} der letzten eigenen Calls PRO
        #                 RICHTUNG (6-s-Fenster, richtungs-genau — sonst
        #                 würde ein sofortiges Gegen-Schalten des Users
        #                 als Eigen-Echo verschluckt, s. _pruefe_manuell)
        # _erwartet[eid]= "on"/"off" das der Daemon zuletzt wollte (Echo-Check)
        self._eigen = {}
        self._erwartet = {}
        self._letzter_call = {}   # eid → ts (Action-Cooldown)

        # Entity-Landkarten für den Event-Listener
        self._licht_zu_zonen = {}
        self._relevante = {TAGMODUS_HELPER, NACHTMODUS_HELPER}
        for z in self.zonen:
            for l in z["lights"]:
                self._licht_zu_zonen.setdefault(l, []).append(z["id"])
            self._relevante.update(z["lights"])
            self._relevante.update(z["presence"])
            if z["lux"]:
                self._relevante.add(z["lux"])

        # Tag/Nacht-Flanken-Erkennung ("on"/"off"/None; None = Helper fehlt
        # oder noch nie gesehen → Bedingung neutral, keine Flanke)
        self._prev_tag = None
        self._prev_nacht = None

        self._grace_bis_ms = 0
        self._anstoss = asyncio.Event()   # Event-Trigger für den Tick
        self._letzter_status = None       # (state, attrs) des letzten Writes

    # ------------------------------------------------------------------
    # Defensive Konvertierung (JSON-null-Falle, siehe __init__)
    # ------------------------------------------------------------------
    @staticmethod
    def _int(v, default):
        try:
            return int(v) if v is not None else int(default)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _float(v, default):
        try:
            return float(v) if v is not None else float(default)
        except (TypeError, ValueError):
            return float(default)

    # ------------------------------------------------------------------
    # Hauptschleife
    # ------------------------------------------------------------------
    async def laufe(self):
        if not self.zonen:
            LOG.warning("Licht-Automatik ohne nutzbare Zonen — Baustein ruht.")
            return
        await self.ha.bereit.wait()

        # Startup-Grace (deckt zugleich den ersten Recorder-Replay ab)
        self._grace_bis_ms = jetzt_ms() + RECONNECT_GRACE_MS
        LOG.info("Start: %d Zone(n), %d s Override-Detection-Grace",
                 len(self.zonen), RECONNECT_GRACE_MS // 1000)

        self._lade_persistenz()
        self.ha.listeners.append(self._bei_event)
        asyncio.create_task(self._verbindungs_waechter())

        while True:
            try:
                await asyncio.wait_for(self._anstoss.wait(), timeout=TICK_S)
            except asyncio.TimeoutError:
                pass  # Sicherheits-Tick
            self._anstoss.clear()
            try:
                if self.ha.bereit.is_set():
                    await self._tick()
            except Exception:
                # EIN Fehler darf den Daemon nie beenden (Pflicht-Regel).
                LOG.exception("Tick-Fehler — nächster Tick läuft trotzdem")

    async def _verbindungs_waechter(self):
        """Erkennt WS-Reconnects (HA-Neustart!) über die bereit-Flanke und
        startet dann das 90-s-Grace-Fenster neu — State-Replay-Falle."""
        vorher = True  # laufe() hat auf bereit gewartet → aktuell verbunden
        while True:
            try:
                await asyncio.sleep(1)
                jetzt_bereit = self.ha.bereit.is_set()
                if jetzt_bereit and not vorher:
                    self._grace_bis_ms = jetzt_ms() + RECONNECT_GRACE_MS
                    # REST-gesetzte Sensoren überleben keinen Core-Restart —
                    # Nur-bei-Änderung-Cache invalidieren, damit der nächste
                    # Tick den Status-Sensor (inkl. Override-Persistenz!)
                    # garantiert neu schreibt. Sonst fehlt er bis zur
                    # nächsten zufälligen inhaltlichen Änderung.
                    self._letzter_status = None
                    LOG.info("WS-Reconnect erkannt — %d s Grace, Events gelten "
                             "solange nicht als Handbedienung",
                             RECONNECT_GRACE_MS // 1000)
                    self._anstoss.set()
                vorher = jetzt_bereit
            except Exception:
                LOG.exception("Verbindungs-Wächter-Fehler")

    # ------------------------------------------------------------------
    # Event-Listener (vom HaClient pro state_changed aufgerufen)
    # ------------------------------------------------------------------
    async def _bei_event(self, eid, neu, alt):
        try:
            if eid in self._licht_zu_zonen:
                self._pruefe_manuell(eid, neu, alt)
            if eid in self._relevante:
                self._anstoss.set()
        except Exception:
            LOG.exception("Event-Fehler %s", eid)

    def _pruefe_manuell(self, eid, neu, alt):
        """Manual-Override-Erkennung (reduziert auf on/off-Wechsel).

        Reihenfolge wie in der Vorlage:
          1. Grace-Fenster (Start/Reconnect) → nie als manuell werten
          2. Zustand == Erwartung → Eigen-Echo, skip (auch außerhalb 6 s —
             langsame Aktoren melden teils erst nach >6 s zurück)
          3. eigener Call IN DIESE RICHTUNG < 6 s her → spätes Eigen-Echo,
             skip (deckt die schnelle Befehls-Umkehr ab: aus@t0 + an@t2 →
             träger Aktor meldet „off" erst bei t3). Ein Wechsel entgegen
             ALLEN jüngsten eigenen Calls ist dagegen IMMER Bedienung —
             on/off wechselt nie spontan (Vorlage-Regel).
          4. sonst: Handbedienung → Zone(n) sperren
        """
        now = jetzt_ms()
        if now < self._grace_bis_ms:
            return  # Replay-Falle: Restart-Events sind keine Bedienung
        alt_s = (alt or {}).get("state")
        neu_s = (neu or {}).get("state")
        if alt_s not in ("on", "off") or neu_s not in ("on", "off"):
            return  # unavailable/unknown/Bootstrap → keine Aussage möglich
        if alt_s == neu_s:
            return  # nur Attribut-Änderung — in der reduzierten Fassung egal
        if neu_s == self._erwartet.get(eid):
            return  # Eigen-Echo: genau das wollte der Daemon
        if (now - self._eigen.get(eid, {}).get(neu_s, 0)) < EIGEN_FENSTER_MS:
            return  # eigener Call in DIESE Richtung vor <6 s → spätes Echo

        grund = "an→aus" if neu_s == "off" else "aus→an"
        for zid in self._licht_zu_zonen.get(eid, []):
            if zid in self._overrides:
                continue  # schon gesperrt — Sperre nicht neu starten (Vorlage)
            zone = next(z for z in self.zonen if z["id"] == zid)
            self._overrides[zid] = {
                "bis_ms": now + zone["sperre_min"] * 60_000,
                "grund": f"{eid} {grund}",
            }
            zz = self._zust[zid]
            zz["will"] = None          # nach Ablauf neutral neu bewerten
            zz["aus_pending_ms"] = None
            LOG.info("MANUELLER EINGRIFF: %s (%s) → Zone %s %d min gesperrt",
                     eid, grund, zid, zone["sperre_min"])
        # Erwartung verwerfen — sonst meldet derselbe Mismatch nochmal
        self._erwartet.pop(eid, None)
        self._anstoss.set()  # Status-Sensor zeitnah aktualisieren

    # ------------------------------------------------------------------
    # Tick: Modus-Flanken → Sperren-Ablauf → Zonen-Regelung → Status
    # ------------------------------------------------------------------
    async def _tick(self):
        now = jetzt_ms()

        # --- Tag/Nacht-Flanken (OVERRIDE-LIFECYCLE, Pflicht) ---
        # Fehlender Helper liefert None → keine Flanke, Nachtmodus neutral.
        tag = self.ha.state(TAGMODUS_HELPER)
        nacht = self.ha.state(NACHTMODUS_HELPER)
        tag_flanke = (self._prev_tag == "off" and tag == "on")
        nacht_flanke = (self._prev_nacht == "off" and nacht == "on")
        self._prev_tag = tag if tag in ("on", "off") else None
        self._prev_nacht = nacht if nacht in ("on", "off") else None

        if tag_flanke or nacht_flanke:
            if self._overrides:
                LOG.info("%s-Flanke → %d Sperre(n) gelöscht",
                         "Nachtmodus" if nacht_flanke else "Tagmodus",
                         len(self._overrides))
                self._overrides.clear()
        if nacht_flanke:
            # Wie die Vorlage: beim Schlafengehen alles aus — reduziert auf
            # die zugeordneten Lichter (kein turn_off all beim Kunden!).
            LOG.info("Nachtmodus-Flanke → zugeordnete Lichter aus")
            for z in self.zonen:
                zz = self._zust[z["id"]]
                zz["will"] = "aus"
                zz["aus_pending_ms"] = None
                for l in z["lights"]:
                    await self._schalte(l, False, force=True)

        nacht_aktiv = (nacht == "on")

        # --- Abgelaufene Sperren räumen ---
        for zid in list(self._overrides.keys()):
            if self._overrides[zid]["bis_ms"] <= now:
                LOG.info("Sperre abgelaufen: Zone %s — Automatik wieder aktiv", zid)
                self._overrides.pop(zid, None)
                self._zust[zid]["will"] = None  # frisch bewerten (sanft, s.u.)

        # --- Zonen-Regelung ---
        status_zonen = {}
        zonen_an = 0
        for z in self.zonen:
            zid = z["id"]
            zz = self._zust[zid]
            praesenz = any(self.ha.state(p) == "on" for p in z["presence"])
            lichter_an = sum(1 for l in z["lights"] if self.ha.state(l) == "on")
            gesperrt = zid in self._overrides

            # Ziel bestimmen: Präsenz + Lux-Hysterese, Nachtmodus dominiert
            if nacht_aktiv or not praesenz:
                will_an = False
            else:
                lux = self._lux_wert(z)
                if lux is None:
                    # kein/defekter Lux-Sensor → rein präsenzgesteuert
                    will_an = True
                else:
                    if lux < z["lux_an_unter"]:
                        zz["hyst_an"] = True
                    elif lux > z["lux_aus_ueber"]:
                        zz["hyst_an"] = False
                    # dazwischen: letzte Entscheidung halten (Hysterese)
                    will_an = zz["hyst_an"]

            if gesperrt:
                # Automatik pausiert — nur beobachten, nichts schalten.
                zz["aus_pending_ms"] = None
            elif will_an:
                zz["aus_pending_ms"] = None
                if lichter_an < len(z["lights"]):
                    for l in z["lights"]:
                        await self._schalte(l, True)
                zz["will"] = "an"
            else:
                # Abschalt-Verzögerung: läuft wenn vorher „an" gewollt war
                # ODER der Wunsch unbekannt ist während Licht brennt (Start:
                # kein hartes Sofort-Aus beim Kunden).
                if zz["will"] == "an" or (zz["will"] is None and lichter_an):
                    if zz["aus_pending_ms"] is None:
                        zz["aus_pending_ms"] = now
                    if (now - zz["aus_pending_ms"]) < z["aus_nach_s"] * 1000:
                        pass  # noch warten — Präsenz-Rückkehr bricht ab
                    else:
                        zz["aus_pending_ms"] = None
                        for l in z["lights"]:
                            await self._schalte(l, False)
                        zz["will"] = "aus"
                else:
                    zz["aus_pending_ms"] = None
                    if lichter_an:
                        for l in z["lights"]:
                            await self._schalte(l, False)
                    zz["will"] = "aus"

            if zz["will"] == "an":
                zonen_an += 1
            ov = self._overrides.get(zid)
            status_zonen[zid] = {
                "name": z["name"],
                "praesenz": praesenz,
                "will_an": zz["will"] == "an",
                "lichter_an": lichter_an,
                "aus_pending": zz["aus_pending_ms"] is not None,
                "override_bis_ms": ov["bis_ms"] if ov else None,
                "override_grund": ov["grund"] if ov else None,
            }

        self._schreibe_status(zonen_an, status_zonen)

    def _lux_wert(self, zone):
        if not zone["lux"]:
            return None
        try:
            return float(self.ha.state(zone["lux"]))
        except (TypeError, ValueError):
            return None  # unknown/unavailable → wie „kein Sensor"

    # ------------------------------------------------------------------
    # Schalten — NUR-BEI-ÄNDERUNG (Pflicht-Regel) + Cooldown + Eigen-Marker
    # ------------------------------------------------------------------
    async def _schalte(self, eid, an: bool, force: bool = False):
        ziel = "on" if an else "off"
        ist = self.ha.state(eid)
        if ist == ziel:
            return  # Ist == Soll → KEIN Call (Nur-bei-Änderung)
        if ist not in ("on", "off"):
            return  # unavailable/unknown → Call wäre sinnlos/blind
        now = jetzt_ms()
        if not force and (now - self._letzter_call.get(eid, 0)) < ACTION_COOLDOWN_MS:
            return  # Anti-Spam solange der Aktor noch nicht geantwortet hat
        # Eigen-Marker VOR dem Call setzen — das Echo kann schneller sein
        # als das await-Ergebnis (sonst Self-Override wie in der Vorlage).
        self._letzter_call[eid] = now
        self._eigen.setdefault(eid, {})[ziel] = now
        self._erwartet[eid] = ziel
        domain = eid.split(".", 1)[0]  # light/switch — beides turn_on/turn_off
        try:
            await self.ha.call(domain, "turn_on" if an else "turn_off",
                               {"entity_id": eid})
            LOG.info("%s → %s.turn_%s", eid, domain, ziel)
        except Exception as e:
            LOG.warning("Schalten %s → %s fehlgeschlagen: %s", eid, ziel, e)

    # ------------------------------------------------------------------
    # Persistenz über den Status-Sensor (Restart-Pflicht der Architektur)
    # ------------------------------------------------------------------
    def _lade_persistenz(self):
        """Override-Sperren aus dem Status-Sensor zurücklesen — sie müssen
        einen Add-on-/HA-Neustart überleben (sonst schaltet die Automatik
        dem Bewohner das eben von Hand geschaltete Licht wieder um)."""
        try:
            zonen = self.ha.attr(STATUS_SENSOR, "zonen", {}) or {}
            now = jetzt_ms()
            for zid, info in zonen.items():
                if zid not in self._zust or not isinstance(info, dict):
                    continue  # Schema-Drift/alte Zone → ignorieren
                bis = self._int(info.get("override_bis_ms"), 0)
                if bis > now:
                    self._overrides[zid] = {
                        "bis_ms": bis,
                        "grund": str(info.get("override_grund") or "wiederhergestellt"),
                    }
                    LOG.info("Sperre wiederhergestellt: Zone %s noch %d min",
                             zid, (bis - now) // 60_000)
        except Exception:
            LOG.exception("Persistenz-Restore fehlgeschlagen — starte leer")

    def _schreibe_status(self, zonen_an: int, status_zonen: dict):
        """Status-Sensor nur bei tatsächlicher Änderung schreiben (Pflicht).
        set_state_sync ist blocking (urllib) → in einen Thread auslagern,
        damit der Tick nie blockiert (Pflicht-Regel)."""
        staat = f"{zonen_an}/{len(self.zonen)} an"
        attrs = {
            "zonen": status_zonen,
            "gesperrte_zonen": len(self._overrides),
            "friendly_name": "JoAmy · Licht-Automatik",
            "icon": "mdi:lightbulb-auto",
        }
        if self._letzter_status == (staat, attrs):
            return  # keine Änderung → kein Write
        self._letzter_status = (staat, attrs)
        asyncio.create_task(
            asyncio.to_thread(self.ha.set_state_sync, STATUS_SENSOR, staat, attrs))
