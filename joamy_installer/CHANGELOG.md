# Änderungsprotokoll

## 0.1.15

- **Musik-Karte einrichten:** neuer Abschnitt — Lautsprecher anhaken, benennen und den
  Musik-Griff an einem nachgebauten Dashboard genau dorthin schieben, wo er später am
  Bildschirmrand sitzen soll. Daraus entsteht der fertige Karten-Code zum Einfügen.

## 0.1.14

- **JoAmy startet dein Home Assistant nie neu — und kann es nicht mehr.** Der
  Neustart-Aufruf ist aus dem Code entfernt, und mit ihm die Berechtigung
  (`hassio_api`/`hassio_role`), die ihn überhaupt möglich machte. Die Option
  `auto_neustart` entfällt ersatzlos. Sollte ein Baustein wider Erwarten nicht im
  laufenden Betrieb laden, erscheint nur eine Meldung — den Zeitpunkt bestimmst du.
- **Style-Auswahl zeigt nur deine gekauften Styles** (vorher standen alle neun zur
  Wahl, obwohl die Karte ungekaufte ohnehin nicht freischaltet).

## 0.1.13

- **Kein automatischer Neustart mehr.** Home Assistant lädt neue Bausteine im
  laufenden Betrieb — das Add-on stößt nur noch die Einrichtung an. Sollte das in
  einem Setup wider Erwarten klemmen, erscheint eine Meldung in Home Assistant;
  **wann** neu gestartet wird, entscheidest du.

## 0.1.12

- **Neue Oberfläche** im JoAmy-Look der Website (dunkel, Bronze, Haus-Logo) — mit
  **Sprachumschalter DE/EN**.
- **Ehrlicher Status:** „nicht erreichbar" steht nur noch da, wenn der Lizenz-Server
  wirklich schweigt. Antwortet er und weist etwas ab, sagt das Add-on was los ist
  und was zu tun ist.
- **Kamera-Karte einrichten:** Anzahl der zu ladenden Ereignisse ist jetzt
  einstellbar; die Klingel-Kamera wird aus deinen angehakten Kameras gewählt; das
  Namensfeld ist entfallen (die Karte trägt vorne keinen Namen mehr).
- **Kein Hineinzoomen mehr** beim Antippen in der Companion-App.

## 0.1.11

- **Besitznachweis:** Das Add-on weist sich beim Lizenz-Server aus. Nach einer
  Neuinstallation findet es seine Kopplung von selbst wieder — ohne neuen Code.

## 0.1.10

- Kamera-Karten-Konfigurator in der Add-on-Seite: Kameras auswählen, Style
  wählen, fertigen Karten-Code kopieren.

## 0.1.9

- Erste Fassung im Add-on-Store: einmal koppeln, danach installieren sich Käufe
  von joamy.uk automatisch (inkl. Sicherung der Vorgängerversion).
