"""JoAmy Installer — Ingress-Oberfläche (eine Seite, warmweiß/bronze).

WICHTIG: Der Supervisor liefert die Seite unter
    /api/hassio_ingress/<token>/
aus und STREIFT dieses Präfix ab, bevor die Anfrage hier ankommt — unsere
Routen sind also "/", "/status", "/suchen". Damit Links und fetch()-Aufrufe
durch den Proxy funktionieren, benutzt die Seite AUSSCHLIESSLICH RELATIVE
Pfade ("status", "suchen"); der mitgeschickte Header X-Ingress-Path wird
nicht gebraucht. Kein eigenes Login — die Ingress-Session schützt.
"""
from __future__ import annotations

import json
import logging
import os

from aiohttp import web

from kern import Installer, LOG_PUFFER

LOG = logging.getLogger("joamy.oberflaeche")

# Die Hausschrift der Website (Inter Tight, variabel) liegt IM Add-on und wird
# unter "schrift.woff2" ausgeliefert — die Ingress-Seite darf nichts aus dem
# Internet nachladen, soll aber exakt wie joamy.uk aussehen.
SCHRIFT_DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inter-tight.woff2")

SEITE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JoAmy Installer</title>
<style>
  /* Optik = joamy.uk (dunkle Bühne, Bronze-Akzent, Inter Tight). Tokens 1:1 aus
     website/assets/css/base.css übernommen — wer die Seite sieht, erkennt JoAmy.
     Die Schrift liegt IM Add-on (Route "schrift.woff2"), kein Netz-Zugriff. */
  @font-face {
    font-family: 'Inter Tight'; font-style: normal; font-weight: 400 600;
    font-display: swap; src: url(schrift.woff2) format('woff2');
  }
  :root {
    --nacht: #050403; --nacht-karte: #14110e; --nacht-vertieft: #0d0b09;
    --nacht-linie: #2a251f;
    --tinte-1: #f5f1ec; --tinte-2: #c9c2b8; --tinte-3: #8d857a;
    --akzent: #c29a6c;
    --gruen: #6ea87f; --rot: #d4705e;
    --r-12: 12px; --r-20: 20px; --r-pill: 999px;
    --font: 'Inter Tight', 'Inter', -apple-system, 'Segoe UI', system-ui, sans-serif;
    --mono: 'SFMono-Regular', 'Cascadia Mono', Consolas, ui-monospace, monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  [hidden] { display: none !important; }
  /* Kein Auto-Zoom in der Companion-App: (1) iOS zoomt beim Antippen eines
     Formularfelds mit Schrift < 16px hinein und kommt nicht mehr heraus,
     (2) ein schneller Doppeltipp auf Knöpfe löst Doppeltipp-Zoom aus.
     touch-action: manipulation schaltet NUR den Doppeltipp-Zoom ab —
     Auf-/Zuziehen mit zwei Fingern bleibt möglich. */
  html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
  * { touch-action: manipulation; }
  body {
    background: var(--nacht); color: var(--tinte-1);
    font: 400 16px/1.55 var(--font);
    -webkit-font-smoothing: antialiased;
    padding: 22px 16px 44px;
    overflow-x: hidden;             /* nichts schiebt die Seite seitlich raus */
    /* derselbe warme Schimmer wie auf der Landing-Bühne */
    background-image: radial-gradient(120% 60% at 50% -10%, rgba(194, 154, 108, .10), transparent 62%);
    background-repeat: no-repeat;
  }
  input, select, textarea, button { font-family: inherit; font-size: 16px; }  /* < 16px ⇒ iOS-Zoom */
  .rahmen { max-width: 720px; margin: 0 auto; display: grid; gap: 16px; }
  /* Wortmarke wie in der Website-Nav: Haus-Icon + fetter Schriftzug */
  .wortmarke { display: inline-flex; align-items: center; gap: 9px; text-decoration: none;
               color: var(--tinte-1); font-weight: 600; font-size: 21px; letter-spacing: -.02em; }
  .wortmarke svg { width: 26px; height: 26px; flex: 0 0 auto; display: block; }
  .kopfzeile { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  /* Sprachumschalter DE|EN — 1:1 die Optik der Website-Nav */
  .lang-switch { display: inline-flex; gap: 2px; flex: 0 0 auto; padding: 3px;
                 border-radius: var(--r-pill); border: 1px solid var(--nacht-linie);
                 background: rgba(5, 4, 3, .55); }
  .lang-opt { border: none; background: transparent; color: var(--tinte-3);
              font-size: 12.5px; font-weight: 600; letter-spacing: .04em; line-height: 1;
              padding: 6px 11px; border-radius: var(--r-pill); width: auto;
              transition: background .2s, color .2s; }
  .lang-opt:hover { color: var(--tinte-1); background: transparent; transform: none; }
  .lang-opt.aktiv { background: var(--tinte-1); color: var(--nacht); }
  header .eyebrow { display: block; font-size: 12.5px; font-weight: 600; letter-spacing: .12em;
                    text-transform: uppercase; color: var(--akzent); margin: 20px 0 8px; }
  header h1 { font-size: clamp(30px, 7.5vw, 40px); font-weight: 600;
              letter-spacing: -.03em; line-height: 1.05; margin-bottom: 10px; }
  header p { color: var(--tinte-3); font-size: 15px; }
  .karte {
    background: var(--nacht-karte); border: 1px solid var(--nacht-linie);
    border-radius: var(--r-20); padding: 20px 20px;
  }
  .karte h2 {
    font-size: 12.5px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
    color: var(--akzent); margin-bottom: 12px;
  }
  #code {
    font: 600 2.6rem/1.1 var(--mono); letter-spacing: .1em;
    color: var(--tinte-1); text-align: center; padding: 6px 0 2px;
  }
  .code-hinweis { text-align: center; color: var(--tinte-2); font-size: 14.5px; }
  .code-hinweis b { color: var(--akzent); font-weight: 600; }
  #code-rest { text-align: center; font-size: 13px; color: var(--tinte-3); margin-top: 6px; }
  .zeile { display: flex; justify-content: space-between; gap: 12px; font-size: 14.5px;
           padding: 8px 0; border-bottom: 1px solid var(--nacht-linie); }
  .zeile:last-child { border-bottom: 0; }
  .zeile > span:first-child { color: var(--tinte-3); }
  .zeile .wert { text-align: right; color: var(--tinte-1); }
  .punkt { display: inline-block; width: .6em; height: .6em; border-radius: 50%;
           margin-right: .45em; background: #4a443c; vertical-align: baseline; }
  .punkt.gut { background: var(--gruen); } .punkt.schlecht { background: var(--rot); }
  ul#bausteine { list-style: none; display: grid; gap: 10px; }
  ul#bausteine li {
    border: 1px solid var(--nacht-linie); border-radius: var(--r-12); padding: 12px 14px;
    display: grid; gap: 3px; background: var(--nacht-vertieft);
  }
  ul#bausteine .titel { font-size: 16px; font-weight: 600; }
  ul#bausteine .titel .theme {
    font: 12px/1.6 var(--mono); color: var(--akzent);
    border: 1px solid var(--nacht-linie); border-radius: var(--r-pill);
    padding: 1px 9px; margin-left: 8px; vertical-align: middle;
  }
  ul#bausteine .fuer { color: var(--tinte-2); font-size: 14px; }
  ul#bausteine .meta { font: 12.5px/1.5 var(--mono); color: var(--tinte-3); }
  #leer { color: var(--tinte-3); font-size: 14.5px; }
  /* Knöpfe = .btn-hell der Website (heller Block auf Nacht) — bewusst NUR in den
     Karten, damit der Sprachumschalter im Kopf davon unberührt bleibt. */
  .karte button {
    font-weight: 600; color: var(--nacht); background: var(--tinte-1);
    border: 1px solid transparent; border-radius: var(--r-pill);
    padding: 13px 24px; cursor: pointer; width: 100%;
    transition: transform .2s cubic-bezier(.25,.1,.25,1), background .2s, border-color .2s, opacity .2s;
  }
  .karte button:hover { background: #ffffff; transform: translateY(-1px); }
  .karte button:active { transform: translateY(0); }
  .karte button:disabled { opacity: .45; cursor: wait; transform: none; }
  .karte button.ghost { background: transparent; color: var(--tinte-2); border-color: var(--nacht-linie); }
  .karte button.ghost:hover { background: transparent; color: var(--tinte-1); border-color: var(--akzent); }
  #such-meldung { text-align: center; margin-top: 10px; font-size: 14px; color: var(--tinte-3); min-height: 1.4em; }
  pre#logs {
    font: 12.5px/1.55 var(--mono); color: var(--tinte-3);
    background: var(--nacht-vertieft); border: 1px solid var(--nacht-linie); border-radius: var(--r-12);
    padding: 12px 14px; overflow-x: auto; max-height: 260px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word;
  }
  #fehler { color: var(--rot); font-size: 14px; margin-top: 10px; }
  #server-hinweis { margin-top: 12px; padding: 11px 13px; border-radius: var(--r-12); font-size: 14px;
    background: rgba(194, 154, 108, .09); border: 1px solid rgba(194, 154, 108, .32); color: var(--tinte-2); }
  /* Kamera-Konfigurator */
  .kf-intro { color: var(--tinte-3); font-size: 14.5px; margin-bottom: 14px; }
  #kf-body { display: grid; gap: 18px; margin-top: 16px; }
  .kf-abschnitt { display: grid; gap: 8px; min-width: 0; }
  .kf-titel { font-size: 12px; font-weight: 600; letter-spacing: .1em;
              text-transform: uppercase; color: var(--tinte-3); }
  #kf-cams { display: grid; gap: 8px; }
  .kf-cam { display: grid; grid-template-columns: auto minmax(0, 1fr) minmax(0, 1.2fr); gap: 10px;
            align-items: center; max-width: 100%;
            border: 1px solid var(--nacht-linie); border-radius: var(--r-12);
            padding: 10px 12px; background: var(--nacht-vertieft); }
  .kf-cam .eid { font: 12.5px/1.4 var(--mono); color: var(--tinte-3); min-width: 0;
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kf-cam input[type=text] { width: 100%; min-width: 0; }
  input[type=checkbox] { width: 19px; height: 19px; accent-color: var(--akzent); flex: 0 0 auto; }
  .kf-abschnitt label { display: flex; align-items: center; gap: 9px; min-width: 0; font-size: 15px; }
  .kf-abschnitt label b { font-weight: 600; }
  /* NICHT `font: inherit` — die Felder sitzen in 14px-Labels und lägen damit
     unter 16px ⇒ iOS zoomt beim Antippen hinein. Größe hier fest setzen. */
  select, input[type=text], input[type=number] {
    font-family: inherit; font-size: 16px; padding: 10px 12px; border: 1px solid var(--nacht-linie);
    border-radius: var(--r-12); background: var(--nacht-vertieft); color: var(--tinte-1);
    width: 100%; min-width: 0; max-width: 100%; appearance: none; -webkit-appearance: none; }
  select { background-image: linear-gradient(45deg, transparent 50%, var(--tinte-3) 50%),
                             linear-gradient(135deg, var(--tinte-3) 50%, transparent 50%);
           background-position: right 15px top 52%, right 10px top 52%;
           background-size: 5px 5px, 5px 5px; background-repeat: no-repeat; padding-right: 30px; }
  select:focus, input:focus { outline: none; border-color: var(--akzent); }
  #kf-ev-body, #kf-tk-body { display: grid; gap: 10px; margin-top: 8px; padding-left: 28px; min-width: 0; }
  #kf-ev-body .hinweis { color: var(--tinte-3); font-size: 13px; }
  #kf-ev-anzahl { width: 7em; }
  #kf-tk-body label, #kf-ev-body label { display: grid; gap: 5px; align-items: start;
                                         font-size: 14px; color: var(--tinte-2); min-width: 0; }
  #kf-ergebnis { display: grid; gap: 12px; }
  pre#kf-yaml { font: 13px/1.6 var(--mono); color: var(--tinte-2);
    background: var(--nacht-vertieft); border: 1px solid var(--nacht-linie); border-radius: var(--r-12);
    padding: 13px 15px; overflow-x: auto; white-space: pre; }
  #kf-meldung { text-align: center; font-size: 14px; color: var(--gruen); min-height: 1.3em; }
  /* Musik-Karte: Platzierung am nachgebauten Dashboard */
  .mk-hinweis { padding: 11px 13px; margin-bottom: 12px; border-radius: var(--r-12); font-size: 13.5px;
    line-height: 1.5; background: rgba(194, 154, 108, .09); border: 1px solid rgba(194, 154, 108, .32);
    color: var(--tinte-2); }
  .mk-hinweis b { color: var(--tinte-1); font-weight: 600; }
  #mk-players { display: grid; gap: 8px; }
  .mk-buehne { display: grid; gap: 8px; justify-items: center; }
  .mk-schirm { position: relative; width: 100%; max-width: 300px; aspect-ratio: 9 / 16;
    border-radius: 18px; border: 1px solid var(--nacht-linie); background: var(--nacht-vertieft);
    overflow: hidden; touch-action: none; user-select: none; }
  .mk-kopf { height: 26px; margin: 8px 10px 6px; border-radius: 6px; background: rgba(255,255,255,.05); }
  .mk-karten { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 0 10px; }
  .mk-dummy { height: 44px; border-radius: 8px; background: rgba(255,255,255,.045);
    border: 1px solid rgba(255,255,255,.05); grid-column: span 2; }
  .mk-dummy.klein { grid-column: span 1; height: 34px; }
  .mk-griff { position: absolute; width: 22px; height: 62px; display: grid; place-items: center;
    background: var(--akzent); color: var(--nacht); font-size: 13px; cursor: grab;
    box-shadow: 0 2px 10px rgba(0,0,0,.45); touch-action: none; }
  .mk-griff:active { cursor: grabbing; }
  .mk-lage { font: 12.5px var(--mono); color: var(--tinte-3); }
  footer { text-align: center; color: var(--tinte-3); font-size: 13px; padding-top: 4px; }
  footer a { color: var(--akzent); text-decoration: none; }
