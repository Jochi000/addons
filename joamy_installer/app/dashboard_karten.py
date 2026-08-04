"""Wohin gehoert eine neue Karte in einer Lovelace-Ansicht?

Home Assistant kennt zwei Bauarten von Ansichten, und sie unterscheiden sich
genau dort, wo es weh tut:

  * klassisch (masonry, panel, sidebar): die Karten liegen in ``view["cards"]``
  * SECTIONS: die Karten liegen in ``view["sections"][n]["cards"]`` — und was
    daneben in ``view["cards"]`` steht, zeigt Home Assistant schlicht NICHT an.

Am 04.08. ist genau daran „In mein Dashboard legen" gescheitert: Das Eintragen
gelang, das Speichern gelang, die Rueckmeldung sagte „erledigt" — und im
Dashboard blieb es leer. Ein Fehler, den keine Fehlermeldung findet, weil
technisch alles geklappt hat. Nachgemessen an Franks Home Assistant lag die
Karte tatsaechlich in ``view["cards"]`` einer Sections-Ansicht: unsichtbar.

Dieses Modul haelt genau diese Entscheidung — und zwar OHNE Fremdpakete, damit
sie sich ueberall ausfuehren und pruefen laesst (siehe
``_test/test_dashboard_karten.py``). Alle Funktionen arbeiten ohne Nebenwirkung:
Sie geben Neues zurueck, statt Uebergebenes zu veraendern. Wer fremde
Dashboard-Konfiguration anfasst, sollte sie nicht nebenbei umschreiben.
"""
from __future__ import annotations


def ist_sections(view: dict) -> bool:
    """Ist das eine Sections-Ansicht?

    Geprueft wird beides: die ausdrueckliche Angabe und das blosse Vorhandensein
    von ``sections``. Home Assistant schreibt bei neu angelegten Ansichten
    ``type: sections``; bei aelteren, umgestellten fehlt die Angabe mitunter,
    die Abschnitte sind aber da.
    """
    return view.get("type") == "sections" or isinstance(view.get("sections"), list)


def alle_karten(view: dict) -> list:
    """Jede Karte der Ansicht — gleich welcher Bauart.

    Wird fuer die Doppelt-Pruefung gebraucht: Eine Karte gilt als vorhanden,
    egal ob sie frei in der Ansicht oder in einem Abschnitt liegt.
    """
    karten = list(view.get("cards") or [])
    for abschnitt in view.get("sections") or []:
        karten.extend((abschnitt or {}).get("cards") or [])
    return karten


def karte_anhaengen(view: dict, karte: dict) -> dict:
    """Die Ansicht mit angehaengter Karte — an der Stelle, an der Home Assistant
    sie auch anzeigt.

    In der Sections-Ansicht kommt die Karte in den LETZTEN Abschnitt. Das ist
    die Stelle, an der auch Home Assistant selbst neue Karten ablegt, und der
    Kunde findet sie damit unten statt mitten in einer gewachsenen Ordnung.
    Gibt es noch gar keinen Abschnitt, wird einer angelegt — sonst haette die
    Ansicht keinen Platz, an dem eine Karte sichtbar waere.
    """
    if not ist_sections(view):
        return {**view, "cards": list(view.get("cards") or []) + [karte]}

    abschnitte = [dict(a or {}) for a in (view.get("sections") or [])]
    if not abschnitte:
        abschnitte = [{"type": "grid", "cards": []}]
    letzter = dict(abschnitte[-1])
    letzter["cards"] = list(letzter.get("cards") or []) + [karte]
    abschnitte[-1] = letzter
    return {**view, "sections": abschnitte}
