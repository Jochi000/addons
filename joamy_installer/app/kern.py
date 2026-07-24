"""JoAmy Installer — Kern: Registrierung, Poll, ZIP-Installation, Core-API.

Ablauf (Kontrakt KONTRAKT-ADDON.md):
  1. Einmalig eine instanz_id (uuid4) erzeugen und in /data/instanz.json
     persistieren (übersteht Add-on-Update UND Neustart).
  2. Beim Lizenz-Server registrieren → instanz_token + Kopplungscode.
     Der Code wird als Zeile exakt `KOPPLUNGSCODE: XXX-YYY` geloggt (die
     Abnahme liest das aus `ha addons logs`) und auf der Ingress-Seite gezeigt.
  3. Poll-Loop auf GET /api/v1/instanz/pakete. Jedes neue/geänderte Paket
     (Fingerabdruck kauf_id+theme+version+name in /data/status.json):
     ZIP laden → alte Version nach /config/joamy_backup/<ts>/ sichern →
     nach /config/custom_components/ entpacken → Config-Flow anstoßen →
     bei auto_neustart Core-Neustart.
  Fehler werden robust geloggt — die Schleife crasht nie.

Pfade sind für den Mock-Test über ENV konfigurierbar:
  DATA_DIR   (Default /data)    — instanz.json, status.json, options.json
  CONFIG_DIR (Default /config)  — custom_components/, joamy_backup/
  SUPERVISOR_URL (Default http://supervisor) — Core-API-Basis
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import shutil
import time
import uuid
import zipfile
from collections import deque
from datetime import datetime

import aiohttp

LOG = logging.getLogger("joamy.installer")

ADDON_VERSION = "0.1.10"

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/config")
SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

INSTANZ_DATEI = os.path.join(DATA_DIR, "instanz.json")
STATUS_DATEI = os.path.join(DATA_DIR, "status.json")
OPTIONS_DATEI = os.path.join(DATA_DIR, "options.json")

# Home Assistant hat eine eigene, pro Instanz eindeutige UUID in
# <config>/.storage/core.uuid. Sie liegt im /config-Ordner → sie ist Teil jedes
# HA-Backups und überlebt Config-Restore UND Umzug auf neue Hardware. Wir leiten
# unsere instanz_id DETERMINISTISCH daraus ab (gehasht, damit die rohe HA-UUID
# unseren Server nie erreicht). Effekt: Käufe sind an das HA gebunden, nicht an
# das flüchtige Add-on-Volume — ein wiederhergestelltes/umgezogenes HA findet
# seine Käufe automatisch wieder, sobald das Add-on neu installiert ist.
CORE_UUID_DATEI = os.path.join(CONFIG_DIR, ".storage", "core.uuid")


def _stabile_instanz_id() -> str | None:
    """Deterministische instanz_id aus HA core.uuid; None wenn nicht lesbar."""
    try:
        with open(CORE_UUID_DATEI, encoding="utf-8") as f:
            roh = json.load(f)
        core = (roh.get("data") or {}).get("uuid")
        if not core or not isinstance(core, str):
            return None
        h = hashlib.sha256((core + "|joamy.instanz.v1").encode("utf-8")).hexdigest()
        return "jha_" + h[:32]
    except Exception:
        return None

MAX_ZIP_BYTES = 200 * 1024 * 1024   # Schutzgrenze; das Kochbuch-Paket liegt ~ wenige MB
REG_DROSSEL_S = 20                  # Registrierung höchstens alle 20 s (UI-Refresh-Schutz)
LOG_ZEILEN_MAX = 200

# Ring-Puffer für die Ingress-Seite („letzte Log-Zeilen").
LOG_PUFFER: deque[str] = deque(maxlen=LOG_ZEILEN_MAX)


class PufferHandler(logging.Handler):
    """Hängt jede formatierte Log-Zeile in den Ring-Puffer für die UI."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_PUFFER.append(self.format(record))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Kleine Datei-Helfer
# ---------------------------------------------------------------------------
def lade_json(pfad: str, standard):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return standard
    except Exception as e:
        LOG.warning("Datei %s nicht lesbar (%s) — nutze Standardwerte.", pfad, e)
        return standard


def speichere_json(pfad: str, daten) -> None:
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    os.replace(tmp, pfad)