</style>
</head>
<body>
<div class="rahmen">
  <header>
    <div class="kopfzeile">
      <a class="wortmarke" href="https://joamy.uk" target="_blank" rel="noopener">
        <svg viewBox="0 0 100 100" fill="none" aria-hidden="true">
          <path d="M20 88 V42 L50 13 L80 42 V88 Z" stroke="currentColor" stroke-width="9"
                stroke-linejoin="round" stroke-linecap="round"/>
          <g stroke="#C29A6C" stroke-width="5" stroke-linecap="round">
            <line x1="50" y1="63" x2="36" y2="48"/><line x1="50" y1="63" x2="66" y2="51"/></g>
          <g fill="#C29A6C"><circle cx="50" cy="63" r="8"/><circle cx="36" cy="48" r="5.5"/>
            <circle cx="66" cy="51" r="5.5"/></g>
        </svg><span>JoAmy</span></a>
      <div class="lang-switch" role="group" aria-label="Sprache / Language">
        <button type="button" class="lang-opt" data-lang="de">DE</button>
        <button type="button" class="lang-opt" data-lang="en">EN</button>
      </div>
    </div>
    <span class="eyebrow" data-i18n>Für Home Assistant</span>
    <h1 data-i18n>Installer</h1>
    <p data-i18n>Einmal koppeln — deine Käufe ziehen ab dann von selbst bei dir ein.</p>
  </header>

  <section class="karte">
    <h2 data-i18n>Kopplungscode</h2>
    <div id="code">—</div>
    <p class="code-hinweis" data-i18n>Diesen Code beim Kauf auf <b>joamy.uk</b> eingeben
       (oder auf <b>joamy.uk/verbinden</b>), um dein Zuhause mit JoAmy zu verbinden.</p>
    <p id="code-rest"></p>
  </section>

  <section class="karte">
    <h2 data-i18n>Status</h2>
    <div class="zeile"><span data-i18n>Lizenz-Server</span><span class="wert" id="st-server">—</span></div>
    <div id="server-hinweis" hidden></div>
    <div class="zeile"><span data-i18n>Registriert</span><span class="wert" id="st-reg">—</span></div>
    <div class="zeile"><span data-i18n>Letzte Suche</span><span class="wert" id="st-poll">—</span></div>
    <div class="zeile"><span data-i18n>Neustart von Home Assistant</span><span class="wert" id="st-neustart">—</span></div>
    <div id="fehler"></div>
  </section>

  <section class="karte">
    <h2 data-i18n>Installierte Bausteine</h2>
    <p id="leer" data-i18n>Noch nichts eingezogen — nach dem Koppeln erscheint dein erster Kauf hier von ganz allein.</p>
    <ul id="bausteine"></ul>
  </section>

  <section class="karte">
    <h2 data-i18n>Von Hand</h2>
    <button id="suchen" data-i18n>Jetzt nach Käufen suchen</button>
    <div id="such-meldung"></div>
  </section>

  <section class="karte" id="konfig-karte">
    <h2 data-i18n>Kamera-Karte einrichten</h2>
    <p class="kf-intro" data-i18n>Wähle deine Kameras — wir bauen dir den fertigen Code. Den fügst du beim
      Hinzufügen der Karte („Karte hinzufügen“ → ganz unten „Manuell“) einfach ein.</p>
    <button id="kf-laden" type="button" data-i18n>Meine Kameras laden</button>
    <div id="kf-body" hidden>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Kameras (anhaken + Namen vergeben)</span>
        <div id="kf-cams"></div>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="kf-stil" data-i18n>Style (kannst du später jederzeit über 🎨 wechseln)</label>
        <span id="kf-stil-hinweis" class="hinweis" hidden></span>
        <select id="kf-stil">
          <option value="skizze">Skizze</option><option value="comic">Comic</option>
          <option value="pinnwand">Pinnwand</option><option value="frost">Frost</option>
          <option value="terminal">Terminal</option><option value="riso">Riso</option>
          <option value="almanach">Almanach</option><option value="keramik">Keramik</option>
          <option value="pigment">Pigment</option>
        </select>
      </div>
      <div class="kf-abschnitt">
        <label><input type="checkbox" id="kf-tk-an"> <span data-i18n><b>Türklingel</b> — Meldung „Jemand klingelt gerade“</span></label>
        <div id="kf-tk-body" hidden>
          <label><span data-i18n>Klingel-Sensor (schaltet beim Klingeln auf „an“)</span>
            <select id="kf-tk-sensor"></select></label>
          <label><span data-i18n>Welche deiner Kameras soll beim Klingeln erscheinen?</span>
            <select id="kf-tk-cam"></select></label>
          <label><span data-i18n>Tür-öffnen-Knopf (optional)</span>
            <select id="kf-tk-knopf"><option value="">— keiner —</option></select></label>
        </div>
      </div>
      <div class="kf-abschnitt">
        <label><input type="checkbox" id="kf-ev-an" checked> <span data-i18n>„Letzte Ereignisse“ anzeigen (sofern die Kamera Aufzeichnungen liefert)</span></label>
        <div id="kf-ev-body">
          <label><span data-i18n>Wie viele der letzten Ereignisse laden?</span>
            <input id="kf-ev-anzahl" type="number" min="1" max="100" step="1" value="20"></label>
          <span class="hinweis" data-i18n>Mehr Ereignisse heißt längeres Laden — 20 ist ein guter Wert.</span>
        </div>
      </div>
      <button id="kf-erzeugen" type="button" data-i18n>Code erzeugen</button>
      <div id="kf-ergebnis" hidden>
        <div class="kf-abschnitt">
          <span class="kf-titel" data-i18n>Fertiger Code — beim Hinzufügen der Karte einfügen</span>
          <pre id="kf-yaml"></pre>
        </div>
        <button id="kf-kopieren" type="button" data-i18n>Code kopieren</button>
        <div id="kf-meldung"></div>
      </div>
    </div>
  </section>

  <section class="karte" id="media-karte">
    <h2 data-i18n>Musik-Karte einrichten</h2>
    <p class="kf-intro" data-i18n>Wähle deine Lautsprecher und schiebe den Musik-Griff dorthin,
      wo er auf deinem Bildschirm sitzen soll. Am Ende bekommst du den fertigen Code zum Einfügen.</p>
    <div class="mk-hinweis" data-i18n><b>Music Assistant wird gebraucht.</b> Zum Suchen und Abspielen
      von Musik braucht die Karte das Add-on „Music Assistant“. Ohne es kannst du nur steuern,
      was gerade läuft.</div>
    <button id="mk-laden" type="button">Meine Lautsprecher laden</button>
    <div id="mk-body" hidden>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Lautsprecher (anhaken + Namen vergeben)</span>
        <div id="mk-players"></div>
      </div>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Wo soll der Musik-Griff sitzen?</span>
        <p class="hinweis" data-i18n>Die Musik-Schublade liegt über deinem Dashboard — zu sehen ist
          nur ein schmaler Griff am Bildschirmrand. Zieh ihn unten an die Stelle, an der er dich am
          wenigsten stört; ein Tipp darauf zieht die Musik heraus. Das gilt auf jeder Seite deines
          Dashboards, egal wie viele Karten du hast.</p>
        <div id="mk-buehne" class="mk-buehne">
          <div class="mk-schirm">
            <div class="mk-kopf"></div>
            <div class="mk-karten">
              <div class="mk-dummy"></div><div class="mk-dummy"></div>
              <div class="mk-dummy klein"></div><div class="mk-dummy klein"></div>
              <div class="mk-dummy"></div>
            </div>
            <div id="mk-griff" class="mk-griff" title="Ziehen">♪</div>
          </div>
          <div class="mk-lage"><span id="mk-lage-text">rechts, mittig</span></div>
        </div>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="mk-stil" data-i18n>Style</label>
        <span id="mk-stil-hinweis" class="hinweis" hidden></span>
        <select id="mk-stil"></select>
      </div>
      <button id="mk-erzeugen" type="button" data-i18n>Code erzeugen</button>
      <div id="mk-ergebnis" hidden>
        <div class="kf-abschnitt">
          <span class="kf-titel" data-i18n>Fertiger Code — beim Hinzufügen der Karte einfügen</span>
          <pre id="mk-yaml"></pre>
        </div>
        <button id="mk-kopieren" type="button" data-i18n>Code kopieren</button>
        <div id="mk-meldung"></div>
      </div>
    </div>
  </section>

  <section class="karte">
    <h2 data-i18n>Logbuch</h2>
    <pre id="logs">—</pre>
  </section>

  <footer>JoAmy · <a href="https://joamy.uk" target="_blank" rel="noopener">joamy.uk</a></footer>
