"""Prüfstand für die Zeitschaltuhr-Rechenfunktionen (KEIN HA nötig).

Deckt die harten Fälle der Testmatrix (Kap. 12.4/12.5/12.6) ab:
Über-Mitternacht inkl. Tageszuordnung, DST-Frühjahrslücke, Herbst-Doppelstunde,
Einmal-Feuern, Einzel-Aus-Block, Sonnenzeit, Reconciliation-Soll.
Aufruf: python3 _zeitschaltuhr_pruefstand.py
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from zeitschaltuhr import (zs_block_ereignisse, zs_faellig, zs_naechstes_ereignis,
                           zs_sonnenzeit, zs_soll_zustand, zs_zeitpunkt_an_tag)

TZ = ZoneInfo("Europe/Berlin")
FEHLER = []


def ok(bedingung, was):
    print(("  ok    " if bedingung else "  FEHL  ") + was)
    if not bedingung:
        FEHLER.append(was)


def lokal(*a):
    return datetime(*a, tzinfo=TZ)


print("1) Über Mitternacht + Tageszuordnung (Ein Mo 21:00 / Aus 06:00, nur Montag)")
uhr = {"id": "u1", "enabled": True, "target": "switch.x",
       "blocks": [{"days": [0], "on": {"type": "time", "value": "21:00"},
                   "off": {"type": "time", "value": "06:00"}}]}
# Montag, 28.07.2025 ist ein Montag
ev = zs_block_ereignisse(uhr["blocks"][0], lokal(2025, 7, 28, 12, 0), {}, TZ)
paare = [(a, z.strftime("%a %H:%M")) for a, z in ev]
ok(("ein", "Mon 21:00") in paare, "Ein am Montag 21:00")
ok(("aus", "Tue 06:00") in paare, "Aus am DIENSTAG 06:00 (gehört zum Starttag Montag)")
ok(not any(a == "ein" and z.startswith("Tue") for a, z in paare), "kein Ein am Dienstag (nicht in days)")
ok(zs_soll_zustand(uhr, lokal(2025, 7, 28, 23, 0), {}, TZ) is True, "23:00 → SOLL an (im Fenster)")
ok(zs_soll_zustand(uhr, lokal(2025, 7, 29, 5, 0), {}, TZ) is True, "Di 05:00 → SOLL an (über Mitternacht)")
ok(zs_soll_zustand(uhr, lokal(2025, 7, 29, 7, 0), {}, TZ) is False, "Di 07:00 → SOLL aus (Aus verpasst → nachholen)")
ok(zs_soll_zustand(uhr, lokal(2025, 7, 31, 12, 0), {}, TZ) is None, "Do mittags → nichts erzwingen")

print("2) DST-Frühjahrslücke (30.03.2025: 02:00–03:00 existiert nicht)")
t = zs_zeitpunkt_an_tag(lokal(2025, 3, 30, 0, 0), 2, 30, TZ)
ok((t.hour, t.minute) == (3, 0), f"02:30 rutscht auf 03:00 (kam: {t.strftime('%H:%M')})")
ok(t.utcoffset().total_seconds() == 7200, "Ergebnis liegt in Sommerzeit (+02:00)")
t2 = zs_zeitpunkt_an_tag(lokal(2025, 3, 30, 0, 0), 1, 30, TZ)
ok((t2.hour, t2.minute) == (1, 30), "01:30 bleibt 01:30 (existiert)")

print("3) Herbst-Doppelstunde (26.10.2025: 02:30 gibt es zweimal → erste Instanz)")
t3 = zs_zeitpunkt_an_tag(lokal(2025, 10, 26, 0, 0), 2, 30, TZ)
ok((t3.hour, t3.minute) == (2, 30), "bleibt 02:30")
ok(t3.utcoffset().total_seconds() == 7200, "ERSTE Instanz (+02:00, noch Sommerzeit)")

print("4) Einmal-Feuern (Feuerfenster + Dedup)")
geschaltet = {}
jetzt = lokal(2025, 7, 28, 21, 0, 30)                      # 30 s nach Soll
faellig = zs_faellig(uhr, jetzt, {}, TZ, geschaltet)
ok(len(faellig) == 1 and faellig[0][0] == "ein", "Ein ist fällig (30 s nach Soll)")
geschaltet[faellig[0][2]] = 1.0
ok(zs_faellig(uhr, jetzt, {}, TZ, geschaltet) == [], "zweiter Tick: NICHT nochmal fällig")
ok(zs_faellig(uhr, lokal(2025, 7, 28, 21, 5, 0), {}, TZ, {}) == [], "5 min später: Fenster vorbei (kein Nachfeuern)")

print("5) Einzel-Aus-Block (Kap. 15.6: nur ausschalten um 23:00, täglich)")
uhr2 = {"id": "u2", "enabled": True, "target": "switch.y",
        "blocks": [{"days": [0, 1, 2, 3, 4, 5, 6], "off": {"type": "time", "value": "23:00"}}]}
ok(zs_soll_zustand(uhr2, lokal(2025, 7, 28, 23, 30), {}, TZ) is False, "23:30 → Aus nachholen")
n = zs_naechstes_ereignis(uhr2, lokal(2025, 7, 28, 12, 0), {}, TZ)
ok(n and n[0] == "aus" and n[1].hour == 23, "nächstes Ereignis: aus 23:00")

print("6) Sonnenzeit (sun.sun-Attribute, +15 min Offset)")
sonne = {"next_setting": "2025-07-28T19:14:00+00:00"}      # 21:14 lokal
s = zs_sonnenzeit(sonne, "sunset", 15, TZ)
ok(s is not None and (s.hour, s.minute) == (21, 29), f"Sonnenuntergang+15 = 21:29 (kam: {s.strftime('%H:%M') if s else '—'})")
uhr3 = {"id": "u3", "enabled": True, "target": "light.z",
        "blocks": [{"days": [0, 1, 2, 3, 4, 5, 6],
                    "on": {"type": "sun", "event": "sunset", "offsetMin": 15},
                    "off": {"type": "time", "value": "23:30"}}]}
ok(zs_soll_zustand(uhr3, lokal(2025, 7, 28, 22, 0), sonne, TZ) is True, "22:00 → im Sonnen-Fenster")

print("7) Pausierte Uhr")
uhr4 = dict(uhr, enabled=False)
ok(zs_soll_zustand(uhr4, lokal(2025, 7, 28, 23, 0), {}, TZ) is None, "pausiert → nie erzwingen")
ok(zs_naechstes_ereignis(uhr4, lokal(2025, 7, 28, 12, 0), {}, TZ) is None, "pausiert → kein nächster Punkt")

print()
print("FEHLER: %d" % len(FEHLER))
raise SystemExit(1 if FEHLER else 0)