def lade_optionen() -> dict:
    """Add-on-Optionen (der Supervisor legt sie unter /data/options.json ab)."""
    roh = lade_json(OPTIONS_DATEI, {})
    if not isinstance(roh, dict):
        roh = {}
    try:
        poll = max(5, int(roh.get("poll_sekunden") or 60))
    except (TypeError, ValueError):
        poll = 60
    return {
        "server_url": str(roh.get("server_url") or "https://lizenz.joamy.uk").rstrip("/"),
        "poll_sekunden": poll,
        "auto_neustart": bool(roh.get("auto_neustart", True)),
    }


def _fingerabdruck(paket: dict) -> str:
    """Erkennungsmerkmal eines Kaufs — ändert sich bei Theme-/Versions-Update."""
    return "|".join(str(paket.get(k, "")) for k in ("kauf_id", "baustein", "theme", "version", "name", "titel"))


class Installer:
    """Hält Zustand + Session; alle öffentlichen Methoden sind crash-sicher."""

    def __init__(self, optionen: dict) -> None:
        self.optionen = optionen
        self.session: aiohttp.ClientSession | None = None

        # instanz.json: instanz_id + Server-Token, persistent in /data.
        # Identitäts-Strategie (restore-fest, ohne bestehende Bindung zu brechen):
        #  - Bereits registrierte Instanz (id + token vorhanden) → UNVERÄNDERT
        #    behalten; ihre Käufe hängen an dieser ID, die rühren wir nie an.
        #  - Frische Installation → stabile ID aus HA core.uuid bevorzugen
        #    (überlebt Restore/Umzug); nur wenn core.uuid nicht lesbar ist
        #    (z. B. exotisches Setup) Fallback auf eine Zufalls-UUID wie bisher.
        inst = lade_json(INSTANZ_DATEI, {})
        if not isinstance(inst, dict):
            inst = {}
        if inst.get("instanz_id") and inst.get("instanz_token"):
            pass  # etablierte Instanz — Identität ist heilig
        elif inst.get("instanz_id"):
            # ID da, aber noch nicht registriert: falls eine stabile core.uuid-ID
            # verfügbar ist und abweicht, jetzt (vor der Registrierung) darauf
            # umstellen — dann ist auch diese Instanz künftig restore-fest.
            stabil = _stabile_instanz_id()
            if stabil and stabil != inst["instanz_id"]:
                LOG.info("Instanz-ID auf HA-stabile Kennung umgestellt (noch nicht registriert).")
                inst = {"instanz_id": stabil, "instanz_token": None}
                speichere_json(INSTANZ_DATEI, inst)
        else:
            neue = _stabile_instanz_id() or str(uuid.uuid4())
            quelle = "aus HA core.uuid (restore-fest)" if neue.startswith("jha_") else "zufällig (core.uuid nicht lesbar)"
            inst = {"instanz_id": neue, "instanz_token": None}
            speichere_json(INSTANZ_DATEI, inst)
            LOG.info("Instanz-ID erzeugt %s.", quelle)
        self.instanz_id: str = inst["instanz_id"]
        self.instanz_token: str | None = inst.get("instanz_token") or None

        # status.json: Fingerabdrücke der installierten Bausteine + offene Arbeit.
        # Schema-Drift-Schutz: fehlende Schlüssel immer nachziehen.
        st = lade_json(STATUS_DATEI, {})
        if not isinstance(st, dict):
            st = {}
        st.setdefault("installiert", {})
        st.setdefault("flow_ausstehend", [])
        st.setdefault("reload_ausstehend", [])
        st.setdefault("neustart_noetig", False)
        if not isinstance(st["installiert"], dict):
            st["installiert"] = {}
        if not isinstance(st["flow_ausstehend"], list):
            st["flow_ausstehend"] = []
        if not isinstance(st["reload_ausstehend"], list):
            st["reload_ausstehend"] = []
        self.status: dict = st

        # Laufzeit-Zustand (bewusst NICHT persistent — Code ist kurzlebig).
        self.kopplungscode: str | None = None
        self.code_ablauf_s: float = 0.0
        self.server_ok: bool | None = None      # None = noch nie versucht
        self.letzter_poll_iso: str | None = None
        self.letzter_fehler: str | None = None
        self._letzte_reg_s: float = 0.0
        self._such_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Start / Registrierung
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        await self.registrieren(erzwinge=True)

    async def _hole_ha_version(self) -> str:
        daten = await self._core_api("GET", "/config")
        if isinstance(daten, dict) and daten.get("version"):
            return str(daten["version"])
        return "unbekannt"

    async def registrieren(self, erzwinge: bool = False) -> None:
        """POST /api/v1/instanz/registrieren — idempotent je instanz_id.

        Liefert (immer) den instanz_token und einen FRISCHEN Kopplungscode.
        Gedrosselt, damit UI-Aufrufe den Server nicht fluten.
        """
        if not erzwinge and time.time() - self._letzte_reg_s < REG_DROSSEL_S:
            return
        self._letzte_reg_s = time.time()

        ha_version = await self._hole_ha_version()
        url = f"{self.optionen['server_url']}/api/v1/instanz/registrieren"
        rumpf = {
            "instanz_id": self.instanz_id,
            "ha_version": ha_version,
            "addon_version": ADDON_VERSION,
        }
        try:
            async with self.session.post(url, json=rumpf) as r:
                daten = await r.json(content_type=None)
                if r.status != 200 or not isinstance(daten, dict):
                    raise RuntimeError((daten or {}).get("fehler") or f"HTTP {r.status}")
        except Exception as e:
            self.server_ok = False
            self.letzter_fehler = f"Registrierung: {e}"
            LOG.error("Registrierung beim Lizenz-Server fehlgeschlagen: %s", e)
            return

        self.server_ok = True
        self.letzter_fehler = None
        token = daten.get("instanz_token")
        if token and token != self.instanz_token:
            self.instanz_token = token
            speichere_json(INSTANZ_DATEI, {"instanz_id": self.instanz_id, "instanz_token": token})

        code = daten.get("kopplungscode")
        if code:
            self.kopplungscode = str(code)
            try:
                gueltig = max(30, int(daten.get("code_gueltig_s") or 900))
            except (TypeError, ValueError):
                gueltig = 900
            self.code_ablauf_s = time.time() + gueltig
            # Zeile EXAKT so — die Abnahme liest sie aus `ha addons logs`.
            print(f"KOPPLUNGSCODE: {self.kopplungscode}", flush=True)
            LOG.info("Kopplungscode erhalten (gültig %d min) — beim Kauf auf joamy.uk eingeben "
                     "(oder auf joamy.uk/verbinden).", gueltig // 60)

    async def code_sicherstellen(self) -> None:
        """Für die UI: abgelaufenen/fehlenden Code frisch holen (gedrosselt)."""
        if not self.instanz_token or not self.kopplungscode or time.time() >= self.code_ablauf_s:
            await self.registrieren()

    # ------------------------------------------------------------------
    # Poll-Loop
    # ------------------------------------------------------------------
    async def poll_schleife(self) -> None:
        LOG.info("Poll-Loop läuft (alle %d s, Server %s).",
                 self.optionen["poll_sekunden"], self.optionen["server_url"])
        while True:
            try:
                await self.suche_kaeufe()
            except Exception as e:                       # nie crashen
                self.letzter_fehler = str(e)
                LOG.error("Poll-Durchlauf fehlgeschlagen: %s", e)
            await asyncio.sleep(self.optionen["poll_sekunden"])

    async def suche_kaeufe(self) -> dict:
        """Ein Poll-Durchlauf; auch vom UI-Knopf „Jetzt nach Käufen suchen"."""
        async with self._such_lock:
            if not self.instanz_token:
                await self.registrieren()
            if not self.instanz_token:
                return {"ok": False, "fehler": "Noch nicht beim Lizenz-Server registriert."}

            pakete = await self._hole_pakete()
            if pakete is None:
                return {"ok": False, "fehler": self.letzter_fehler or "Server nicht erreichbar."}

            if self.server_ok is False:
                LOG.info("Lizenz-Server wieder erreichbar.")
            self.server_ok = True
            self.letzter_poll_iso = datetime.now().isoformat(timespec="seconds")
            neu: list[str] = []
            for paket in pakete:
                baustein = str(paket.get("baustein") or "").strip()
                if not baustein:
                    continue
                fp = _fingerabdruck(paket)
                alt = self.status["installiert"].get(baustein)
                if alt and alt.get("fingerabdruck") == fp:
                    continue
                try:
                    await self.installiere(paket, fp)
                    neu.append(baustein)
                except Exception as e:
                    self.letzter_fehler = f"Installation {baustein}: {e}"
                    LOG.error("Installation von '%s' fehlgeschlagen: %s", baustein, e)

            await self._flows_und_neustart()
            return {"ok": True, "pakete": len(pakete), "neu_installiert": neu}

    async def _hole_pakete(self) -> list | None:
        url = f"{self.optionen['server_url']}/api/v1/instanz/pakete"
        for versuch in (1, 2):
            try:
                kopf = {"X-Instanz-Token": self.instanz_token or ""}
                async with self.session.get(url, headers=kopf) as r:
                    if r.status == 401 and versuch == 1:
                        # Server kennt den Token nicht mehr → neu registrieren, 1× erneut.
                        LOG.warning("Instanz-Token abgelehnt — registriere neu.")
                        await self.registrieren(erzwinge=True)
                        continue
                    daten = await r.json(content_type=None)
                    if r.status != 200 or not isinstance(daten, dict):
                        raise RuntimeError((daten or {}).get("fehler") or f"HTTP {r.status}")
                    pakete = daten.get("pakete")
                    return pakete if isinstance(pakete, list) else []
            except Exception as e:
                # Nur beim ZUSTANDSWECHSEL warnen (sonst spammt ein längerer
                # Server-Ausfall das Logbuch alle poll_sekunden voll) — danach
                # still weiterprobieren; die Erholung wird als INFO gemeldet.
                if self.server_ok is not False:
                    LOG.warning("Lizenz-Server nicht erreichbar: %s — ich versuche es still weiter.", e)
                self.server_ok = False
                self.letzter_fehler = f"Paket-Abfrage: {e}"
                return None
        return None

    # ------------------------------------------------------------------
    # Installation: ZIP laden → Backup → entpacken
    # ------------------------------------------------------------------
    async def installiere(self, paket: dict, fp: str) -> None:
        kauf_id = paket.get("kauf_id")
        baustein = str(paket.get("baustein") or "")
        LOG.info("Neuer Kauf erkannt: Baustein '%s' (Theme %s, Version %s, für %s) — lade Paket …",
                 baustein, paket.get("theme"), paket.get("version"), paket.get("name"))

        zip_bytes = await self._lade_zip(kauf_id)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        defekt = zf.testzip()
        if defekt is not None:
            raise RuntimeError(f"ZIP beschädigt (Datei {defekt})")

        # Welche Integrations-Ordner bringt das Paket mit? (Wurzel = custom_components/<domain>/…)
        # Domain-Namen streng validieren — sonst könnte ein bösartiger Eintrag
        # wie "custom_components/../x" den Backup-Schritt auf /config lenken.
        domains: set[str] = set()
        for name in zf.namelist():
            teile = name.replace("\\", "/").split("/")
            if (len(teile) >= 3 and teile[0] == "custom_components"
                    and re.fullmatch(r"[A-Za-z0-9_]+", teile[1] or "")):
                domains.add(teile[1])
        if not domains:
            raise RuntimeError("ZIP enthält kein custom_components/<domain>/ — Paket unbrauchbar")
        domain_liste = sorted(domains)

        # Alte Version(en) sichern — Kontrakt: /config/joamy_backup/<ts>/.
        # war_update[domain] = es gab schon eine Version (→ Update ohne Neustart).
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        war_update: dict[str, bool] = {}
        for domain in domain_liste:
            war_update[domain] = self._sichere_alt(domain, ts)

        # Entpacken. Nur Pfade unterhalb custom_components/, Traversal hart abgewiesen.
        wurzel_dateien: list[tuple[str, bytes]] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            teile = name.split("/")
            if name.startswith("/") or ".." in teile or (teile and ":" in teile[0]):
                LOG.warning("Überspringe verdächtigen ZIP-Eintrag: %s", info.filename)
                continue
            if teile[0] == "custom_components" and len(teile) >= 3 and teile[1] in domains:
                ziel = os.path.join(CONFIG_DIR, *teile)
                os.makedirs(os.path.dirname(ziel), exist_ok=True)
                with open(ziel, "wb") as f:
                    f.write(zf.read(info))
            elif len(teile) == 1:
                # Wurzel-Dateien (LIES-MICH.txt) → in den Integrations-Ordner legen.
                wurzel_dateien.append((teile[0], zf.read(info)))
            else:
                LOG.debug("Ignoriere ZIP-Eintrag außerhalb custom_components/: %s", name)
        for datei_name, inhalt in wurzel_dateien:
            ziel = os.path.join(CONFIG_DIR, "custom_components", domain_liste[0], datei_name)
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            with open(ziel, "wb") as f:
                f.write(inhalt)

        # Fingerabdruck + offene Arbeit persistieren (übersteht Neustart).
        self.status["installiert"][baustein] = {
            "kauf_id": kauf_id,
            "baustein": baustein,
            "theme": paket.get("theme"),
            "name": paket.get("name"),
            "version": paket.get("version"),
            "fingerabdruck": fp,
            "domains": domain_liste,
            "installiert_am": datetime.now().isoformat(timespec="seconds"),
        }
        # NEU vs UPDATE: eine bereits installierte Integration (Alt-Version war da)
        # wird per reload_config_entry aktualisiert — KEIN Vollneustart (der neue
        # Karten-Stand inkl. Cache-Bust wird beim Reload gezogen; der User muss nur
        # das Dashboard neu laden). Nur eine WIRKLICH neue Integration braucht einen
        # einmaligen Core-Neustart, damit die Custom-Component importiert wird.
        neu_domains = [d for d in domain_liste if not war_update.get(d)]
        upd_domains = [d for d in domain_liste if war_update.get(d)]
        for domain in neu_domains:
            if domain not in self.status["flow_ausstehend"]:
                self.status["flow_ausstehend"].append(domain)
        for domain in upd_domains:
            if domain not in self.status.setdefault("reload_ausstehend", []):
                self.status["reload_ausstehend"].append(domain)
        if neu_domains:
            self.status["neustart_noetig"] = True
        speichere_json(STATUS_DATEI, self.status)
        LOG.info("Baustein '%s' installiert → /config/custom_components/%s (Backup: joamy_backup/%s).",
                 baustein, domain_liste[0], ts)

    async def _lade_zip(self, kauf_id) -> bytes:
        url = f"{self.optionen['server_url']}/api/v1/instanz/paket/{kauf_id}"
        kopf = {"X-Instanz-Token": self.instanz_token or ""}
        async with self.session.get(url, headers=kopf) as r:
            if r.status != 200:
                try:
                    daten = await r.json(content_type=None)
                    grund = (daten or {}).get("fehler")
                except Exception:
                    grund = None
                raise RuntimeError(grund or f"Paket-Download HTTP {r.status}")
            rumpf = await r.read()
        if len(rumpf) > MAX_ZIP_BYTES:
            raise RuntimeError(f"Paket zu groß ({len(rumpf)} Bytes)")
        return rumpf

    def _sichere_alt(self, domain: str, ts: str) -> bool:
        """True = es gab eine Alt-Version (Update); False = Erstinstallation."""
        if not re.fullmatch(r"[A-Za-z0-9_]+", domain or ""):
            return False
        quelle = os.path.join(CONFIG_DIR, "custom_components", domain)
        if not os.path.isdir(quelle):
            return False
        ziel = os.path.join(CONFIG_DIR, "joamy_backup", ts, domain)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        shutil.move(quelle, ziel)
        LOG.info("Alte Version gesichert: /config/joamy_backup/%s/%s", ts, domain)
        return True

    # ------------------------------------------------------------------
    # Core-API: Config-Flow anstoßen + optionaler Neustart
    # ------------------------------------------------------------------
    async def _flows_und_neustart(self) -> None:
        """Wird jeden Poll-Tick gerufen: offene Flows nachziehen, Neustart nachholen.

        Direkt nach dem Entpacken kennt der Core die Integration meist noch
        nicht (Custom-Component ohne Neustart nicht geladen) — der Flow-Versuch
        schlägt dann fehl, bleibt in flow_ausstehend und klappt beim nächsten
        Tick NACH dem Neustart. Das Add-on selbst überlebt den Core-Neustart.
        """
        geaendert = False
        # Updates bereits geladener Integrationen: reload_config_entry statt
        # Vollneustart — zieht den neuen Karten-Stand (neuer Cache-Bust) ohne
        # Core-Neustart. Der User lädt danach nur sein Dashboard neu.
        for domain in list(self.status.get("reload_ausstehend") or []):
            zustand = await self._reload_domain(domain)
            if zustand == "fertig":
                self.status["reload_ausstehend"].remove(domain)
                geaendert = True
            elif zustand == "neustart":
                # Integration wider Erwarten NICHT geladen → doch einmalig neu starten.
                self.status["reload_ausstehend"].remove(domain)
                if domain not in self.status["flow_ausstehend"]:
                    self.status["flow_ausstehend"].append(domain)
                self.status["neustart_noetig"] = True
                geaendert = True
            # "warten" → Core nicht erreichbar, nächster Tick

        for domain in list(self.status.get("flow_ausstehend") or []):
            if await self._stosse_flow_an(domain):
                self.status["flow_ausstehend"].remove(domain)
                geaendert = True

        if self.status.get("neustart_noetig"):
            if not self.optionen["auto_neustart"]:
                LOG.info("auto_neustart ist aus — bitte Home Assistant einmal selbst neu starten.")
                self.status["neustart_noetig"] = False
                geaendert = True
            elif await self._core_neustart():
                self.status["neustart_noetig"] = False
                geaendert = True

        if geaendert:
            speichere_json(STATUS_DATEI, self.status)

    async def _reload_domain(self, domain: str) -> str:
        """Update einer bereits geladenen Integration ohne Vollneustart.

        Rückgabe: 'fertig' (reload angestoßen) · 'neustart' (Integration wider
        Erwarten nicht geladen → einmaliger Neustart) · 'warten' (Core nicht
        erreichbar). reload_config_entry re-läuft async_setup_entry → neuer
        Karten-Cache-Bust; der Nutzer lädt danach nur sein Dashboard neu.
        """
        eintraege = await self._core_api("GET", f"/config/config_entries/entry?domain={domain}")
        if eintraege is None:
            return "warten"
        if not (isinstance(eintraege, list) and eintraege):
            return "neustart"        # kein Eintrag → doch nicht geladen
        for e in eintraege:
            eid = e.get("entry_id") if isinstance(e, dict) else None
            if eid:
                await self._core_api("POST", f"/config/config_entries/entry/{eid}/reload")
        LOG.info("Baustein '%s' aktualisiert (reload, ohne Neustart) — Dashboard neu laden genügt.", domain)
        return "fertig"

    async def _stosse_flow_an(self, domain: str) -> bool:
        """True = erledigt (Eintrag existiert, wurde erstellt oder Abort)."""
        eintraege = await self._core_api("GET", f"/config/config_entries/entry?domain={domain}")
        if eintraege is None:
            return False                                  # Core (noch) nicht erreichbar
        if isinstance(eintraege, list) and eintraege:
            LOG.info("Integration '%s' ist bereits eingerichtet — kein Flow nötig.", domain)
            return True

        antwort = await self._core_api(
            "POST", "/config/config_entries/flow",
            {"handler": domain, "show_advanced_options": False})
        if not isinstance(antwort, dict):
            LOG.info("Config-Flow für '%s' noch nicht möglich (Integration erst nach Neustart geladen).",
                     domain)
            return False

        typ = antwort.get("type")
        if typ == "abort":
            LOG.info("Config-Flow '%s': %s — schon eingerichtet, alles gut.",
                     domain, antwort.get("reason") or "abort")
            return True
        if typ == "create_entry":
            LOG.info("Integration '%s' eingerichtet.", domain)
            return True
        if typ == "form" and antwort.get("flow_id"):
            # Single-Instance-Flows zeigen erst ein leeres Bestätigungsformular.
            antwort2 = await self._core_api(
                "POST", f"/config/config_entries/flow/{antwort['flow_id']}", {})
            if isinstance(antwort2, dict) and antwort2.get("type") in ("create_entry", "abort"):
                LOG.info("Integration '%s' eingerichtet (%s).", domain, antwort2.get("type"))
                return True
        LOG.warning("Config-Flow '%s' unerwartet beantwortet: %s", domain, antwort)
        return False

    async def _core_neustart(self) -> bool:
        """Core-Neustart über den Supervisor-Management-Endpunkt (wie `ha core restart`).

        NICHT über /core/api/services/homeassistant/restart — der Proxy wartet
        auf die Service-Antwort und läuft in ein 504-Gateway-Timeout (HA 2026.x).
        /core/restart blockiert bis der Core wieder da ist; großzügiger Timeout.
        Einmal-Schuss: Auch bei unklarem Ausgang wird NICHT endlos neu ausgelöst
        (Schutz vor Neustart-Schleifen); danach Readiness-Poll mit Log.
        """
        LOG.info("Starte Home Assistant neu, damit der neue Baustein lädt (auto_neustart) …")
        url = f"{SUPERVISOR_URL}/core/restart"
        kopf = {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', SUPERVISOR_TOKEN)}"}
        try:
            async with self.session.post(
                url, headers=kopf, timeout=aiohttp.ClientTimeout(total=300)
            ) as r:
                if r.status >= 400:
                    LOG.warning("Neustart abgelehnt (HTTP %s: %s) — Hinweis bleibt in der Oberfläche.",
                                r.status, (await r.text())[:150])
                    return True  # kein Retry-Loop; Nutzer sieht den Hinweis
        except Exception as e:  # Timeout/Verbindungsabriss: Neustart läuft vermutlich trotzdem
            LOG.info("Neustart angestoßen (Antwort offen: %s) — warte auf den Core …", str(e)[:80])
        # Readiness: bis zu 2 Minuten auf die Core-API warten (rein informativ)
        for _ in range(24):
            await asyncio.sleep(5)
            if await self._core_api("GET", "/config") is not None:
                LOG.info("Home Assistant ist wieder da — Baustein aktiv.")
                return True
        LOG.warning("Core-API nach Neustart noch nicht erreichbar — bitte im Zweifel manuell prüfen.")
        return True

    async def _core_api(self, methode: str, pfad: str, json_daten=None):
        """Ein Aufruf der Core-API über den Supervisor-Proxy; None bei Fehler.

        Auth-Header explizit pro Aufruf (Session hat bewusst keinen Default-Auth).
        """
        url = f"{SUPERVISOR_URL}/core/api{pfad}"
        kopf = {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', SUPERVISOR_TOKEN)}"}
        try:
            async with self.session.request(methode, url, json=json_daten, headers=kopf) as r:
                if r.status >= 400:
                    text = (await r.text())[:200]
                    LOG.debug("Core-API %s %s → HTTP %s: %s", methode, pfad, r.status, text)
                    return None
                try:
                    return await r.json(content_type=None)
                except Exception:
                    return {}
        except Exception as e:
            LOG.debug("Core-API nicht erreichbar (%s %s): %s", methode, pfad, e)
            return None

    async def entitaeten_fuer_konfig(self) -> dict:
        """Kamera-/Türklingel-/Knopf-Entitäten für den Karten-Konfigurator.

        Liest /states über den Core-Proxy und gruppiert nach Domain. Der
        Konfigurator (Ingress-Seite) baut daraus den YAML-Kopiercode.
        """
        states = await self._core_api("GET", "/states")
        if not isinstance(states, list):
            return {"cameras": [], "binary_sensors": [], "buttons": [],
                    "fehler": "Home Assistant nicht erreichbar."}

        def liste(prefix: str) -> list:
            out = []
            for s in states:
                eid = s.get("entity_id", "")
                if isinstance(eid, str) and eid.startswith(prefix):
                    name = (s.get("attributes") or {}).get("friendly_name") or eid
                    out.append({"entity": eid, "name": str(name)})
            out.sort(key=lambda x: x["name"].lower())
            return out

        return {
            "cameras": liste("camera."),
            "binary_sensors": liste("binary_sensor."),
            "buttons": liste("button."),
        }

    # ------------------------------------------------------------------
    # Status für die Ingress-Seite
    # ------------------------------------------------------------------
    async def status_fuer_ui(self) -> dict:
        await self.code_sicherstellen()
        code_rest = max(0, int(self.code_ablauf_s - time.time())) if self.kopplungscode else 0
        bausteine = []
        for baustein, info in sorted(self.status.get("installiert", {}).items()):
            bausteine.append({
                "baustein": baustein,
                "theme": info.get("theme"),
                "name": info.get("name"),
                "version": info.get("version"),
                "installiert_am": info.get("installiert_am"),
            })
        return {
            "kopplungscode": self.kopplungscode,
            "code_rest_s": code_rest,
            "server_url": self.optionen["server_url"],
            "server_ok": self.server_ok,
            "registriert": bool(self.instanz_token),
            "instanz_id": self.instanz_id,
            "addon_version": ADDON_VERSION,
            "auto_neustart": self.optionen["auto_neustart"],
            "poll_sekunden": self.optionen["poll_sekunden"],
            "neustart_noetig": bool(self.status.get("neustart_noetig")),
            "flow_ausstehend": list(self.status.get("flow_ausstehend") or []),
            "letzter_poll": self.letzter_poll_iso,
            "letzter_fehler": self.letzter_fehler,
            "bausteine": bausteine,
            "logs": list(LOG_PUFFER)[-40:],
        }