</div>

<script>
// Erststand kommt server-seitig mit — der Code steht damit schon im HTML.
var stand = __STATUS_JSON__;

function el(id) { return document.getElementById(id); }

/* ---------- Sprache DE/EN — dieselbe Mechanik wie web-i18n.js der Website:
   Schlüssel ist der normalisierte DEUTSCHE Text, der Wert die englische Fassung
   (darf HTML enthalten). Kein Treffer ⇒ Deutsch bleibt stehen. Gemerkt wird die
   Wahl in localStorage; ohne Wahl entscheidet die Browsersprache. ---------- */
var UEB = {
  'Für Home Assistant': 'For Home Assistant',
  'Einmal koppeln — deine Käufe ziehen ab dann von selbst bei dir ein.':
    'Pair once — from then on your purchases move in all by themselves.',
  'Kopplungscode': 'Pairing code',
  'Diesen Code beim Kauf auf joamy.uk eingeben (oder auf joamy.uk/verbinden), um dein Zuhause mit JoAmy zu verbinden.':
    'Enter this code when buying on <b>joamy.uk</b> (or at <b>joamy.uk/verbinden</b>) to connect your home with JoAmy.',
  'Status': 'Status',
  'Lizenz-Server': 'License server',
  'Registriert': 'Registered',
  'Letzte Suche': 'Last check',
  'Neustart von Home Assistant': 'Restarting Home Assistant',
  'wird von JoAmy nie ausgelöst': 'never triggered by JoAmy',
  'einmal empfohlen — wann, entscheidest du': 'recommended once — you decide when',
  'Noch kein Kamera-Baustein gekauft — hier stehen später nur deine Styles.':
    'No camera building block bought yet — later only your own styles appear here.',
  'Installierte Bausteine': 'Installed building blocks',
  'Noch nichts eingezogen — nach dem Koppeln erscheint dein erster Kauf hier von ganz allein.':
    'Nothing has moved in yet — after pairing, your first purchase shows up here all by itself.',
  'Von Hand': 'By hand',
  'Jetzt nach Käufen suchen': 'Check for purchases now',
  'Kamera-Karte einrichten': 'Set up the camera card',
  'Wähle deine Kameras — wir bauen dir den fertigen Code. Den fügst du beim Hinzufügen der Karte („Karte hinzufügen“ → ganz unten „Manuell“) einfach ein.':
    'Pick your cameras — we build the finished code for you. Just paste it when adding the card (“Add card” → “Manual” at the very bottom).',
  'Kameras (anhaken + Namen vergeben)': 'Cameras (tick them + give them names)',
  'Style (kannst du später jederzeit über 🎨 wechseln)': 'Style (you can switch anytime later via 🎨)',
  'Türklingel — Meldung „Jemand klingelt gerade“': '<b>Doorbell</b> — “Someone is ringing” message',
  'Klingel-Sensor (schaltet beim Klingeln auf „an“)': 'Doorbell sensor (switches to “on” when someone rings)',
  'Welche deiner Kameras soll beim Klingeln erscheinen?': 'Which of your cameras should appear when someone rings?',
  'Tür-öffnen-Knopf (optional)': 'Door-release button (optional)',
  '„Letzte Ereignisse“ anzeigen (sofern die Kamera Aufzeichnungen liefert)':
    'Show “latest events” (if the camera provides recordings)',
  'Wie viele der letzten Ereignisse laden?': 'How many of the latest events should be loaded?',
  'Mehr Ereignisse heißt längeres Laden — 20 ist ein guter Wert.':
    'More events means longer loading — 20 is a good value.',
  'Code erzeugen': 'Generate code',
  'Fertiger Code — beim Hinzufügen der Karte einfügen': 'Finished code — paste it when adding the card',
  'Code kopieren': 'Copy code',
  'Logbuch': 'Log',
  /* --- vom Skript erzeugte Texte --- */
  'Meine Kameras laden': 'Load my cameras',
  'Kameras neu laden': 'Reload cameras',
  'lädt …': 'loading …',
  '— wählen —': '— choose —',
  '— keiner —': '— none —',
  '— erst oben eine Kamera anhaken —': '— tick a camera above first —',
  'Name': 'Name',
  'erreichbar': 'reachable',
  'antwortet, meldet ein Problem': 'responds, reports a problem',
  'nicht erreichbar': 'unreachable',
  'ja': 'yes',
  'noch nicht': 'not yet',
  'noch keine': 'none yet',
  'an': 'on',
  'aus': 'off',
  ' · Neustart steht noch aus': ' · restart still pending',
  'Zuletzt gemeldet: ': 'Last reported: ',
  'Gebacken für ': 'Baked for ',
  'Version ': 'Version ',
  ' · installiert ': ' · installed ',
  'Noch etwa {n} Minuten gültig — danach holt sich diese Seite automatisch einen frischen.':
    'Valid for about {n} more minutes — after that this page fetches a fresh one automatically.',
  'Noch kein Code — der Lizenz-Server hat noch keinen geliefert.':
    'No code yet — the license server has not delivered one.',
  'Suche läuft …': 'Checking …',
  'Gefunden und installiert: ': 'Found and installed: ',
  'Alles aktuell — kein neuer Kauf gefunden.': 'Everything up to date — no new purchase found.',
  'Das hat nicht geklappt: ': 'That did not work: ',
  'Das hat nicht geklappt — Verbindung prüfen.': 'That did not work — please check the connection.',
  'unbekannter Fehler': 'unknown error',
  'Keine camera.*-Entitäten gefunden': 'No camera.* entities found',
  '. (Kameras erst in Home Assistant einrichten.)': '. (Set your cameras up in Home Assistant first.)',
  'Konnte Home Assistant nicht erreichen.': 'Could not reach Home Assistant.',
  '# Bitte mindestens eine Kamera anhaken.': '# Please tick at least one camera.',
  'Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.':
    'Copied! Now paste it under “Add card” → “Manual”.',
  /* --- Hinweise, die der Server (kern.py) auf Deutsch liefert --- */
  'Dieses Add-on ist älter als der Lizenz-Server. Bitte im Add-on-Store auf die neueste Version aktualisieren — danach klappt es von selbst.':
    'This add-on is older than the license server. Please update it to the newest version in the add-on store — after that it works by itself.',
  'Der Lizenz-Server hat gerade eine Störung. Das Add-on versucht es weiter.':
    'The license server is having trouble right now. The add-on keeps trying.'
};
function norm(s) { return String(s == null ? '' : s).replace(/\\s+/g, ' ').trim(); }
var LOOKUP = {};
for (var _k in UEB) { if (Object.prototype.hasOwnProperty.call(UEB, _k)) LOOKUP[norm(_k)] = UEB[_k]; }
var sprache = (function () {
  var g = null;
  try { g = localStorage.getItem('joamy-addon-lang'); } catch (e) {}
  if (g === 'de' || g === 'en') return g;
  return String(navigator.language || 'de').toLowerCase().indexOf('en') === 0 ? 'en' : 'de';
})();
// wt(): deutscher Text rein, englischer zurück (sonst unverändert).
function wt(s) { if (sprache !== 'en') return s; var t = LOOKUP[norm(s)]; return t == null ? s : t; }
function elementRendern(e) {
  if (e.__i18nHtml === undefined) { e.__i18nHtml = e.innerHTML; e.__i18nKey = norm(e.textContent); }
  var ziel = e.__i18nHtml;
  if (sprache === 'en') { var v = LOOKUP[e.__i18nKey]; if (v != null) ziel = v; }
  if (e.innerHTML !== ziel) e.innerHTML = ziel;   // Deutsch = Default ⇒ DOM unangetastet
}
function spracheAnwenden() {
  var t = document.querySelectorAll('[data-i18n]');
  for (var i = 0; i < t.length; i++) elementRendern(t[i]);
  document.documentElement.setAttribute('lang', sprache);
  var o = document.querySelectorAll('.lang-opt');
  for (var j = 0; j < o.length; j++) {
    var an = o[j].getAttribute('data-lang') === sprache;
    o[j].classList.toggle('aktiv', an);
    o[j].setAttribute('aria-pressed', an ? 'true' : 'false');
  }
}
function setzeSprache(l) {
  sprache = (l === 'en') ? 'en' : 'de';
  try { localStorage.setItem('joamy-addon-lang', sprache); } catch (e) {}
  spracheAnwenden();
  male(letzterStand);                                  // Status-Zeilen neu beschriften
  if (window.__kfSprache) window.__kfSprache();         // Kamera-Konfigurator ebenso
}
(function () {
  var o = document.querySelectorAll('.lang-opt');
  for (var i = 0; i < o.length; i++) {
    o[i].addEventListener('click', function () { setzeSprache(this.getAttribute('data-lang')); });
  }
})();
function punkt(gut) {
  var s = document.createElement('span');
  s.className = 'punkt ' + (gut === true ? 'gut' : gut === false ? 'schlecht' : '');
  return s;
}
var letzterStand = stand;

