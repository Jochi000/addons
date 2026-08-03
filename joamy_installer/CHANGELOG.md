## 0.1.56
- **Neu: „In mein Dashboard legen".** Neben jedem „Code kopieren" steht jetzt
  ein Knopf, der die Karte direkt in dein Dashboard einträgt — du wählst nur
  Dashboard und Ansicht. Kein Kopieren, kein „Manuell", kein Einfügen.
  Verschieben kannst du die Karte dort anschließend wie jede andere.
- Vor jedem Eintragen wird deine bisherige Dashboard-Konfiguration nach
  /config/joamy_backup/ gesichert. Es wird nur angehängt, nie etwas ersetzt.
- Bei Dashboards im YAML-Modus sagt das Add-on das klar, statt still zu
  scheitern.
- 14 Meldungen waren nur auf Deutsch — sie liefen über das JavaScript und
  wurden von der Übersetzungsprüfung gar nicht erfasst. Jetzt alle
  zweisprachig, und die Prüfung schaut künftig auch dort hin.

## 0.1.55
- Die Add-on-Seite passt sich jetzt jedem Bildschirm an — vom kleinen Handy
  bis zum grossen Monitor. Vorher wurde sie auf schmalen Geraeten seitlich
  abgeschnitten: Man musste wischen, und alles wirkte zu gross.
- Der Kopplungscode waechst mit der Bildschirmbreite mit, statt eine feste
  Groesse zu erzwingen.
- Auf dem Rechner sieht alles unveraendert aus.

## 0.1.54
- Nach dem einmaligen Neustart verschwindet der Hinweis „Einmal neu starten"
  jetzt sofort, sobald du die Add-on-Seite öffnest — vorher konnte er noch bis
  zu zwei Minuten stehen bleiben, obwohl längst alles fertig war.
- Im Text steht jetzt dabei, dass Home Assistant nach dem Neustart noch einen
  kurzen Moment braucht. Damit sieht es nicht mehr wie ein Fehler aus.
- **Neuer Hinweis: Lade dein Dashboard einmal neu (F5)**, damit eine frisch
  installierte Karte unter „Karte hinzufügen" auftaucht. Home Assistant liest
  die Liste der Karten nur beim Laden der Seite — ohne Neuladen wartest du
  vergeblich, egal wie lange.
- Solange noch etwas eingerichtet wird, sieht das Add-on alle 8 Sekunden nach
  statt nur einmal pro Minute. Im Normalbetrieb bleibt es beim eingestellten Takt.
