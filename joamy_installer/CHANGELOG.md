## 0.1.62
- Der Hinweis unter dem Trinkgeld-Knopf stimmte nicht mehr: Es öffnet sich
  kein neuer Tab, das Fenster geht hier auf.

## 0.1.61
- **Trinkgeld geht jetzt direkt im Add-on** — ohne dass sich eine fremde
  Seite öffnet. Ein Tippen auf den gelben Knopf blendet das Fenster von Buy
  me a coffee über der Seite ein; Betrag eingeben, fertig. Der schwebende
  Knopf unten rechts ist dafür verschwunden, alles läuft über den Knopf in
  der Trinkgeld-Karte.
- Der Knopf leuchtet dezent gelb, damit man ihn findet.
- Ohne Internet bleibt er ein gewöhnlicher Link auf buymeacoffee.com —
  lieber die Seite öffnen als gar nichts tun.

## 0.1.60
- **Der Trinkgeld-Knopf unten rechts war da, aber unsichtbar.** Er wurde erst
  nachträglich eingehängt — und das Widget baut nur dann etwas, wenn es beim
  Aufbau der Seite dabei ist. Jetzt erscheint er wirklich.

## 0.1.59
- **Auf dem Handy lief die Seite seitlich aus dem Bild.** Schuld war die
  Style-Angabe bei den installierten Bausteinen: Sie stand als eine einzige
  lange Kette („almanach,comic,frost,…") in einer Zeile, die nirgends umbrach,
  und hat die ganze Seite auf 654 Pixel aufgezogen — deutlich breiter als
  jedes Handy. Jetzt bricht sie um, und die Seite passt sich wieder von
  selbst an jede Bildschirmbreite an.
- Auch die Geräteliste in den Konfiguratoren passt jetzt auf sehr schmale
  Geräte: Entitäts-Namen wie „light.wohnzimmer_deckenspots_hinten" sind ein
  einziges langes Wort und schoben die Seite auf 320-Pixel-Displays hinaus.

## 0.1.58
- **Auf Englisch stand an einigen Stellen Deutsch.** Alles, was erst beim
  Bedienen entsteht, wurde einmal übersetzt und danach nie wieder — wer
  hinterher auf Englisch umschaltete, behielt deutsche Knöpfe. Ebenso die
  Beschriftungen, die man nicht sieht, aber hört (Vorlesehilfen), und die
  grauen Beispieltexte in Eingabefeldern. Jetzt wandert alles mit.
- **Beleuchtung und Jalousie: „als freie Einzelkarte" ist jetzt die
  Voreinstellung.** Wer lieber eine Kachel mit Überschrift und Hintergrund
  möchte, stellt das weiterhin um.
- **Trinkgeld-Knopf unten rechts.** Wem JoAmy gefällt, kann von jeder Seite
  aus etwas dalassen — die Bausteine bleiben kostenlos.

## 0.1.57
- **„In mein Dashboard legen" hat nicht funktioniert — behoben.** Die Karte
  wurde eingetragen, gespeichert, und im Dashboard war trotzdem nichts.
  Grund: In den neueren Ansichten mit Abschnitten („Sections") zeigt Home
  Assistant nur, was in einem Abschnitt liegt — die Karte lag daneben und
  war damit unsichtbar. Sie kommt jetzt in den Abschnitt.
- **Der Knopf steht jetzt bei JEDEM Baustein.** Vorher hing er an einem
  Kopieren-Knopf, den nur drei Konfiguratoren haben — sichtbar war er
  dadurch nur bei Beleuchtung und Jalousie. Jetzt hängt er unter jedem
  angezeigten Code.
- **Beleuchtung und Jalousie werden getrennt eingerichtet.** Bisher waren
  beide in einer Maske: eine Liste für Lampen, eine für Rollläden, ein
  Knopf, zwei Codes. Jetzt hat jedes seinen eigenen Abschnitt mit eigener
  Auswahl, eigenem Style und eigenem Code — wie jeder andere Baustein auch.
- Wird ein Dashboard automatisch von Home Assistant erzeugt (das ist bei
  „Übersicht" der Normalfall), sagt das Add-on das jetzt klar, statt von
  YAML zu reden. Darin lässt sich nichts dauerhaft ablegen — ein eigenes
  Dashboard schon.
- Eine zweite Karte derselben Art lässt sich wieder eintragen. Vorher
  genügte irgendeine Lichtkarte in der Ansicht, damit jede weitere still
  abgelehnt wurde („liegt dort schon").
- Der fertige Code wird jetzt serverseitig mit einer richtigen
  YAML-Bibliothek gelesen statt im Browser Zeile für Zeile — verschachtelte
  Angaben (etwa beim Button-Baukasten) kamen dabei verstümmelt an.

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