function male(st) {
  letzterStand = st;
  el('code').textContent = st.kopplungscode || '— — —';
  el('code-rest').textContent = st.kopplungscode
    ? wt('Noch etwa {n} Minuten gültig — danach holt sich diese Seite automatisch einen frischen.')
        .replace('{n}', Math.max(1, Math.round(st.code_rest_s / 60)))
    : wt('Noch kein Code — der Lizenz-Server hat noch keinen geliefert.');

  // „nicht erreichbar" NUR wenn der Server wirklich stumm bleibt. Antwortet er und
  // weist die Anfrage ab (z. B. veraltetes Add-on → HTTP 403), sagen wir genau das.
  var zst = st.server_zustand
    || (st.server_ok === true ? 'ok' : st.server_ok === false ? 'weg' : 'unbekannt');
  var sv = el('st-server'); sv.textContent = '';
  sv.appendChild(punkt(zst === 'ok' ? true : zst === 'unbekannt' ? null : false));
  sv.appendChild(document.createTextNode(
    (zst === 'ok' ? wt('erreichbar')
      : zst === 'abgelehnt' ? wt('antwortet, meldet ein Problem')
      : zst === 'weg' ? wt('nicht erreichbar') : '…')
    + ' (' + st.server_url + ')'));
  var hw = el('server-hinweis');
  hw.textContent = st.server_hinweis ? wt(st.server_hinweis) : '';
  hw.hidden = !st.server_hinweis;

  var rg = el('st-reg'); rg.textContent = '';
  rg.appendChild(punkt(st.registriert));
  rg.appendChild(document.createTextNode(st.registriert ? wt('ja') : wt('noch nicht')));

  el('st-poll').textContent = st.letzter_poll || wt('noch keine');
  // Wir starten Home Assistant NIE selbst — das steht hier auch so.
  el('st-neustart').textContent = st.neustart_noetig
    ? wt('einmal empfohlen — wann, entscheidest du')
    : wt('wird von JoAmy nie ausgelöst');
  el('fehler').textContent = st.letzter_fehler ? wt('Zuletzt gemeldet: ') + st.letzter_fehler : '';

  var ul = el('bausteine'); ul.textContent = '';
  (st.bausteine || []).forEach(function (b) {
    var li = document.createElement('li');
    var t = document.createElement('div'); t.className = 'titel';
    t.textContent = (b.baustein || '?').charAt(0).toUpperCase() + (b.baustein || '?').slice(1);
    if (b.theme) {
      var chip = document.createElement('span'); chip.className = 'theme';
      chip.textContent = b.theme; t.appendChild(chip);
    }
    var f = document.createElement('div'); f.className = 'fuer';
    f.textContent = b.name ? wt('Gebacken für ') + b.name : '';
    var m = document.createElement('div'); m.className = 'meta';
    m.textContent = wt('Version ') + (b.version || '?')
      + (b.installiert_am ? wt(' · installiert ') + b.installiert_am.replace('T', ' ') : '');
    li.appendChild(t); if (b.name) li.appendChild(f); li.appendChild(m);
    ul.appendChild(li);
  });
  el('leer').style.display = (st.bausteine || []).length ? 'none' : '';

  el('logs').textContent = (st.logs || []).join('\\n') || '—';
  stileAnbieten(st);
}

/* Style-Auswahl im Kamera-Konfigurator: NUR die tatsächlich gekauften Styles.
   Alles andere wäre eine Attrappe — die Karte schaltet ungekaufte Styles ohnehin
   nicht frei. Vor dem ersten Kauf steht die volle Liste (zum Anschauen). */
var STIL_NAMEN = { skizze:'Skizze', comic:'Comic', pinnwand:'Pinnwand', frost:'Frost',
                   terminal:'Terminal', riso:'Riso', almanach:'Almanach',
                   keramik:'Keramik', pigment:'Pigment' };
var stilStand = null;
function stileAnbieten(st) {
  var sel = el('kf-stil'); if (!sel) return;
  var kam = (st.bausteine || []).filter(function (b) { return b.baustein === 'kamera'; })[0];
  var gekauft = (kam && kam.themes && kam.themes.length) ? kam.themes.slice()
    : (kam && kam.theme ? String(kam.theme).split(',') : []);
  gekauft = gekauft.filter(function (t) { return STIL_NAMEN[t]; });
  var signatur = gekauft.join(',') + '|' + sprache;
  if (signatur === stilStand) return;            // nichts Neues → DOM in Ruhe lassen
  stilStand = signatur;
  var vorher = sel.value;
  var liste = gekauft.length ? gekauft : Object.keys(STIL_NAMEN);
  sel.innerHTML = '';
  liste.forEach(function (t) {
    var o = document.createElement('option'); o.value = t; o.textContent = STIL_NAMEN[t];
    sel.appendChild(o);
  });
  sel.value = vorher;
  if (!sel.value) sel.value = liste[0];        // '' = kein Treffer ⇒ erster Style
  var hw = el('kf-stil-hinweis');
  if (hw) {
    hw.textContent = gekauft.length ? '' : wt('Noch kein Kamera-Baustein gekauft — hier stehen später nur deine Styles.');
    hw.hidden = !!gekauft.length;
  }
}

// Alle Pfade RELATIV — die Seite läuft hinter /api/hassio_ingress/<token>/.
function lade() {
  fetch('status', { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(male)
    .catch(function () {});
}

el('suchen').addEventListener('click', function () {
  var knopf = el('suchen'), meldung = el('such-meldung');
  knopf.disabled = true; meldung.textContent = wt('Suche läuft …');
  fetch('suchen', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function (erg) {
      meldung.textContent = erg.ok
        ? (erg.neu_installiert && erg.neu_installiert.length
            ? wt('Gefunden und installiert: ') + erg.neu_installiert.join(', ') + '.'
            : wt('Alles aktuell — kein neuer Kauf gefunden.'))
        : (wt('Das hat nicht geklappt: ') + (erg.fehler || wt('unbekannter Fehler')));
    })
    .catch(function () { meldung.textContent = wt('Das hat nicht geklappt — Verbindung prüfen.'); })
    .finally(function () { knopf.disabled = false; lade(); });
});

// YAML-Werte sicher quoten — von beiden Konfiguratoren genutzt.
function yamlEscape(s) {
  s = String(s == null ? '' : s);
  var c = s.charAt(0);
  var braucht = s === '' || s !== s.trim() || s.indexOf(':') >= 0 || s.indexOf('#') >= 0 ||
    c === '"' || c === "'" || c === '@' || c === '&' || c === '*' || c === '-' ||
    c === '[' || c === '{' || c === '!' || c === '|' || c === '>' || c === '%' || c === '?';
  if (!braucht) return s;
  return "'" + s.split("'").join("''") + "'";
}

// ---- Kamera-Karten-Konfigurator ----
(function () {
  var ent = { cameras: [], binary_sensors: [], buttons: [] };
  function fuelle(sel, arr, leer) {
    sel.innerHTML = '';
    if (leer) { var o = document.createElement('option'); o.value = ''; o.textContent = leer; sel.appendChild(o); }
    arr.forEach(function (e) { var o = document.createElement('option'); o.value = e.entity; o.textContent = e.name + ' (' + e.entity + ')'; sel.appendChild(o); });
  }
  function nameVon(entity) { var f = ent.cameras.filter(function (c) { return c.entity === entity; })[0]; return f ? f.name : entity.replace('camera.', ''); }
  // Genau die Kameras, die oben angehakt sind — mit dem Namen, den du vergeben hast.
  function angehakteCams() {
    var out = [], rows = document.querySelectorAll('#kf-cams .kf-cam');
    for (var i = 0; i < rows.length; i++) {
      var cb = rows[i].querySelector('input[type=checkbox]'); if (!cb.checked) continue;
      var nm = rows[i].querySelector('input[type=text]');
      var eid = cb.getAttribute('data-entity');
      out.push({ entity: eid, name: (nm.value.trim() || nameVon(eid)) });
    }
    return out;
  }
  // Die Klingel-Kamera wird NICHT geraten: zur Wahl steht nur, was oben angehakt
  // ist (Haken raus ⇒ die Kamera taucht hier gar nicht erst auf).
  function fuelleTkCam() {
    var sel = el('kf-tk-cam'); if (!sel) return;
    var vorher = sel.value;
    var liste = angehakteCams();
    sel.innerHTML = '';
    var o0 = document.createElement('option');
    o0.value = ''; o0.textContent = liste.length ? wt('— wählen —') : wt('— erst oben eine Kamera anhaken —');
    sel.appendChild(o0);
    liste.forEach(function (c) {
      var o = document.createElement('option'); o.value = c.entity;
      o.textContent = c.name + ' (' + c.entity + ')'; sel.appendChild(o);
    });
    sel.value = vorher;                       // Auswahl behalten, falls noch vorhanden
    if (sel.value !== vorher) sel.value = '';
  }
  var geladen = false;              // steuert die Beschriftung des Lade-Knopfes
  // Beim Sprachwechsel alles nachziehen, was das Skript selbst geschrieben hat.
  window.__kfSprache = function () {
    if (el('kf-laden')) el('kf-laden').textContent = wt(geladen ? 'Kameras neu laden' : 'Meine Kameras laden');
    if (!geladen) return;
    var rows = document.querySelectorAll('#kf-cams .kf-cam');
    for (var i = 0; i < rows.length; i++) rows[i].querySelector('input[type=text]').placeholder = wt('Name');
    var s = el('kf-tk-sensor'), k = el('kf-tk-knopf');
    var vS = s.value, vK = k.value;
    fuelle(s, ent.binary_sensors || [], wt('— wählen —')); s.value = vS;
    fuelle(k, ent.buttons || [], wt('— keiner —')); k.value = vK;
    fuelleTkCam();
  };
  if (el('kf-laden')) {
    el('kf-laden').textContent = wt('Meine Kameras laden');
    el('kf-laden').addEventListener('click', function () {
      var b = el('kf-laden'); b.disabled = true; b.textContent = wt('lädt …');
      fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
        ent = d || { cameras: [], binary_sensors: [], buttons: [] };
        var cams = el('kf-cams'); cams.innerHTML = '';
        if (!(ent.cameras || []).length) {
          var p = document.createElement('p'); p.style.color = 'var(--rot)';
          p.textContent = wt('Keine camera.*-Entitäten gefunden') + (ent.fehler ? ': ' + ent.fehler : '')
            + wt('. (Kameras erst in Home Assistant einrichten.)');
          cams.appendChild(p);
        }
        (ent.cameras || []).forEach(function (c) {
          var row = document.createElement('div'); row.className = 'kf-cam';
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true;
          var eid = document.createElement('span'); eid.className = 'eid'; eid.textContent = c.entity;
          var nm = document.createElement('input'); nm.type = 'text'; nm.value = c.name; nm.setAttribute('data-entity', c.entity); nm.placeholder = wt('Name');
          cb.setAttribute('data-entity', c.entity);
          cb.addEventListener('change', fuelleTkCam);
          nm.addEventListener('input', fuelleTkCam);
          row.appendChild(cb); row.appendChild(eid); row.appendChild(nm); cams.appendChild(row);
        });
        fuelle(el('kf-tk-sensor'), ent.binary_sensors || [], wt('— wählen —'));
        fuelleTkCam();
        fuelle(el('kf-tk-knopf'), ent.buttons || [], wt('— keiner —'));
        geladen = true;
        el('kf-body').hidden = false;
      }).catch(function () {
        var p = document.createElement('p'); p.style.color = 'var(--rot)';
        p.textContent = wt('Konnte Home Assistant nicht erreichen.');
        el('kf-cams').innerHTML = ''; el('kf-cams').appendChild(p); el('kf-body').hidden = false;
      }).finally(function () { b.disabled = false; b.textContent = wt(geladen ? 'Kameras neu laden' : 'Meine Kameras laden'); });
    });
    el('kf-tk-an').addEventListener('change', function () { el('kf-tk-body').hidden = !this.checked; });
    el('kf-ev-an').addEventListener('change', function () { el('kf-ev-body').hidden = !this.checked; });
    el('kf-erzeugen').addEventListener('click', function () {
      var cams = angehakteCams();
      el('kf-ergebnis').hidden = false; el('kf-meldung').textContent = '';
      if (!cams.length) { el('kf-yaml').textContent = wt('# Bitte mindestens eine Kamera anhaken.'); return; }
      var L = [];
      L.push('type: custom:joamy-kamera-card');
      L.push('stil: ' + el('kf-stil').value);
      L.push('cameras:');
      cams.forEach(function (c) { L.push('  - entity: ' + c.entity); L.push('    name: ' + yamlEscape(c.name)); });
      if (el('kf-tk-an').checked) {
        L.push('doorbell:'); L.push('  enabled: true');
        var rs = el('kf-tk-sensor').value; if (rs) L.push('  ringEntity: ' + rs);
        var rc = el('kf-tk-cam').value; if (rc) L.push('  camera: ' + rc);
        var rk = el('kf-tk-knopf').value; if (rk) L.push('  unlockButton: ' + rk);
      }
      L.push('events:'); L.push('  enabled: ' + (el('kf-ev-an').checked ? 'true' : 'false'));
      if (el('kf-ev-an').checked) {
        var anz = parseInt(el('kf-ev-anzahl').value, 10);
        if (!(anz >= 1)) anz = 20;
        L.push('  count: ' + Math.min(100, anz));
      }
      el('kf-yaml').textContent = L.join('\\n');
    });
    el('kf-kopieren').addEventListener('click', function () {
      var t = el('kf-yaml').textContent;
      var fertig = function () { el('kf-meldung').style.color = 'var(--gruen)'; el('kf-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
      var fallback = function () { var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); fertig(); } catch (e) {} document.body.removeChild(ta); };
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t).then(fertig).catch(fallback); } else { fallback(); }
    });
  }
})();

/* ---- Musik-Karte: Lautsprecher wählen + Griff auf dem Dashboard platzieren ----
   Der Griff ist das Einzige, was der Kunde später dauerhaft sieht. Deshalb wird
   er hier an einem nachgebauten Dashboard gesetzt — ziehen, loslassen, fertig:
   die Seite ergibt sich aus der Hälfte, in der er losgelassen wird, die Höhe
   aus der Y-Position. Genau diese zwei Werte landen im Code. */
(function () {
  if (!el('mk-laden')) return;
  var lautsprecher = [];
  var lage = { seite: 'rechts', hoehe: 50 };

  function lageText() {
    var h = lage.hoehe;
    var wo = h < 28 ? wt('oben') : (h > 72 ? wt('unten') : wt('mittig'));
    return (lage.seite === 'links' ? wt('links') : wt('rechts')) + ', ' + wo + ' (' + Math.round(h) + '%)';
  }
  function griffZeichnen() {
    var g = el('mk-griff'); if (!g) return;
    g.style.top = lage.hoehe + '%';
    g.style.transform = 'translateY(-50%)';
    if (lage.seite === 'links') { g.style.left = '0'; g.style.right = 'auto'; g.style.borderRadius = '0 8px 8px 0'; }
    else { g.style.right = '0'; g.style.left = 'auto'; g.style.borderRadius = '8px 0 0 8px'; }
    el('mk-lage-text').textContent = lageText();
  }
  (function ziehbar() {
    var g = el('mk-griff'), schirm = document.querySelector('.mk-schirm');
    if (!g || !schirm) return;
    var zieht = false;
    var setzeAus = function (ev) {
      var r = schirm.getBoundingClientRect();
      lage.hoehe = Math.max(8, Math.min(92, ((ev.clientY - r.top) / r.height) * 100));
      lage.seite = (ev.clientX - r.left) < r.width / 2 ? 'links' : 'rechts';
      griffZeichnen();
    };
    // Ziehen darf ÜBERALL auf dem Bildschirm beginnen — auch neben dem Griff.
    // Wer ihn direkt anfasst, zieht ihn; wer daneben tippt, holt ihn dorthin.
    // Ziehen am FENSTER verfolgen (nicht am Element): so bleibt der Griff auch
    // dann am Finger, wenn der Zeiger kurz aus dem Bildschirm-Rechteck läuft.
    schirm.addEventListener('pointerdown', function (ev) {
      zieht = true; setzeAus(ev); ev.preventDefault();
      var bewegt = function (e2) { if (zieht) setzeAus(e2); };
      var hoch = function () {
        zieht = false;
        window.removeEventListener('pointermove', bewegt);
        window.removeEventListener('pointerup', hoch);
        window.removeEventListener('pointercancel', hoch);
      };
      window.addEventListener('pointermove', bewegt);
      window.addEventListener('pointerup', hoch);
      window.addEventListener('pointercancel', hoch);
    });
    griffZeichnen();
  })();

  function stileMedia() {
    var sel = el('mk-stil'); if (!sel) return;
    var b = ((letzterStand && letzterStand.bausteine) || []).filter(function (x) { return x.baustein === 'media'; })[0];
    var gekauft = (b && b.themes && b.themes.length) ? b.themes.filter(function (t) { return STIL_NAMEN[t]; }) : [];
    var liste = gekauft.length ? gekauft : Object.keys(STIL_NAMEN);
    var vorher = sel.value;
    sel.innerHTML = '';
    liste.forEach(function (t) { var o = document.createElement('option'); o.value = t; o.textContent = STIL_NAMEN[t]; sel.appendChild(o); });
    // Achtung: ein nicht vorhandener Wert setzt value auf '' (selectedIndex -1) —
    // dann steht das Feld LEER da und der erzeugte Code hätte kein Style.
    sel.value = vorher; if (!sel.value) sel.value = liste[0];
    var hw = el('mk-stil-hinweis');
    hw.textContent = gekauft.length ? '' : wt('Noch kein Musik-Baustein gekauft — hier stehen später nur deine Styles.');
    hw.hidden = !!gekauft.length;
  }

  el('mk-laden').textContent = wt('Meine Lautsprecher laden');
  el('mk-laden').addEventListener('click', function () {
    var b = el('mk-laden'); b.disabled = true; b.textContent = wt('lädt …');
    fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      lautsprecher = (d && d.media_players) || [];
      var ziel = el('mk-players'); ziel.innerHTML = '';
      if (!lautsprecher.length) {
        var p = document.createElement('p'); p.style.color = 'var(--rot)';
        p.textContent = wt('Keine media_player-Entitäten gefunden — richte zuerst Lautsprecher in Home Assistant ein.');
        ziel.appendChild(p);
      }
      lautsprecher.forEach(function (c) {
        var row = document.createElement('div'); row.className = 'kf-cam';
        var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true; cb.setAttribute('data-entity', c.entity);
        var eid = document.createElement('span'); eid.className = 'eid'; eid.textContent = c.entity;
        var nm = document.createElement('input'); nm.type = 'text'; nm.value = c.name; nm.placeholder = wt('Name');
        row.appendChild(cb); row.appendChild(eid); row.appendChild(nm); ziel.appendChild(row);
      });
      stileMedia();
      el('mk-body').hidden = false;
      griffZeichnen();
    }).catch(function () {
      el('mk-players').textContent = wt('Konnte Home Assistant nicht erreichen.');
      el('mk-body').hidden = false;
    }).finally(function () { b.disabled = false; b.textContent = wt('Lautsprecher neu laden'); });
  });

  el('mk-erzeugen').addEventListener('click', function () {
    var reihen = document.querySelectorAll('#mk-players .kf-cam');
    var gewaehlt = [];
    for (var i = 0; i < reihen.length; i++) {
      var cb = reihen[i].querySelector('input[type=checkbox]'); if (!cb.checked) continue;
      var nm = reihen[i].querySelector('input[type=text]');
      var eid = cb.getAttribute('data-entity');
      gewaehlt.push({ entity: eid, name: (nm.value.trim() || eid.replace('media_player.', '')) });
    }
    el('mk-ergebnis').hidden = false; el('mk-meldung').textContent = '';
    if (!gewaehlt.length) { el('mk-yaml').textContent = wt('# Bitte mindestens einen Lautsprecher anhaken.'); return; }
    var L = ['type: custom:joamy-media-card', 'stil: ' + el('mk-stil').value, 'players:'];
    gewaehlt.forEach(function (p) { L.push('  - entity: ' + p.entity); L.push('    name: ' + yamlEscape(p.name)); });
    L.push('drawer:');
    L.push('  seite: ' + lage.seite);
    L.push('  hoehe: ' + Math.round(lage.hoehe));
    el('mk-yaml').textContent = L.join('\\n');
  });

  el('mk-kopieren').addEventListener('click', function () {
    var t = el('mk-yaml').textContent;
    var fertig = function () { el('mk-meldung').style.color = 'var(--gruen)'; el('mk-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
    var fallback = function () { var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); fertig(); } catch (e) {} document.body.removeChild(ta); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(fertig).catch(fallback); else fallback();
  });
})();

spracheAnwenden();
male(stand);
setInterval(lade, 5000);
</script>
</body>
</html>
"""


def baue_web_app(installer: Installer) -> web.Application:
    async def seite(request: web.Request) -> web.Response:
        try:
            st = await installer.status_fuer_ui()
        except Exception as e:
            LOG.error("Status für Seite fehlgeschlagen: %s", e)
            st = {"kopplungscode": None, "bausteine": [], "logs": [str(e)]}
        # "</" maskieren, damit der eingebettete JSON das <script> nicht sprengt.
        stand = json.dumps(st, ensure_ascii=False).replace("</", "<\\/")
        return web.Response(text=SEITE.replace("__STATUS_JSON__", stand),
                            content_type="text/html", charset="utf-8")

    async def status(request: web.Request) -> web.Response:
        try:
            return web.json_response(await installer.status_fuer_ui())
        except Exception as e:
            LOG.error("Status-Endpunkt fehlgeschlagen: %s", e)
            return web.json_response({"ok": False, "fehler": str(e)}, status=500)

    async def suchen(request: web.Request) -> web.Response:
        try:
            return web.json_response(await installer.suche_kaeufe())
        except Exception as e:
            LOG.error("Manuelle Suche fehlgeschlagen: %s", e)
            return web.json_response({"ok": False, "fehler": str(e)}, status=500)

    async def logs(request: web.Request) -> web.Response:
        return web.Response(text="\n".join(LOG_PUFFER) or "—", content_type="text/plain",
                            charset="utf-8")

    async def entities(request: web.Request) -> web.Response:
        try:
            return web.json_response(await installer.entitaeten_fuer_konfig())
        except Exception as e:
            LOG.error("Entities-Endpunkt fehlgeschlagen: %s", e)
            return web.json_response(
                {"cameras": [], "binary_sensors": [], "buttons": [], "fehler": str(e)}, status=500)

    async def schrift(request: web.Request) -> web.StreamResponse:
        if not os.path.exists(SCHRIFT_DATEI):
            raise web.HTTPNotFound()
        return web.FileResponse(SCHRIFT_DATEI, headers={
            "Cache-Control": "public, max-age=604800",
            "Content-Type": "font/woff2",
        })

    app = web.Application()
    app.router.add_get("/", seite)
    app.router.add_get("/schrift.woff2", schrift)
    app.router.add_get("/status", status)
    app.router.add_post("/suchen", suchen)
    app.router.add_get("/logs", logs)
    app.router.add_get("/entities", entities)
    return app
