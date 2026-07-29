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
  #kf-body, #mk-body, #bx-body, #bk-body { display: grid; gap: 18px; margin-top: 16px; }
  /* Zeitschaltuhr hat keinen Body-Wrapper — gleicher Rhythmus per Margin. */
  #zs-karte > .kf-abschnitt, #kal-karte > .kf-abschnitt { margin: 16px 0; }
  #zs-karte > button, #kal-karte > button { margin-top: 18px; }
  #kf-laden, #mk-laden, #bx-laden, #bk-laden, #zs-laden, #kl-laden { margin: 14px 0 2px; }
  /* Hinweise überall leise und klein — nicht nur im Ereignis-Block. */
  .hinweis { color: var(--tinte-3); font-size: 13px; line-height: 1.55; }
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
  select, input[type=text], input[type=number], input[type=search] {
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
  .anleitung { margin-top: 14px; border: 1px solid var(--rand); border-radius: 12px;
    background: rgba(255,255,255,.03); padding: 10px 12px; }
  .anleitung summary { cursor: pointer; font-size: 14px; color: var(--tinte); list-style: none; }
  .anleitung summary::-webkit-details-marker { display: none; }
  .anleitung summary::before { content: "▶"; font-size: 11px; margin-right: 8px; color: var(--gruen); }
  .anleitung[open] summary::before { content: "▼"; }
  .anleitung-schritte { margin: 10px 0 12px; padding-left: 20px; display: grid; gap: 6px;
    font-size: 13.5px; color: var(--tinte-2); }
  .anleitung video { width: 100%; max-width: 320px; display: block; margin: 0 auto;
    border: 1px solid var(--rand); border-radius: 12px; background: #000; }
  .kf-beispiele { margin: 6px 0 0; padding-left: 18px; display: grid; gap: 5px;
    font-size: 13px; color: var(--tinte-2); }
  .kf-beispiele code { font: 12.5px var(--mono); color: var(--tinte); background: rgba(255,255,255,.05);
    border: 1px solid var(--rand); border-radius: 6px; padding: 1px 6px; display: inline-block;
    word-break: break-all; }
  .kf-quellen { display: grid; gap: 6px; margin-top: 8px; max-height: 240px; overflow-y: auto; }
  .kf-quellen button { text-align: left; font-size: 13px; padding: 8px 10px; width: 100%; }
  .kf-quellen button.gewaehlt { border-color: var(--gruen); color: var(--tinte); }
  .kf-quellen button b { display: block; font-size: 14px; }
  .kf-quellen button span { color: var(--tinte-2); font: 11.5px var(--mono); word-break: break-all; }
  pre#kf-yaml, pre#mk-yaml, pre#bx-yaml-licht, pre#bx-yaml-jal, pre#zs-yaml, pre#bk-yaml, pre#kl-yaml { font: 13px/1.6 var(--mono); color: var(--tinte-2);
    background: var(--nacht-vertieft); border: 1px solid var(--nacht-linie); border-radius: var(--r-12);
    padding: 13px 15px; overflow-x: auto; white-space: pre; }
  #kf-meldung { text-align: center; font-size: 14px; color: var(--gruen); min-height: 1.3em; }
  #knopf-meldung { text-align: center; font-size: 14px; color: var(--gruen); min-height: 1.3em; }
  #knopf-meldung.fehler { color: var(--rot); }
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
  /* ---- Button-Baukasten (Basics) ---- */
  .bk-trenn { border-top: 1px solid var(--nacht-linie); margin: 28px 0 18px; }
  .bx-extra-code { display: grid; gap: 8px; margin-top: 12px; }
  .bx-extra-code pre { font: 13px/1.6 var(--mono); color: var(--tinte-2); background: var(--nacht-vertieft);
    border: 1px solid var(--nacht-linie); border-radius: var(--r-12); padding: 13px 15px; overflow-x: auto; white-space: pre; }
  .bk-zeilen { display: grid; grid-template-columns: 330px 1fr; gap: 20px; align-items: start; }
  @media (max-width: 640px) { .bk-zeilen { grid-template-columns: 1fr; } }
  .bk-buehne { display: grid; gap: 10px; justify-items: center; }
  /* Groß zum BEARBEITEN (Drag-and-drop braucht Fläche) — die echte Karte
     im Dashboard bleibt in ihrer normalen Größe. */
  .bk-knopf { position: relative; width: 310px; max-width: 100%; min-height: 220px; border-radius: 20px;
    cursor: pointer; background: var(--nacht-vertieft); border: 1px solid var(--nacht-linie);
    display: grid; place-items: center; align-content: center; gap: 8px; padding: 40px 14px 24px;
    user-select: none; touch-action: manipulation; }
  .bk-ico { width: 76px; height: 76px; border-radius: 50%; display: grid; place-items: center;
    border: 1.5px solid var(--nacht-linie); color: var(--tinte-2); background: rgba(255,255,255,.04);
    transition: color .25s, border-color .25s, filter .25s; }
  .bk-ico svg { width: 40px; height: 40px; }
  .bk-knopf.an .bk-ico { color: var(--knopf-an, var(--akzent)); border-color: currentColor; }
  .bk-knopf:not(.an):not(.sicher):not(.offen) .bk-ico { color: var(--knopf-aus, var(--tinte-2)); }
  .bk-knopf.sicher .bk-ico { color: var(--gruen); border-color: currentColor; filter: drop-shadow(0 0 9px var(--gruen)); }
  .bk-knopf.offen .bk-ico { color: var(--rot); border-color: currentColor; filter: drop-shadow(0 0 9px var(--rot)); }
  .bk-name { font-size: 16px; font-weight: 600; color: var(--tinte-1); max-width: 100%;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bk-status { font-size: 12px; color: var(--tinte-3); min-height: 1.2em; }
  @keyframes bkPuls { 0%,100% { transform: scale(1); } 50% { transform: scale(1.12); } }
  @keyframes bkDreh { to { transform: rotate(360deg); } }
  @keyframes bkWippe { 0%,100% { transform: rotate(-7deg); } 50% { transform: rotate(7deg); } }
  @keyframes bkFunkeln { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .55; transform: scale(.88); } }
  .bk-knopf.an.m-glow .bk-ico { filter: drop-shadow(0 0 10px var(--knopf-an, var(--akzent))); }
  .bk-knopf.an.m-glow .bk-ico svg { animation: bkPuls 3.2s ease-in-out infinite; }
  .bk-knopf.an.m-puls .bk-ico svg { animation: bkPuls 1.6s ease-in-out infinite; }
  .bk-knopf.an.m-dreh .bk-ico svg { animation: bkDreh 2.6s linear infinite; }
  .bk-knopf.an.m-wippe .bk-ico svg { animation: bkWippe 1.8s ease-in-out infinite; transform-origin: 50% 20%; }
  .bk-knopf.an.m-funkeln .bk-ico svg { animation: bkFunkeln 2.2s ease-in-out infinite; }
  .bk-hilfen { position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .15s; }
  body.bk-ziehen .bk-hilfen { opacity: 1; }
  .bk-linie.v { position: absolute; left: 50%; top: 6px; bottom: 6px; border-left: 1.5px dashed rgba(255,255,255,.16); }
  .bk-linie.h { position: absolute; top: 50%; left: 6px; right: 6px; border-top: 1.5px dashed rgba(255,255,255,.16); }
  .bk-linie.an { border-color: var(--akzent); }
  .bk-punkt { position: absolute; width: 10px; height: 10px; border-radius: 50%;
    border: 1.5px dashed rgba(255,255,255,.3); transform: translate(-50%,-50%);
    transition: transform .15s, border-color .15s, background .15s; }
  .bk-punkt[data-a="ol"] { left: 15%; top: 14%; }
  .bk-punkt[data-a="or"] { left: 85%; top: 14%; }
  .bk-punkt[data-a="ul"] { left: 15%; top: 86%; }
  .bk-punkt[data-a="ur"] { left: 85%; top: 86%; }
  .bk-punkt.an { border-style: solid; border-color: var(--akzent); background: rgba(255,255,255,.12);
    transform: translate(-50%,-50%) scale(1.7); }
  .bk-mittezone { position: absolute; left: 50%; top: 50%; width: 132px; height: 132px; border-radius: 50%;
    transform: translate(-50%,-50%); border: 1.5px dashed transparent; transition: border-color .15s, background .15s; }
  .bk-mittezone.an { border-color: var(--gruen); background: rgba(89,201,138,.10); }
  .bk-knopf.magnet { border-color: var(--akzent); }
  #bk-suche { width: 100%; }
  #bk-palette { max-height: 250px; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 8px;
    align-content: flex-start; padding: 9px; border: 1px solid var(--nacht-linie);
    border-radius: var(--r-12); background: var(--nacht-vertieft); }
  .bk-pal-kopf { width: 100%; font-size: 11.5px; letter-spacing: .4px; text-transform: uppercase;
    color: var(--tinte-3); margin: 4px 0 0; }
  .bk-chip.geraet b { display: none; }
  @keyframes bkPlopp { 0% { transform: translate(-50%,-50%) scale(.3); opacity: 0; }
    60% { transform: translate(-50%,-50%) scale(1.18); opacity: 1; }
    100% { transform: translate(-50%,-50%) scale(1); } }
  @keyframes bkIcoPop { 0% { transform: scale(.55); } 55% { transform: scale(1.28); } 100% { transform: scale(1); } }
  .bk-ico.pop svg { animation: bkIcoPop .5s cubic-bezier(.2,1.4,.4,1); }
  .bk-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px; border-radius: 999px;
    background: rgba(255,255,255,.06); border: 1px solid var(--nacht-linie); font-size: 12px;
    color: var(--tinte-2); cursor: grab; touch-action: none; user-select: none; max-width: 220px; }
  .bk-chip b { color: var(--tinte-1); font-weight: 600; white-space: nowrap; }
  .bk-chip i { font-style: normal; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bk-chip u { text-decoration: none; color: var(--tinte-3); cursor: pointer; padding: 0 2px; font-weight: 700; }
  .bk-chip.zieht { opacity: .92; box-shadow: 0 6px 18px rgba(0,0,0,.5); cursor: grabbing; }
  .bk-chip.auf-karte { position: absolute; transform: translate(-50%,-50%); max-width: 46%;
    padding: 3px 9px; font-size: 12px; z-index: 3; }
  .bk-chip.auf-karte i, .bk-chip.auf-karte u { display: none; }
  .bk-chip.auf-karte.geraet i { display: block; }
  .bk-chip.auf-karte.plopp { animation: bkPlopp .35s cubic-bezier(.2,1.4,.4,1); }
  .bk-symgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(46px, 1fr)); gap: 6px; width: 100%; }
  .bk-symgrid button { padding: 9px 0; display: grid; place-items: center; color: var(--tinte-2); font-size: 11px; }
  .bk-symgrid button.gewaehlt { border-color: var(--akzent); color: var(--tinte); }
  .bk-symgrid svg { width: 22px; height: 22px; }
  .bk-felder { display: grid; gap: 14px; min-width: 0; }
  .bk-farben { display: flex; align-items: center; gap: 10px; margin-top: 8px; font-size: 13px; color: var(--tinte-2); }
  .bk-farben input[type="color"] { width: 46px; height: 30px; padding: 2px; border: 1px solid var(--nacht-linie);
    border-radius: 8px; background: var(--nacht-vertieft); }
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

  <section class="karte" id="konfig-karte" hidden>
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
        <label class="kf-titel" for="kf-groesse" data-i18n>Größe</label>
        <select id="kf-groesse">
          <option value="normal" data-i18n>Normal — wie im JoAmy-Vorbild</option>
          <option value="kompakt" data-i18n>Kompakt — eine Stufe kleiner</option>
        </select>
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
          <label><span data-i18n>Aus welchem Medien-Ordner kommen die Aufnahmen?</span>
            <input id="kf-ev-quelle" type="text" list="kf-ev-liste" placeholder="media-source://…" autocapitalize="off" autocorrect="off" spellcheck="false"></label>
          <datalist id="kf-ev-liste"></datalist>
          <button id="kf-ev-suchen" type="button" class="leise" data-i18n>Meine Medien-Ordner anzeigen</button>
          <div id="kf-ev-treffer" class="kf-quellen" hidden></div>
          <span class="hinweis" data-i18n>Leer lassen heißt: JoAmy nimmt den ersten Ordner, der Aufnahmen enthält. Wenn du mehrere Kamerasysteme hast, trag deins ein — Beispiele:</span>
          <ul class="kf-beispiele">
            <li><b>UniFi Protect</b> <code>media-source://unifiprotect</code></li>
            <li><b>Frigate</b> <code>media-source://frigate/event_search/clips</code></li>
            <li><b data-i18n>Kamera-Aufnahmen von HA</b> <code>media-source://camera</code></li>
            <li><b data-i18n>Eigener Ordner</b> <span data-i18n>(z. B. Reolink/FTP nach</span> <code>/media/kameras</code>) <code>media-source://media_source/local/kameras</code></li>
          </ul>
        </div>
      </div>
      <button id="kf-erzeugen" type="button" data-i18n>Code anzeigen und kopieren</button>
      <div id="kf-ergebnis" hidden>
        <div class="kf-abschnitt">
          <span class="kf-titel" data-i18n>Fertiger Code — beim Hinzufügen der Karte einfügen</span>
          <pre id="kf-yaml"></pre>
        </div>
        <button id="kf-kopieren" type="button" data-i18n hidden>Code kopieren</button>
        <details class="anleitung">
          <summary data-i18n>Wie füge ich den Code ins Dashboard ein? (kurzes Video)</summary>
          <ol class="anleitung-schritte">
            <li data-i18n>Dashboard öffnen → Menü oben rechts → <b>Dashboard bearbeiten</b></li>
            <li data-i18n>Auf <b>+</b> tippen → Reiter <b>Nach Karte</b> → nach <b>Manuell</b> suchen</li>
            <li data-i18n>Alles im Feld markieren, deinen Code <b>einfügen</b> → <b>Speichern</b> → <b>Fertig</b></li>
          </ol>
          <video id="kf-video" controls playsinline preload="none" src="anleitung.mp4"></video>
        </details>
        <div id="kf-meldung"></div>
      </div>
    </div>
  </section>

  <section class="karte" id="media-karte" hidden>
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
        <label class="kf-titel" for="mk-groesse" data-i18n>Größe</label>
        <select id="mk-groesse">
          <option value="normal" data-i18n>Normal — wie im JoAmy-Vorbild</option>
          <option value="kompakt" data-i18n>Kompakt — eine Stufe kleiner</option>
        </select>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="mk-stil" data-i18n>Style</label>
        <span id="mk-stil-hinweis" class="hinweis" hidden></span>
        <select id="mk-stil"></select>
      </div>
      <button id="mk-erzeugen" type="button" data-i18n>Code anzeigen und kopieren</button>
      <div id="mk-ergebnis" hidden>
        <div class="kf-abschnitt">
          <span class="kf-titel" data-i18n>Fertiger Code — beim Hinzufügen der Karte einfügen</span>
          <pre id="mk-yaml"></pre>
        </div>
        <button id="mk-kopieren" type="button" data-i18n hidden>Code kopieren</button>
        <details class="anleitung">
          <summary data-i18n>Wie füge ich den Code ins Dashboard ein? (kurzes Video)</summary>
          <ol class="anleitung-schritte">
            <li data-i18n>Dashboard öffnen → Menü oben rechts → <b>Dashboard bearbeiten</b></li>
            <li data-i18n>Auf <b>+</b> tippen → Reiter <b>Nach Karte</b> → nach <b>Manuell</b> suchen</li>
            <li data-i18n>Alles im Feld markieren, deinen Code <b>einfügen</b> → <b>Speichern</b> → <b>Fertig</b></li>
          </ol>
          <video id="mk-video" controls playsinline preload="none" src="anleitung.mp4"></video>
        </details>
        <div id="mk-meldung"></div>
      </div>
    </div>
  </section>

  <section class="karte" id="basics-karte" hidden>
    <h2 data-i18n>Basics einrichten — Beleuchtung &amp; Jalousie</h2>
    <p class="kf-intro" data-i18n>Zwei Karten in einem Baustein: Licht und Rollläden. Beide erkennen
      selbst, was dein Gerät kann — dimmen, Weißton, Farbe, Lamellen. Wähle unten aus, was auf die
      Karten soll, und füge den fertigen Code in dein Dashboard ein.</p>
    <div class="mk-hinweis"><b data-i18n>Favoritenstellung:</b> <span data-i18n>Fahre Lampe oder Rollladen in
      deine Lieblingsstellung und halte den Stern 2 Sekunden — er rastet ein. Ab dann fährt ein kurzer
      Druck auf den Stern genau diese Stellung an. Nochmal 2 Sekunden halten löscht den Favoriten.
      Jedes Gerät hat seinen eigenen Favoriten, und Home Assistant merkt sie sich auch über Neustarts.</span></div>
    <button id="bx-laden" type="button" data-i18n>Meine Lichter &amp; Rollläden laden</button>
    <div id="bx-body" hidden>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Lichter für die Beleuchtungs-Karte</span>
        <div id="bx-lights"></div>
      </div>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Rollläden für die Jalousie-Karte</span>
        <div id="bx-covers"></div>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="bx-rahmen" data-i18n>Darstellung</label>
        <select id="bx-rahmen">
          <option value="karte" data-i18n>Eine Karte mit Überschrift und Hintergrund</option>
          <option value="frei" data-i18n>Jede Lampe / jeder Rollladen als freie Einzelkarte</option>
        </select>
        <span class="hinweis" data-i18n>„Frei“ erzeugt einen eigenen Code je Gerät — jede Karte lässt sich einzeln im Dashboard platzieren.</span>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="bx-spalten" data-i18n>Nebeneinander</label>
        <select id="bx-spalten">
          <option value="1" data-i18n>Untereinander (Standard)</option>
          <option value="2" data-i18n>2 nebeneinander</option>
          <option value="3" data-i18n>3 nebeneinander</option>
        </select>
        <span class="hinweis" data-i18n>Wähle dafür mindestens so viele Geräte aus — die Karten skalieren sich automatisch kleiner, damit sie in eine Reihe passen (höchstens 3).</span>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="bx-groesse" data-i18n>Größe</label>
        <select id="bx-groesse">
          <option value="normal" data-i18n>Normal — wie im JoAmy-Vorbild</option>
          <option value="kompakt" data-i18n>Kompakt — eine Stufe kleiner</option>
        </select>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="bx-stil" data-i18n>Style</label>
        <span id="bx-stil-hinweis" class="hinweis" hidden></span>
        <select id="bx-stil"></select>
      </div>
      <button id="bx-erzeugen" type="button" data-i18n>Codes anzeigen</button>
      <div id="bx-ergebnis" hidden>
        <div class="kf-abschnitt">
          <span class="kf-titel" data-i18n>Beleuchtungs-Karte — beim Hinzufügen unter „Manuell" einfügen</span>
          <pre id="bx-yaml-licht"></pre>
        </div>
        <div class="kf-abschnitt">
          <span class="kf-titel" data-i18n>Jalousie-Karte — als zweite Karte genauso einfügen</span>
          <pre id="bx-yaml-jal"></pre>
        </div>
        <button id="bx-kopieren-licht" type="button" data-i18n>Licht-Code kopieren</button>
        <button id="bx-kopieren-jal" type="button" data-i18n>Jalousie-Code kopieren</button>
        <div id="bx-meldung"></div>
      </div>
    </div>
    <div class="bk-trenn"></div>
    <h2 data-i18n>Button-Karte — dein Baukasten</h2>
    <p class="kf-intro" data-i18n>Bau deinen Button hier visuell zusammen: Zieh ein Gerät in die Mitte der Vorschau,
      Werte dorthin, wo du sie haben willst, tippe ein Symbol an. Ein Klick — der fertige Code ist kopiert.</p>
    <button id="bk-laden" type="button" data-i18n>Baukasten öffnen</button>
    <div id="bk-body" hidden>
      <div class="bk-zeilen">
        <div class="bk-buehne">
          <div id="bk-vorschau" class="bk-knopf">
            <div class="bk-hilfen" id="bk-hilfen">
              <div class="bk-linie v"></div>
              <div class="bk-linie h"></div>
              <div class="bk-punkt" data-a="ol"></div>
              <div class="bk-punkt" data-a="or"></div>
              <div class="bk-punkt" data-a="ul"></div>
              <div class="bk-punkt" data-a="ur"></div>
              <div class="bk-mittezone"></div>
            </div>
            <div class="bk-ico" id="bk-ico"></div>
            <div class="bk-name" id="bk-name">Button</div>
            <div class="bk-status" id="bk-status"></div>
          </div>
          <span class="hinweis" data-i18n>Tipp: Tippe auf die Vorschau — sie wechselt zwischen An und Aus, so siehst du Farben und Bewegung in beiden Zuständen.</span>
          <div class="kf-abschnitt">
            <span class="kf-titel" data-i18n>Alles hier kannst du auf die Karte ziehen: Werte dorthin, wo du sie willst — ein schaltbares Gerät in die Mitte, dann wird es der Button.</span>
            <input id="bk-suche" type="search">
            <div id="bk-palette"></div>
            <span class="hinweis" data-i18n>Beim Ziehen erscheinen Magnet-Linien: Ecken und Mittelachsen rasten sanft ein. Zum Entfernen einen Wert einfach von der Karte herunterziehen.</span>
          </div>
        </div>
        <div class="bk-felder">
          <div class="kf-abschnitt">
            <label class="kf-titel" for="bk-funktion" data-i18n>Funktion</label>
            <select id="bk-funktion">
              <option value="geraet" data-i18n>Ein Gerät schalten</option>
              <option value="sprung" data-i18n>Sprung zu einem anderen Dashboard</option>
            </select>
          </div>
          <div class="kf-abschnitt" id="bk-feld-entity">
            <label class="kf-titel" for="bk-entity" data-i18n>Gerät</label>
            <select id="bk-entity"></select>
            <span class="hinweis" data-i18n>Symbol, Farbe und Bewegung passen sich automatisch dem Gerät an — unten kannst du alles ändern.</span>
          </div>
          <div class="kf-abschnitt" id="bk-feld-ziel" hidden>
            <label class="kf-titel" for="bk-ziel" data-i18n>Ziel (Pfad des Dashboards)</label>
            <input id="bk-ziel" type="text" placeholder="/lovelace/kameras">
            <span class="hinweis" data-i18n>Den Pfad siehst du oben in der Adresszeile, wenn du das Ziel-Dashboard offen hast.</span>
          </div>
          <div class="kf-abschnitt">
            <label class="kf-titel" for="bk-label" data-i18n>Beschriftung</label>
            <input id="bk-label" type="text">
          </div>
          <div class="kf-abschnitt">
            <span class="kf-titel" data-i18n>Symbol</span>
            <div id="bk-symgrid" class="bk-symgrid"></div>
          </div>
          <div class="kf-abschnitt" id="bk-feld-farben">
            <label class="kf-cam"><input type="checkbox" id="bk-farben-eigene">
              <span data-i18n>Eigene Farben statt der Style-Farben</span></label>
            <div class="bk-farben" id="bk-farben" hidden>
              <label for="bk-farbe-an" data-i18n>Farbe An</label><input type="color" id="bk-farbe-an" value="#59c98a">
              <label for="bk-farbe-aus" data-i18n>Farbe Aus</label><input type="color" id="bk-farbe-aus" value="#8a8f98">
            </div>
          </div>
          <div class="kf-abschnitt" id="bk-feld-motion">
            <label class="kf-titel" for="bk-motion" data-i18n>Bewegung</label>
            <select id="bk-motion">
              <option value="std" data-i18n>Automatisch — passend zum Gerät</option>
              <option value="glow" data-i18n>Glühen</option>
              <option value="puls" data-i18n>Pulsieren</option>
              <option value="dreh" data-i18n>Drehen</option>
              <option value="wippe" data-i18n>Wippen</option>
              <option value="funkeln" data-i18n>Funkeln</option>
              <option value="aus" data-i18n>Aus — keine Bewegung</option>
            </select>
            <span class="hinweis" id="bk-motion-hinweis"></span>
          </div>
          <div class="kf-abschnitt">
            <label class="kf-titel" for="bk-groesse" data-i18n>Größe</label>
            <select id="bk-groesse">
              <option value="normal" data-i18n>Normal — wie im JoAmy-Vorbild</option>
              <option value="kompakt" data-i18n>Kompakt — eine Stufe kleiner</option>
            </select>
          </div>
          <div class="kf-abschnitt">
            <label class="kf-titel" for="bk-stil" data-i18n>Style</label>
            <span id="bk-stil-hinweis" class="hinweis" hidden></span>
            <select id="bk-stil"></select>
          </div>
        </div>
      </div>
      <button id="bk-erzeugen" type="button" data-i18n>Code anzeigen und kopieren</button>
      <div class="kf-abschnitt" id="bk-ergebnis" hidden>
        <pre id="bk-yaml"></pre>
      </div>
      <div id="bk-meldung"></div>
    </div>
  </section>

  <section class="karte" id="knopf-karte" hidden>
    <h2 data-i18n>JoAmy-Knopf</h2>
    <p class="kf-intro" data-i18n>Der kleine runde Knopf auf dem Dashboard öffnet die JoAmy-Modi
      (zum Beispiel „Karten werfen"). Er ist automatisch da, sobald eine JoAmy-Karte geladen ist,
      und lässt sich mit dem Finger frei verschieben.</p>
    <div class="kf-abschnitt">
      <label><input type="checkbox" id="knopf-schalter"> <b data-i18n>JoAmy-Knopf auf dem Dashboard anzeigen</b></label>
      <span class="hinweis" data-i18n>Ausgeblendet gilt überall und für alle Nutzer. Die Modi selbst
        laufen unverändert weiter — nur die Bedienstelle verschwindet.</span>
    </div>
    <div id="knopf-meldung"></div>
  </section>

  <section class="karte" id="zs-karte" hidden>
    <h2 data-i18n>Zeitschaltuhr einrichten</h2>
    <p class="kf-intro" data-i18n>Wie an einer klassischen Zeitschaltuhr: Gerät wählen, Ein- und
      Aus-Zeit stecken, fertig. Geräte, Zeiten und Timer stellst du direkt in der Karte ein —
      hier brauchst du nur den Code fürs Dashboard.</p>
    <div class="mk-hinweis"><b data-i18n>Bleibt alles erhalten:</b> <span data-i18n>Deine Zeitpläne und
      laufenden Timer überleben jeden Neustart von Home Assistant — sie liegen sicher in deinem
      Home Assistant, nicht in der Karte.</span></div>
    <div class="kf-abschnitt">
      <label class="kf-titel" for="zs-groesse" data-i18n>Größe</label>
      <select id="zs-groesse">
        <option value="normal" data-i18n>Normal — wie im JoAmy-Vorbild</option>
        <option value="kompakt" data-i18n>Kompakt — eine Stufe kleiner</option>
      </select>
    </div>
    <div class="kf-abschnitt">
      <label class="kf-titel" for="zs-ansicht" data-i18n>Darstellung der Karte</label>
      <select id="zs-ansicht">
        <option value="voll" data-i18n>Alles auf den ersten Blick — alle Zeitpläne direkt in der Karte</option>
        <option value="kompakt" data-i18n>Kleiner Überblick — Anzahl und nächste Schaltung; Antippen öffnet alles</option>
      </select>
      <span class="hinweis" data-i18n>Der kleine Überblick hält dein Dashboard schlank, auch wenn du viele Zeitpläne hast.</span>
    </div>
    <div class="kf-abschnitt">
      <label class="kf-titel" for="zs-stil" data-i18n>Style</label>
      <span id="zs-stil-hinweis" class="hinweis" hidden></span>
      <select id="zs-stil"></select>
    </div>
    <button id="zs-erzeugen" type="button" data-i18n>Code anzeigen und kopieren</button>
    <div id="zs-ergebnis" hidden>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Fertiger Code — beim Hinzufügen der Karte einfügen</span>
        <pre id="zs-yaml"></pre>
      </div>
      <button id="zs-kopieren" type="button" data-i18n hidden>Code kopieren</button>
      <div id="zs-meldung"></div>
    </div>
  </section>

  <section class="karte" id="kal-karte" hidden>
    <h2 data-i18n>Kalender einrichten</h2>
    <p class="kf-intro" data-i18n>Deine Kalender werden automatisch gefunden — hake ab, was du nicht sehen
      willst. Liegt ein Termin in der aktuellen Uhrzeit, legt er sich groß über die Karte; der Kalender
      bleibt dahinter verschwommen sichtbar, ein Fingertipp blendet ihn aus.</p>
    <button id="kl-laden" type="button" data-i18n>Meine Kalender laden</button>
    <div id="kl-body" hidden>
      <div class="kf-abschnitt">
        <span class="kf-titel" data-i18n>Diese Kalender zeigt die Karte</span>
        <div id="kl-liste"></div>
        <span class="hinweis" data-i18n>Alle angehakt heißt: die Karte erkennt auch später neu angelegte Kalender von selbst. Wählst du ab, zeigt sie genau deine Auswahl.</span>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="kl-groesse" data-i18n>Größe</label>
        <select id="kl-groesse">
          <option value="normal" data-i18n>Normal — wie im JoAmy-Vorbild</option>
          <option value="kompakt" data-i18n>Kompakt — eine Stufe kleiner</option>
        </select>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="kl-stil" data-i18n>Style</label>
        <span id="kl-stil-hinweis" class="hinweis" hidden></span>
        <select id="kl-stil"></select>
      </div>
      <button id="kl-erzeugen" type="button" data-i18n>Code anzeigen und kopieren</button>
      <div class="kf-abschnitt" id="kl-ergebnis" hidden>
        <pre id="kl-yaml"></pre>
      </div>
      <div id="kl-meldung"></div>
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
  'Zeitschaltuhr einrichten': 'Set up the timer switch',
  'Darstellung der Karte': 'Card layout',
  'Alles auf den ersten Blick — alle Zeitpläne direkt in der Karte': 'Everything at a glance — all schedules right in the card',
  'Kleiner Überblick — Anzahl und nächste Schaltung; Antippen öffnet alles': 'Small overview — count and next switch time; tap to open everything',
  'Der kleine Überblick hält dein Dashboard schlank, auch wenn du viele Zeitpläne hast.': 'The small overview keeps your dashboard lean, even with many schedules.',
  'Wie an einer klassischen Zeitschaltuhr: Gerät wählen, Ein- und Aus-Zeit stecken, fertig. Geräte, Zeiten und Timer stellst du direkt in der Karte ein — hier brauchst du nur den Code fürs Dashboard.':
    'Just like a classic plug-in timer: pick a device, set the on and off time, done. Devices, times and quick timers are set right in the card — here you only need the code for your dashboard.',
  'Bleibt alles erhalten:': 'Everything is kept:',
  'Deine Zeitpläne und laufenden Timer überleben jeden Neustart von Home Assistant — sie liegen sicher in deinem Home Assistant, nicht in der Karte.':
    'Your schedules and running timers survive every Home Assistant restart — they are stored safely inside your Home Assistant, not in the card.',
  'Basics einrichten — Beleuchtung & Jalousie': 'Set up the Basics — lighting & blinds',
  'Zwei Karten in einem Baustein: Licht und Rollläden. Beide erkennen selbst, was dein Gerät kann — dimmen, Weißton, Farbe, Lamellen. Wähle unten aus, was auf die Karten soll, und füge den fertigen Code in dein Dashboard ein.':
    'Two cards in one module: lights and blinds. Both detect on their own what your device can do — dimming, white tones, colour, slats. Pick below what goes on the cards and paste the finished code into your dashboard.',
  'Favoritenstellung:': 'Favourite position:',
  'Fahre Lampe oder Rollladen in deine Lieblingsstellung und halte den Stern 2 Sekunden — er rastet ein. Ab dann fährt ein kurzer Druck auf den Stern genau diese Stellung an. Nochmal 2 Sekunden halten löscht den Favoriten. Jedes Gerät hat seinen eigenen Favoriten, und Home Assistant merkt sie sich auch über Neustarts.':
    'Move a lamp or blind into your favourite position and hold the star for 2 seconds — it locks in. From then on a short press on the star recalls exactly that position. Holding for 2 seconds again deletes the favourite. Every device has its own favourite, and Home Assistant remembers them across restarts.',
  'Meine Lichter & Rollläden laden': 'Load my lights & blinds',
  'Lichter für die Beleuchtungs-Karte': 'Lights for the lighting card',
  'Rollläden für die Jalousie-Karte': 'Blinds for the blinds card',
  'Darstellung': 'Layout',
  'Eine Karte mit Überschrift und Hintergrund': 'One card with heading and background',
  'Jede Lampe / jeder Rollladen als freie Einzelkarte': 'Every lamp / blind as a free standalone card',
  '„Frei“ erzeugt einen eigenen Code je Gerät — jede Karte lässt sich einzeln im Dashboard platzieren.':
    '“Free” creates its own code per device — each card can be placed individually in your dashboard.',
  '# ─── nächste Karte — einzeln unter „Manuell“ einfügen ───': '# ─── next card — paste separately via “Manual” ───',
  'Nebeneinander': 'Side by side',
  'Untereinander (Standard)': 'Stacked (default)',
  '2 nebeneinander': '2 side by side',
  '3 nebeneinander': '3 side by side',
  'Wähle dafür mindestens so viele Geräte aus — die Karten skalieren sich automatisch kleiner, damit sie in eine Reihe passen (höchstens 3).':
    'Select at least that many devices — the cards automatically scale down so they fit in one row (3 at most).',
  'Code anzeigen und kopieren': 'Show and copy code',
  'Codes anzeigen': 'Show codes',
  'Größe': 'Size',
  'Normal — wie im JoAmy-Vorbild': 'Normal — like the JoAmy original',
  'Kompakt — eine Stufe kleiner': 'Compact — one step smaller',
  'Beleuchtungs-Karte — beim Hinzufügen unter „Manuell“ einfügen': 'Lighting card — paste via “Manual” when adding a card',
  'Jalousie-Karte — als zweite Karte genauso einfügen': 'Blinds card — paste the same way as a second card',
  'Licht-Code kopieren': 'Copy lighting code',
  'Jalousie-Code kopieren': 'Copy blinds code',
  'Button-Karte — dein Baukasten': 'Button card — your builder kit',
  'Bau deinen Button hier visuell zusammen: Zieh ein Gerät in die Mitte der Vorschau, Werte dorthin, wo du sie haben willst, tippe ein Symbol an. Ein Klick — der fertige Code ist kopiert.':
    'Build your button visually right here: drag a device into the middle of the preview, drop values wherever you want them, tap a symbol. One click — the finished code is copied.',
  'Baukasten öffnen': 'Open the builder kit',
  'Tipp: Tippe auf die Vorschau — sie wechselt zwischen An und Aus, so siehst du Farben und Bewegung in beiden Zuständen.':
    'Tip: tap the preview — it toggles between on and off so you can see colours and motion in both states.',
  'Zusatzwerte — Sensor wählen und auf eine Ecke der Vorschau ziehen': 'Extra values — pick a sensor and drag it onto a corner of the preview',
  '+ Hinzufügen': '+ Add',
  'Funktion': 'Function',
  'Ein Gerät schalten': 'Switch a device',
  'Sprung zu einem anderen Dashboard': 'Jump to another dashboard',
  'Gerät': 'Device',
  'Symbol, Farbe und Bewegung passen sich automatisch dem Gerät an — unten kannst du alles ändern.':
    'Symbol, colour and motion adapt to the device automatically — you can change everything below.',
  'Ziel (Pfad des Dashboards)': 'Target (dashboard path)',
  'Den Pfad siehst du oben in der Adresszeile, wenn du das Ziel-Dashboard offen hast.':
    'You can see the path in the address bar while the target dashboard is open.',
  'Beschriftung': 'Label',
  'Symbol': 'Symbol',
  'Eigene Farben statt der Style-Farben': 'Custom colours instead of the style colours',
  'Farbe An': 'Colour on',
  'Farbe Aus': 'Colour off',
  'Bewegung': 'Motion',
  'Automatisch — passend zum Gerät': 'Automatic — matched to the device',
  'Glühen': 'Glow',
  'Pulsieren': 'Pulse',
  'Drehen': 'Spin',
  'Wippen': 'Rock',
  'Funkeln': 'Sparkle',
  'Aus — keine Bewegung': 'Off — no motion',
  'Automatisch heißt hier:': 'Automatic here means:',
  'Automatisch': 'Automatic',
  'Schlösser': 'Locks',
  'Lichter': 'Lights',
  'Schalter': 'Switches',
  'Ventilatoren': 'Fans',
  'Rollläden': 'Blinds',
  'Szenen': 'Scenes',
  'Skripte': 'Scripts',
  'Knöpfe': 'Buttons',
  'Helfer (an/aus)': 'Helpers (on/off)',
  'Medien': 'Media players',
  'automatisch — Name des Geräts': 'automatic — device name',
  'Alles hier kannst du auf die Karte ziehen: Werte dorthin, wo du sie willst — ein schaltbares Gerät in die Mitte, dann wird es der Button.':
    'Drag anything here onto the card: values wherever you want them — drop a switchable device in the middle and it becomes the button.',
  'Beim Ziehen erscheinen Magnet-Linien: Ecken und Mittelachsen rasten sanft ein. Zum Entfernen einen Wert einfach von der Karte herunterziehen.':
    'While dragging, magnet lines appear: corners and centre axes snap gently. To remove a value, just drag it off the card.',
  'Sensoren': 'Sensors',
  'JoAmy-Knopf': 'JoAmy button',
  'Der kleine runde Knopf auf dem Dashboard öffnet die JoAmy-Modi (zum Beispiel „Karten werfen"). Er ist automatisch da, sobald eine JoAmy-Karte geladen ist, und lässt sich mit dem Finger frei verschieben.':
    'The small round button on the dashboard opens the JoAmy modes (for example \u201cThrow cards\u201d). It appears automatically as soon as a JoAmy card is loaded and can be moved freely with your finger.',
  'JoAmy-Knopf auf dem Dashboard anzeigen': 'Show the JoAmy button on the dashboard',
  'Ausgeblendet gilt überall und für alle Nutzer. Die Modi selbst laufen unverändert weiter — nur die Bedienstelle verschwindet.':
    'Hidden applies everywhere and for all users. The modes themselves keep running — only the control disappears.',
  'Der Knopf ist wieder da — überall.': 'The button is back — everywhere.',
  'Ausgeblendet — überall und sofort.': 'Hidden — everywhere, immediately.',
  'Das hat nicht geklappt — Home Assistant war nicht erreichbar.':
    'That did not work — Home Assistant was not reachable.',
  'Kalender einrichten': 'Set up the calendar',
  'Deine Kalender werden automatisch gefunden — hake ab, was du nicht sehen willst. Liegt ein Termin in der aktuellen Uhrzeit, legt er sich groß über die Karte; der Kalender bleibt dahinter verschwommen sichtbar, ein Fingertipp blendet ihn aus.':
    'Your calendars are found automatically — untick what you don’t want to see. When an appointment falls on the current time it lays itself large over the card; the calendar stays blurred behind it, one tap hides it.',
  'Meine Kalender laden': 'Load my calendars',
  'Diese Kalender zeigt die Karte': 'These calendars appear on the card',
  'Alle angehakt heißt: die Karte erkennt auch später neu angelegte Kalender von selbst. Wählst du ab, zeigt sie genau deine Auswahl.':
    'All ticked means: the card also picks up calendars you create later. If you untick some, it shows exactly your selection.',
  'Keine Kalender gefunden — in Home Assistant unter Einstellungen → Integrationen einen „Lokalen Kalender" anlegen.':
    'No calendars found — create a “Local calendar” in Home Assistant under Settings → Integrations.',
  'Mindestens einen Kalender anhaken.': 'Tick at least one calendar.',
  'Suchen …': 'Search …',
  'Erst ein Gerät wählen — oder oben auf „Sprung“ stellen.': 'Pick a device first — or set “Jump” above.',
  'Meine Geräte & Sensoren laden': 'Load my devices & sensors',
  'Keine Sensoren gefunden.': 'No sensors found.',
  'Weiter': 'Go',
  'verriegelt': 'locked',
  'offen': 'open',
  'an': 'on',
  'aus': 'off',
  'Keine gefunden.': 'None found.',
  'Kopieren hat nicht geklappt — bitte den Code oben markieren und von Hand kopieren.':
    'Copying did not work — please select the code above and copy it by hand.',
  'Karte %n kopieren': 'Copy card %n',
  'Jede Karte einzeln einfügen — Home Assistant nimmt immer nur eine auf einmal.':
    'Paste each card separately — Home Assistant only accepts one at a time.',
  'Lade …': 'Loading …',
  'Neu laden': 'Reload',
  '# Kein Licht angehakt.': '# No light ticked.',
  '# Kein Rollladen angehakt.': '# No blind ticked.',
  'Hier stehen nach dem Kauf nur deine Styles.': 'After your purchase only your styles are listed here.',
  'Wie füge ich den Code ins Dashboard ein? (kurzes Video)': 'How do I paste the code into my dashboard? (short video)',
  'Dashboard öffnen → Menü oben rechts → Dashboard bearbeiten': 'Open your dashboard → menu top right → Edit dashboard',
  'Auf + tippen → Reiter Nach Karte → nach Manuell suchen': 'Tap + → tab By card → search for Manual',
  'Alles im Feld markieren, deinen Code einfügen → Speichern → Fertig': 'Select everything in the field, paste your code → Save → Done',
  'Aus welchem Medien-Ordner kommen die Aufnahmen?': 'Which media folder holds the recordings?',
  'Meine Medien-Ordner anzeigen': 'Show my media folders',
  'Suche deine Medien-Ordner …': 'Looking for your media folders …',
  'Keine Medien-Ordner gefunden — trag deinen Ordner von Hand ein (Beispiele unten).':
    'No media folders found — enter your folder by hand (examples below).',
  'Konnte die Medien-Ordner nicht lesen — trag deinen Ordner von Hand ein.':
    'Could not read the media folders — enter your folder by hand.',
  'Leer lassen heißt: JoAmy nimmt den ersten Ordner, der Aufnahmen enthält. Wenn du mehrere Kamerasysteme hast, trag deins ein — Beispiele:':
    'Leave it empty and JoAmy takes the first folder that holds recordings. If you run several camera systems, enter yours — examples:',
  'Kamera-Aufnahmen von HA': 'Camera recordings from HA',
  'Eigener Ordner': 'Your own folder',
  '(z. B. Reolink/FTP nach': '(e.g. Reolink/FTP into',
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
  /* --- Musik-Karte (Konfigurator) --- */
  'Musik-Karte einrichten': 'Set up the music card',
  'Wähle deine Lautsprecher und schiebe den Musik-Griff dorthin, wo er auf deinem Bildschirm sitzen soll. Am Ende bekommst du den fertigen Code zum Einfügen.':
    'Pick your speakers and slide the music handle to where it should sit on your screen. At the end you get the finished code to paste in.',
  'Music Assistant wird gebraucht. Zum Suchen und Abspielen von Musik braucht die Karte das Add-on „Music Assistant“. Ohne es kannst du nur steuern, was gerade läuft.':
    '<b>Music Assistant is required.</b> To search for and play music, the card needs the “Music Assistant” add-on. Without it you can only control what is already playing.',
  'Meine Lautsprecher laden': 'Load my speakers',
  'Lautsprecher neu laden': 'Reload speakers',
  'Lautsprecher (anhaken + Namen vergeben)': 'Speakers (tick them + give them names)',
  'Wo soll der Musik-Griff sitzen?': 'Where should the music handle sit?',
  'Die Musik-Schublade liegt über deinem Dashboard — zu sehen ist nur ein schmaler Griff am Bildschirmrand. Zieh ihn unten an die Stelle, an der er dich am wenigsten stört; ein Tipp darauf zieht die Musik heraus. Das gilt auf jeder Seite deines Dashboards, egal wie viele Karten du hast.':
    'The music drawer sits above your dashboard — all you see is a slim handle at the edge of the screen. Drag it below to the spot where it bothers you least; a tap on it pulls the music out. This works on every page of your dashboard, no matter how many cards you have.',
  'Style': 'Style',
  'Keine media_player-Entitäten gefunden — richte zuerst Lautsprecher in Home Assistant ein.':
    'No media_player entities found — set up speakers in Home Assistant first.',
  'Noch kein Musik-Baustein gekauft — hier stehen später nur deine Styles.':
    'No music building block bought yet — later only your own styles appear here.',
  '# Bitte mindestens einen Lautsprecher anhaken.': '# Please tick at least one speaker.',
  'links': 'left', 'rechts': 'right', 'oben': 'top', 'unten': 'bottom', 'mittig': 'middle',
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

/* --- JoAmy-Knopf: Sichtbarkeit lädt/setzt den Hub-Store über das Add-on --- */
function ladeKnopf() {
  fetch('knopf', { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (t) {
      if (!t || !t.verfuegbar) return;           // Baustein nicht da → Sektion bleibt weg
      window.__knopfDa = true;
      var karte = el('knopf-karte'), schalter = el('knopf-schalter');
      if (!karte || !schalter) return;
      karte.hidden = false;
      schalter.checked = !!t.sichtbar;
      if (schalter.dataset.verdrahtet) return;
      schalter.dataset.verdrahtet = '1';
      schalter.addEventListener('change', function () {
        var soll = schalter.checked;
        schalter.disabled = true;
        fetch('knopf', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sichtbar: soll }) })
          .then(function (r) { return r.json(); })
          .then(function (a) {
            schalter.disabled = false;
            var m = el('knopf-meldung');
            if (a && a.ok) {
              schalter.checked = !!a.sichtbar;   // der ECHTE Stand aus dem Store
              if (m) { m.textContent = a.sichtbar ? wt('Der Knopf ist wieder da — überall.') : wt('Ausgeblendet — überall und sofort.'); m.className = ''; }
            } else {
              schalter.checked = !soll;          // nichts vorgaukeln
              if (m) { m.textContent = wt('Das hat nicht geklappt — Home Assistant war nicht erreichbar.'); m.className = 'fehler'; }
            }
          })
          .catch(function () {
            schalter.disabled = false; schalter.checked = !soll;
            var m = el('knopf-meldung');
            if (m) { m.textContent = wt('Das hat nicht geklappt — Home Assistant war nicht erreichbar.'); m.className = 'fehler'; }
          });
      });
    })
    .catch(function () {});
}
ladeKnopf();
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
  // STANDING RULE (Frank 28.07.): Der Sprachwechsel MUSS jede Sektion erreichen —
  // auch alles, was per JavaScript gesetzt wurde (Platzhalter, Listen, Statuszeilen).
  ['__kfSprache', '__mkSprache', '__bxSprache', '__bkSprache', '__klSprache', '__zsSprache']
    .forEach(function (n) { if (window[n]) { try { window[n](); } catch (e) {} } });
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

  // Konfiguratoren NUR zeigen, wenn der zugehörige Baustein gekauft ist —
  // Einstellungen für nie gekaufte Karten verwirren Kunden und wirken
  // unseriös (Franks Regel, gilt für ALLE künftigen Karten-Konfiguratoren).
  var gekauftB = {};
  (st.bausteine || []).forEach(function (b) { gekauftB[b.baustein] = true; });
  if (el('konfig-karte')) el('konfig-karte').hidden = !gekauftB.kamera;
  if (el('basics-karte')) el('basics-karte').hidden = !gekauftB.basics;
  if (el('zs-karte')) el('zs-karte').hidden = !gekauftB.zeitschaltuhr;
  if (el('kal-karte')) el('kal-karte').hidden = !gekauftB.kalender;
  if (el('media-karte')) el('media-karte').hidden = !gekauftB.media;
  // JoAmy-Knopf: sichtbar, wenn der toss-Baustein WIRKLICH antwortet (ladeKnopf
  // fragt nach). Der Status-Poll (alle 5 s) darf die Entscheidung nicht umwerfen.
  if (el('knopf-karte')) el('knopf-karte').hidden = !(gekauftB.toss || window.__knopfDa);
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
    el('kf-ev-suchen').addEventListener('click', function () {
      var b = this, kasten = el('kf-ev-treffer');
      b.disabled = true; b.textContent = wt('Suche deine Medien-Ordner …');
      fetch('medienquellen', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
        var q = (d && d.quellen) || [];
        el('kf-ev-liste').innerHTML = q.map(function (x) { return '<option value="' + x.id + '">' + (x.pfad || x.titel) + '</option>'; }).join('');
        kasten.innerHTML = ''; kasten.hidden = false;
        if (!q.length) { var p0 = document.createElement('p'); p0.className = 'hinweis';
          p0.textContent = wt('Keine Medien-Ordner gefunden — trag deinen Ordner von Hand ein (Beispiele unten).'); kasten.appendChild(p0); return; }
        q.forEach(function (x) {
          var kn = document.createElement('button'); kn.type = 'button'; kn.className = 'leise';
          var t1 = document.createElement('b'); t1.textContent = x.pfad || x.titel;
          var t2 = document.createElement('span'); t2.textContent = x.id;
          kn.appendChild(t1); kn.appendChild(t2);
          kn.addEventListener('click', function () { el('kf-ev-quelle').value = x.id;
            Array.prototype.forEach.call(kasten.children, function (c) { c.classList.remove('gewaehlt'); });
            kn.classList.add('gewaehlt'); });
          kasten.appendChild(kn);
        });
      }).catch(function () {
        kasten.hidden = false; kasten.textContent = wt('Konnte die Medien-Ordner nicht lesen — trag deinen Ordner von Hand ein.');
      }).finally(function () { b.disabled = false; b.textContent = wt('Meine Medien-Ordner anzeigen'); });
    });
    el('kf-erzeugen').addEventListener('click', function () {
      var cams = angehakteCams();
      el('kf-ergebnis').hidden = false; el('kf-meldung').textContent = '';
      if (!cams.length) { el('kf-yaml').textContent = wt('# Bitte mindestens eine Kamera anhaken.'); return; }
      var L = [];
      L.push('type: custom:joamy-kamera-card');
      L.push('stil: ' + el('kf-stil').value);
      if (el('kf-groesse') && el('kf-groesse').value === 'kompakt') L.push('groesse: kompakt');
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
        var q = (el('kf-ev-quelle').value || '').trim();
        if (q) L.push('  quelle: ' + yamlEscape(q));
      }
      el('kf-yaml').textContent = L.join('\\n');
      el('kf-kopieren').click();
    });
    el('kf-kopieren').addEventListener('click', function () {
      var t = el('kf-yaml').textContent;
      var fertig = function () { el('kf-meldung').style.color = 'var(--gruen)'; el('kf-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
      var fallback = function () { var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); fertig(); } catch (e) {} document.body.removeChild(ta); };
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t).then(fertig).catch(fallback); } else { fallback(); }
    });
  }
})();

/* ---- Zeitschaltuhr: nur Style wählen → fertiger Code ---- */
(function () {
  if (!document.getElementById('zs-erzeugen')) return;
  function stileZs() {
    var sel = el('zs-stil'); if (!sel) return;
    var b = ((letzterStand && letzterStand.bausteine) || []).filter(function (x) { return x.baustein === 'zeitschaltuhr'; })[0];
    var gek = (b && b.themes && b.themes.length) ? b.themes.filter(function (t2) { return STIL_NAMEN[t2]; }) : [];
    var liste = gek.length ? gek : Object.keys(STIL_NAMEN);
    var vorher = sel.value;
    sel.innerHTML = '';
    liste.forEach(function (t2) { var o = document.createElement('option'); o.value = t2; o.textContent = STIL_NAMEN[t2]; sel.appendChild(o); });
    sel.value = vorher; if (!sel.value) sel.value = liste[0];
    var hw = el('zs-stil-hinweis');
    if (hw) { hw.textContent = gek.length ? '' : wt('Hier stehen nach dem Kauf nur deine Styles.'); hw.hidden = !!gek.length; }
  }
  window.__zsStile = stileZs;
  stileZs();
  el('zs-erzeugen').addEventListener('click', function () {
    stileZs();
    el('zs-ergebnis').hidden = false; el('zs-meldung').textContent = '';
    var zeilen = ['type: custom:joamy-zeitschaltuhr-card', 'stil: ' + el('zs-stil').value];
    if (el('zs-ansicht') && el('zs-ansicht').value === 'kompakt') zeilen.push('ansicht: kompakt');
    if (el('zs-groesse') && el('zs-groesse').value === 'kompakt') zeilen.push('groesse: kompakt');
    el('zs-yaml').textContent = zeilen.join('\\n');
    el('zs-kopieren').click();
  });
  el('zs-kopieren').addEventListener('click', function () {
    var t2 = el('zs-yaml').textContent;
    var fertig = function () { el('zs-meldung').style.color = 'var(--gruen)'; el('zs-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
    var fallback = function () { var ta = document.createElement('textarea'); ta.value = t2; document.body.appendChild(ta); ta.select(); var ok2 = false; try { ok2 = document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta); if (ok2) { fertig(); } else { el('zs-meldung').style.color = 'var(--rot)'; el('zs-meldung').textContent = wt('Kopieren hat nicht geklappt — bitte den Code oben markieren und von Hand kopieren.'); } };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t2).then(fertig).catch(fallback); } else { fallback(); }
  });
})();

/* ---- Basics: Lichter + Rollläden wählen → zwei fertige Codes ---- */
(function () {
  if (!document.getElementById('bx-laden')) return;
  var geladen = false;
  function kaesten(ziel, liste, prefix) {
    var wrap = el(ziel); wrap.innerHTML = '';
    liste.forEach(function (e, i) {
      var z = document.createElement('label'); z.className = 'kf-cam';
      var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = i < 3;   // Voreinstellung bewusst klein: 8 Geraete ergaben eine 3,5-m-Karte cb.dataset.entity = e.entity;
      var sp = document.createElement('span'); sp.textContent = e.name + ' (' + e.entity + ')';
      z.appendChild(cb); z.appendChild(sp); wrap.appendChild(z);
    });
    if (!liste.length) { var p = document.createElement('p'); p.className = 'hinweis';
      p.textContent = wt('Keine gefunden.'); wrap.appendChild(p); }
  }
  el('bx-laden').addEventListener('click', function () {
    var b = this; b.disabled = true; b.textContent = wt('Lade …');
    fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      kaesten('bx-lights', d.lights || [], 'l');
      kaesten('bx-covers', d.covers || [], 'c');
      var stil = el('bx-stil'); stil.innerHTML = '';
      var bb = ((letzterStand && letzterStand.bausteine) || []).filter(function (x) { return x.baustein === 'basics'; })[0];
      var gek = (bb && bb.themes && bb.themes.length) ? bb.themes.filter(function (t2) { return STIL_NAMEN[t2]; }) : [];
      var liste = gek.length ? gek : Object.keys(STIL_NAMEN);
      liste.forEach(function (t2) { var o = document.createElement('option'); o.value = t2; o.textContent = STIL_NAMEN[t2]; stil.appendChild(o); });
      var hw = el('bx-stil-hinweis');
      if (hw) { hw.textContent = gek.length ? '' : wt('Hier stehen nach dem Kauf nur deine Styles.'); hw.hidden = !!gek.length; }
      el('bx-body').hidden = false; geladen = true;
    }).catch(function () {
      var p = document.createElement('p'); p.style.color = 'var(--rot)';
      p.textContent = wt('Konnte Home Assistant nicht erreichen.');
      el('bx-lights').innerHTML = ''; el('bx-lights').appendChild(p); el('bx-body').hidden = false;
    }).finally(function () { b.disabled = false; b.textContent = wt(geladen ? 'Neu laden' : 'Meine Lichter & Rollläden laden'); });
  });
  function angehakte(ziel) {
    return Array.prototype.slice.call(el(ziel).querySelectorAll('input:checked')).map(function (c) { return c.dataset.entity; });
  }
  function baueYaml(typ, entities) {
    var frei = el('bx-rahmen') && el('bx-rahmen').value === 'frei';
    var kompakt = el('bx-groesse').value === 'kompakt';
    var spalten = el('bx-spalten') ? parseInt(el('bx-spalten').value, 10) || 1 : 1;
    function eine(liste) {
      var L = ['type: custom:' + typ, 'stil: ' + el('bx-stil').value];
      if (frei) L.push('rahmen: frei');
      // Immer mitschreiben: spalten: 1 erzwingt „wirklich untereinander" —
      // ohne die Angabe verteilt die Karte automatisch (2 je Reihe am Handy).
      L.push('spalten: ' + Math.min(3, Math.max(1, spalten)));
      if (kompakt) L.push('groesse: kompakt');
      L.push('entities:');
      liste.forEach(function (e2) { L.push('  - ' + e2); });
      return L.join('\\n');
    }
    // Nebeneinander braucht die Geräte in EINEM Code — sonst stünden sie
    // nie in einer Reihe. Nur frei OHNE Spalten trennt je Gerät.
    if (!frei || spalten > 1) return [eine(entities)];
    // Mehrere Einzelkarten: NIE am Stück ausgeben — zusammen eingefügt lehnt
    // Home Assistant sie ab („duplicated mapping key"). Je Karte ein eigener
    // Block mit eigenem Kopierknopf (28.07.).
    return entities.map(function (e2) { return eine([e2]); });
  }
  // Zeigt einen oder mehrere Codes an; ab dem zweiten je ein eigener Kopierknopf.
  function zeigeCodes(pre, codes, leerText) {
    var halter = pre.parentNode;
    var alt = halter.querySelectorAll('.bx-extra-code');
    for (var i = 0; i < alt.length; i++) halter.removeChild(alt[i]);
    if (!codes.length) { pre.textContent = leerText; return; }
    pre.textContent = codes[0];
    for (var j = 1; j < codes.length; j++) {
      (function (code, nr) {
        var box = document.createElement('div'); box.className = 'bx-extra-code';
        var p2 = document.createElement('pre'); p2.textContent = code;
        var k = document.createElement('button'); k.type = 'button';
        k.textContent = wt('Karte %n kopieren').replace('%n', String(nr));
        k.addEventListener('click', function () { kopiereText(code); });
        box.appendChild(p2); box.appendChild(k); halter.appendChild(box);
      })(codes[j], j + 1);
    }
    if (codes.length > 1) {
      var hin = document.createElement('span'); hin.className = 'hinweis bx-extra-code';
      hin.textContent = wt('Jede Karte einzeln einfügen — Home Assistant nimmt immer nur eine auf einmal.');
      halter.insertBefore(hin, halter.firstChild);
    }
  }
  el('bx-erzeugen').addEventListener('click', function () {
    var li = angehakte('bx-lights'), co = angehakte('bx-covers');
    el('bx-ergebnis').hidden = false; el('bx-meldung').textContent = '';
    zeigeCodes(el('bx-yaml-licht'), li.length ? baueYaml('joamy-licht-card', li) : [], wt('# Kein Licht angehakt.'));
    zeigeCodes(el('bx-yaml-jal'), co.length ? baueYaml('joamy-jalousie-card', co) : [], wt('# Kein Rollladen angehakt.'));
  });
  function kopiere(quelle) { kopiereText(el(quelle).textContent); }
  function kopiereText(t2) {
    var fertig = function () { el('bx-meldung').style.color = 'var(--gruen)'; el('bx-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
    var fallback = function () { var ta = document.createElement('textarea'); ta.value = t2; document.body.appendChild(ta); ta.select(); var ok2 = false; try { ok2 = document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta); if (ok2) { fertig(); } else { el('bx-meldung').style.color = 'var(--rot)'; el('bx-meldung').textContent = wt('Kopieren hat nicht geklappt — bitte den Code oben markieren und von Hand kopieren.'); } };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t2).then(fertig).catch(fallback); } else { fallback(); }
  }
  window.__bxSprache = function () {
    var b = el('bx-laden'); if (b) b.textContent = wt(geladen ? 'Neu laden' : 'Meine Lichter & Rollläden laden');
  };
  el('bx-kopieren-licht').addEventListener('click', function () { kopiere('bx-yaml-licht'); });
  el('bx-kopieren-jal').addEventListener('click', function () { kopiere('bx-yaml-jal'); });
})();

/* ---- Button-Baukasten: visuell zusammenbauen, Code mit einem Klick ----
   Vorschau = schematischer Button (Add-on-Optik, nicht der Karten-Style);
   Motion/Farben/Zustände live. Sensor-Chips per Pointer auf die Eck-Slots
   ziehen. Kontextabhängig: Sprung ohne Gerät/Farben/Bewegung, zustandslose
   Domänen (Szene/Skript/Knopf) ohne Farben/Bewegung, Schloss fest grün/rot. */
(function () {
  if (!document.getElementById('bk-laden')) return;
  var NL = String.fromCharCode(10);
  var geladen = false, symbolWahl = '', anZ = true;
  function P(d) { return '<path d="' + d + '"/>'; }
  function C(cx, cy, r, f) { return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '"' + (f ? ' fill="currentColor" stroke="none"' : '') + '/>'; }
  function R(x, y, w, h, rx) { return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="' + rx + '"/>'; }
  /* Dieselben 43 Formen wie in der Karte (bx-Symbolbibliothek). */
  var SYM = {
    haustuer: P('M4 21V5.5L12 2l8 3.5V21') + P('M9 21v-8h6v8') + C(13.6, 16.5, .9, 1),
    tuer: R(6, 3, 12, 18, 1.5) + C(15, 12, .9, 1),
    schloss_zu: R(5, 10.5, 14, 9.5, 2) + P('M8 10.5V7a4 4 0 0 1 8 0v3.5') + P('M12 14.5v2.5'),
    schloss_auf: R(5, 10.5, 14, 9.5, 2) + P('M8 10.5V7a4 4 0 0 1 7.7-1.5') + P('M12 14.5v2.5'),
    schluessel: C(8, 8, 4.2) + P('M11 11l9 9') + P('M16.5 16.5l2.4-2.4M19 19l2-2'),
    garage: P('M3 21V8l9-5 9 5v13') + P('M6.5 21v-9h11v9') + P('M6.5 15h11') + P('M6.5 18h11'),
    tor: P('M3 20V8M21 20V8') + P('M3 10h18M3 14h18M3 18h18') + P('M7 20V10M12 20V10M17 20V10'),
    licht: P('M9 18h6M10 21h4') + P('M12 3a6 6 0 0 1 4 10.5c-.8.7-1 1.6-1 2.5H9c0-.9-.2-1.8-1-2.5A6 6 0 0 1 12 3z'),
    deckenlampe: P('M12 2v5') + P('M5 13a7 7 0 0 1 14 0z') + P('M12 16.5v1') + C(12, 20, 1.4),
    stehlampe: P('M9 3h7l-2.5 7h-4z') + P('M12 10v9') + P('M8 21h8'),
    steckdose: C(12, 12, 9) + P('M9.5 9.5v3M14.5 9.5v3') + P('M12 15.5v2'),
    ventilator: C(12, 12, 2.2) + P('M12 9.8C12 6 10 4 7.5 4 6 4 5 5 5 6.4 5 9 8.5 9.8 12 9.8z') + P('M14.2 12c3.8 0 5.8-2 5.8-4.5C20 6 19 5 17.6 5 15 5 14.2 8.5 14.2 12z') + P('M12 14.2c0 3.8 2 5.8 4.5 5.8 1.5 0 2.5-1 2.5-2.4 0-2.6-3.5-3.4-7-3.4z') + P('M9.8 12c-3.8 0-5.8 2-5.8 4.5C4 18 5 19 6.4 19 9 19 9.8 15.5 9.8 12z'),
    klima: R(3, 5, 18, 7, 2) + P('M7 8.5h10') + P('M7 15c0 2-1.5 2.5-1.5 4M12 15c0 2-1.5 2.5-1.5 4M17 15c0 2-1.5 2.5-1.5 4'),
    heizung: P('M5 10c2-2.5.5-4.5 2-6.5M10 10c2-2.5.5-4.5 2-6.5M15 10c2-2.5.5-4.5 2-6.5') + R(4, 13, 16, 7, 2) + P('M7 13v7M11 13v7M15 13v7'),
    thermometer: P('M10 4a2 2 0 0 1 4 0v9.3a4.5 4.5 0 1 1-4 0z') + C(12, 17.5, 1.6, 1),
    rollo: R(3, 3, 18, 18, 1.5) + P('M3 7h18M3 10.5h18M3 14h18') + P('M12 14v4.5') + C(12, 19.6, .9),
    vorhang: P('M4 4h16') + P('M6 4c1 6-.5 12-2 16 4-1.5 5-3 6-6V4M18 4c-1 6 .5 12 2 16-4-1.5-5-3-6-6V4'),
    fenster: R(4, 3, 16, 18, 1.5) + P('M12 3v18M4 12h16'),
    kamera: R(2.5, 7, 15, 10, 2.5) + P('M17.5 10.5 21.5 8v8l-4-2.5') + C(9.5, 12, 2.6),
    sirene: P('M7 18v-6a5 5 0 0 1 10 0v6') + R(4.5, 18, 15, 3, 1.2) + P('M12 3v2M5 5.5 6.5 7M19 5.5 17.5 7'),
    glocke: P('M6 16v-5.5a6 6 0 0 1 12 0V16l1.6 2.5H4.4z') + P('M10.3 21a2 2 0 0 0 3.4 0'),
    musik: P('M9 18V6l10-2.5V15') + C(6.6, 18, 2.5) + C(16.6, 15, 2.5),
    tv: R(3, 5, 18, 12, 2) + P('M8.5 21h7M12 17v4'),
    staubsauger: C(12, 11, 7.5) + C(12, 11, 3.2) + C(12, 11, .9, 1) + P('M5.5 19.5h13'),
    waschmaschine: R(4, 2.8, 16, 18.4, 2) + C(12, 13.4, 4.6) + P('M8.6 12.2c1.4 1.2 3.6 1.2 5-.1') + C(7.4, 6, .9) + C(10.4, 6, .9),
    wasser: P('M12 3.5c3.4 4.2 6 7.6 6 10.7a6 6 0 0 1-12 0c0-3.1 2.6-6.5 6-10.7z'),
    pflanze: P('M12 21v-7') + P('M12 14C12 9 9 7 4.5 7c0 5 3 7 7.5 7z') + P('M12 12c0-4 2.5-5.7 6.5-5.7 0 4.2-2.5 5.9-6.5 5.9') + P('M8 21h8'),
    kaffee: P('M5 9h11v6a5 5 0 0 1-10 0z') + P('M16 10h2.2a2.3 2.3 0 0 1 0 4.6H16') + P('M8 5.5c0-1 .8-1 .8-2M11.5 5.5c0-1 .8-1 .8-2'),
    herd: R(3.5, 3.5, 17, 17, 2) + C(8.4, 8.4, 2.2) + C(15.6, 8.4, 2.2) + C(8.4, 15.6, 2.2) + C(15.6, 15.6, 2.2),
    kuehlschrank: R(6, 2.5, 12, 19, 1.8) + P('M6 9.5h12') + P('M9 6v1.5M9 13v3'),
    auto: P('M4 16v-4l2-5h12l2 5v4') + P('M4 12h16') + C(7.5, 16.8, 1.7) + C(16.5, 16.8, 1.7) + P('M3 16.8h2.6M9.4 16.8h5.2M18.6 16.8H21'),
    ladeport: R(6, 6, 12, 15, 2) + P('M12 2.8v3.2M9 4v2M15 4v2') + P('M12.8 10 10 14h4l-2.8 4'),
    szene: P('M12 3l2.2 4.5 5 .7-3.6 3.5.9 5-4.5-2.4L7.5 16.7l.9-5L4.8 8.2l5-.7z'),
    stern: P('M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.5l-5.9 3.1 1.2-6.5L2.5 9.5l6.6-.9z'),
    blitz: P('M13 2 4.5 13.5H11L9.5 22 19 10h-6.5z'),
    power: P('M12 3v8') + P('M6.2 6.5a8 8 0 1 0 11.6 0'),
    play: P('M7 4.5v15l13-7.5z'),
    haus: P('M3.5 11 12 3.5 20.5 11') + P('M5.5 9.5V20h13V9.5'),
    sprung: P('M5 12h13') + P('M13 6l6 6-6 6') + P('M5 5v14'),
    zahnrad: C(12, 12, 3.2) + P('M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.2 5.2l2.1 2.1M16.7 16.7l2.1 2.1M18.8 5.2l-2.1 2.1M7.3 16.7l-2.1 2.1'),
    sonne: C(12, 12, 4.2) + P('M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8'),
    mond: P('M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z'),
    feuer: P('M12 2.5c1 3-3.5 5-3.5 9a3.5 3.5 0 0 0 7 0c0-1.4-.7-2.6-1.5-3.7') + P('M12 21.5a6.5 6.5 0 0 1-6.5-6.5c0-2 1-3.8 2-5.3') + P('M12 21.5a6.5 6.5 0 0 0 6.5-6.5c0-1.5-.5-2.9-1.3-4.2')
  };
  var VORSCHLAG = { lock: 'haustuer', light: 'licht', switch: 'steckdose', fan: 'ventilator',
    cover: 'rollo', scene: 'szene', script: 'blitz', button: 'power', input_boolean: 'power',
    input_button: 'power', climate: 'klima', media_player: 'musik', vacuum: 'staubsauger', camera: 'kamera' };
  var MOTION_STD = { fan: 'dreh', light: 'glow', switch: 'glow', input_boolean: 'glow',
    media_player: 'puls', vacuum: 'puls', cover: 'puls', climate: 'puls', scene: 'funkeln', lock: 'glow' };
  var STATUSLOS = ['scene', 'script', 'button', 'input_button'];
  function svgVon(n) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + (SYM[n] || SYM.power) + '</svg>'; }
  function domainJetzt() { return el('bk-funktion').value === 'sprung' ? '' : (el('bk-entity').value || '').split('.')[0]; }
  function istStatuslos() { return el('bk-funktion').value === 'sprung' || STATUSLOS.indexOf(domainJetzt()) >= 0; }

  /* ---- Symbol-Galerie ---- */
  function markiereGitter() {
    Array.prototype.forEach.call(el('bk-symgrid').querySelectorAll('button'), function (b) {
      b.classList.toggle('gewaehlt', (b.dataset.sym || '') === symbolWahl);
    });
  }
  function baueGitter() {
    var g = el('bk-symgrid'); g.innerHTML = '';
    var auto = document.createElement('button'); auto.type = 'button'; auto.dataset.sym = '';
    auto.textContent = wt('Automatisch').slice(0, 4); auto.title = wt('Automatisch');
    auto.addEventListener('click', function () { symbolWahl = ''; markiereGitter(); vorschau(); });
    g.appendChild(auto);
    Object.keys(SYM).forEach(function (n) {
      var b = document.createElement('button'); b.type = 'button'; b.dataset.sym = n;
      b.title = n.replace(/_/g, ' '); b.innerHTML = svgVon(n);
      b.addEventListener('click', function () { symbolWahl = n; markiereGitter(); vorschau(); });
      g.appendChild(b);
    });
    markiereGitter();
  }

  /* ---- Kontextabhängige Felder: Sinnloses bleibt unsichtbar ---- */
  function felder() {
    var fn = el('bk-funktion').value, d = domainJetzt(), los = istStatuslos();
    el('bk-feld-entity').hidden = fn !== 'geraet';
    el('bk-feld-ziel').hidden = fn !== 'sprung';
    el('bk-feld-farben').hidden = los || d === 'lock';
    el('bk-feld-motion').hidden = los;
    var namen = { glow: wt('Glühen'), puls: wt('Pulsieren'), dreh: wt('Drehen'), wippe: wt('Wippen'), funkeln: wt('Funkeln') };
    var std = MOTION_STD[d] || 'glow';
    el('bk-motion-hinweis').textContent = (fn === 'geraet' && el('bk-entity').value) ? wt('Automatisch heißt hier:') + ' ' + (namen[std] || std) : '';
  }

  /* ---- Live-Vorschau ---- */
  function vorschau() {
    var v = el('bk-vorschau'), fn = el('bk-funktion').value, d = domainJetzt(), los = istStatuslos();
    var sym = symbolWahl || (fn === 'sprung' ? 'sprung' : (VORSCHLAG[d] || 'power'));
    el('bk-ico').innerHTML = svgVon(sym);
    var o = el('bk-entity').selectedOptions && el('bk-entity').selectedOptions[0];
    el('bk-name').textContent = el('bk-label').value || (fn === 'sprung' ? wt('Weiter') : ((o && o.dataset.name) || 'Button'));
    v.className = 'bk-knopf';
    var mArt = el('bk-motion').value === 'std' ? (MOTION_STD[d] || 'glow') : el('bk-motion').value;
    if (!los) {
      if (d === 'lock') { v.classList.add(anZ ? 'sicher' : 'offen'); }
      else if (anZ) { v.classList.add('an'); if (mArt !== 'aus') v.classList.add('m-' + mArt); }
    }
    el('bk-status').textContent = los ? '' : (d === 'lock' ? wt(anZ ? 'verriegelt' : 'offen') : wt(anZ ? 'an' : 'aus'));
    var eigene = !los && d !== 'lock' && el('bk-farben-eigene').checked;
    v.style.setProperty('--knopf-an', eigene ? el('bk-farbe-an').value : '');
    v.style.setProperty('--knopf-aus', eigene ? el('bk-farbe-aus').value : '');
  }
  el('bk-vorschau').addEventListener('click', function (ev) {
    if (ev.target.closest && ev.target.closest('.bk-chip')) return;
    if (Date.now() - ebenGezogen < 300) return;
    anZ = !anZ; vorschau();
  });

  /* ---- Magnet-Leinwand: ALLES auf die Karte ziehen ----
     Palette → Karte: frei platzieren (x/y in %), Ecken/Mittelachsen rasten
     magnetisch ein; ein schaltbares Gerät in der MITTE abgelegt WIRD der
     Button. Von der Karte herunterziehen = entfernen. */
  var SCHALTBAR = ['lock', 'light', 'switch', 'fan', 'cover', 'scene', 'script', 'button', 'input_boolean', 'media_player'];
  var ECKEN = { ol: [15, 14], or: [85, 14], ul: [15, 86], ur: [85, 86] };
  var ebenGezogen = 0;
  function chipBau(entity, name, wert) {
    var chip = document.createElement('span'); chip.className = 'bk-chip';
    chip.dataset.entity = entity; chip.dataset.name = name || entity; chip.dataset.wert = wert || '';
    var b = document.createElement('b'); b.textContent = wert || '';
    var i2 = document.createElement('i'); i2.textContent = name || entity;
    chip.appendChild(b); chip.appendChild(i2);
    // Ein Sensor OHNE Wert ist trotzdem ein Sensor — nur schaltbare Domaenen
    // duerfen wie ein Geraet aussehen (sonst landen 5 wertlose Sensoren als 'Geraet').
    var _dom = String(entity).split('.')[0];
    if (!wert && SCHALTBAR.indexOf(_dom) >= 0) chip.classList.add('geraet');
    else if (!wert) { b.textContent = '—'; }
    return chip;
  }
  function kartePos(x, y) {
    var r = el('bk-vorschau').getBoundingClientRect();
    return { x: (x - r.left) / r.width * 100, y: (y - r.top) / r.height * 100,
      drin: x >= r.left - 12 && x <= r.right + 12 && y >= r.top - 12 && y <= r.bottom + 12 };
  }
  function schnapp(p, schaltbar) {
    var s = { x: Math.max(4, Math.min(96, p.x)), y: Math.max(5, Math.min(95, p.y)), pos: '', mitte: false };
    s.mitte = !!schaltbar && Math.abs(p.x - 50) < 24 && Math.abs(p.y - 50) < 26;
    if (s.mitte) return s;
    for (var k in ECKEN) { var e = ECKEN[k];
      if (Math.abs(p.x - e[0]) < 12 && Math.abs(p.y - e[1]) < 13) { s.x = e[0]; s.y = e[1]; s.pos = k; return s; } }
    if (Math.abs(p.x - 50) < 6) s.x = 50;
    if (Math.abs(p.y - 50) < 7) s.y = 50;
    return s;
  }
  function hilfenZeig(s) {
    var H = el('bk-hilfen');
    H.querySelector('.bk-linie.v').classList.toggle('an', !!s && !s.pos && !s.mitte && s.x === 50);
    H.querySelector('.bk-linie.h').classList.toggle('an', !!s && !s.pos && !s.mitte && s.y === 50);
    Array.prototype.forEach.call(H.querySelectorAll('.bk-punkt'), function (pk) {
      pk.classList.toggle('an', !!s && s.pos === pk.dataset.a); });
    H.querySelector('.bk-mittezone').classList.toggle('an', !!s && s.mitte);
  }
  function hauptGeraet(entity) {
    el('bk-entity').value = entity;
    symbolWahl = ''; markiereGitter(); felder(); vorschau();
    var ico = el('bk-ico'); ico.classList.remove('pop'); void ico.offsetWidth; ico.classList.add('pop');
    setTimeout(function () { ico.classList.remove('pop'); }, 600);
  }
  function platziere(chip, s) {
    chip.classList.add('auf-karte');
    chip.style.left = s.x.toFixed(0) + '%'; chip.style.top = s.y.toFixed(0) + '%';
    chip.dataset.pos = s.pos || ''; chip.dataset.x = s.x.toFixed(0); chip.dataset.y = s.y.toFixed(0);
    el('bk-vorschau').appendChild(chip);
    chip.classList.remove('plopp'); void chip.offsetWidth; chip.classList.add('plopp');
  }
  function ziehStart(ev, quelle, istNeu) {
    ev.preventDefault();
    var start = { x: ev.clientX, y: ev.clientY }, aktiv = false, geist = null;
    var schaltbar = SCHALTBAR.indexOf((quelle.dataset.entity || '').split('.')[0]) >= 0;
    var move = function (e2) {
      if (!aktiv && Math.abs(e2.clientX - start.x) + Math.abs(e2.clientY - start.y) < 7) return;
      if (!aktiv) {
        aktiv = true;
        geist = istNeu ? chipBau(quelle.dataset.entity, quelle.dataset.name, quelle.dataset.wert) : quelle;
        if (istNeu) document.body.appendChild(geist);
        geist.classList.add('zieht'); document.body.classList.add('bk-ziehen');
      }
      geist.style.position = 'fixed'; geist.style.left = (e2.clientX - 34) + 'px';
      geist.style.top = (e2.clientY - 14) + 'px'; geist.style.zIndex = '99'; geist.style.transform = 'none';
      var p = kartePos(e2.clientX, e2.clientY);
      el('bk-vorschau').classList.toggle('magnet', p.drin);
      hilfenZeig(p.drin ? schnapp(p, schaltbar) : null);
    };
    var up = function (e2) {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      if (!aktiv) return;
      ebenGezogen = Date.now();
      document.body.classList.remove('bk-ziehen');
      el('bk-vorschau').classList.remove('magnet');
      hilfenZeig(null);
      geist.classList.remove('zieht');
      geist.style.position = ''; geist.style.left = ''; geist.style.top = '';
      geist.style.zIndex = ''; geist.style.transform = '';
      var p = kartePos(e2.clientX, e2.clientY);
      if (!p.drin) { geist.remove(); return; }
      var s = schnapp(p, schaltbar);
      if (s.mitte) { geist.remove(); hauptGeraet(quelle.dataset.entity); return; }
      if (istNeu && el('bk-vorschau').querySelectorAll('.bk-chip.auf-karte').length >= 6) { geist.remove(); return; }
      platziere(geist, s);
      if (istNeu) kartenZiehbar(geist);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  }
  function paletteZiehbar(chip) { chip.addEventListener('pointerdown', function (ev) { ziehStart(ev, chip, true); }); }
  function kartenZiehbar(chip) { chip.addEventListener('pointerdown', function (ev) { ziehStart(ev, chip, false); }); }
  function bauePalette(d) {
    var pal = el('bk-palette'); pal.innerHTML = '';
    var grp = [['sensors', 'Sensoren'], ['locks', 'Schlösser'], ['lights', 'Lichter'], ['switches', 'Schalter'],
      ['fans', 'Ventilatoren'], ['covers', 'Rollläden'], ['scenes', 'Szenen'], ['scripts', 'Skripte'],
      ['buttons', 'Knöpfe'], ['input_booleans', 'Helfer (an/aus)'], ['media_players', 'Medien']];
    grp.forEach(function (g) {
      var L = d[g[0]] || []; if (!L.length) return;
      var kopf = document.createElement('div'); kopf.className = 'bk-pal-kopf'; kopf.dataset.de = g[1]; kopf.textContent = wt(g[1]);
      pal.appendChild(kopf);
      L.forEach(function (e) { var c = chipBau(e.entity, e.name, e.wert || ''); paletteZiehbar(c); pal.appendChild(c); });
    });
    el('bk-suche').placeholder = wt('Suchen …');
  }
  el('bk-suche').addEventListener('input', function () {
    var q = this.value.trim().toLowerCase();
    var kopf = null, sichtbar = 0;
    Array.prototype.forEach.call(el('bk-palette').children, function (k) {
      if (k.classList.contains('bk-pal-kopf')) {
        if (kopf) kopf.hidden = sichtbar === 0;
        kopf = k; sichtbar = 0; return;
      }
      var passt = !q || ((k.dataset.name || '') + ' ' + (k.dataset.entity || '')).toLowerCase().indexOf(q) >= 0;
      k.hidden = !passt; if (passt) sichtbar++;
    });
    if (kopf) kopf.hidden = sichtbar === 0;
  });

  /* ---- Laden ---- */
  el('bk-laden').addEventListener('click', function () {
    var kb = this; kb.disabled = true; kb.textContent = wt('Lade …');
    fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      var grp = [['locks', 'Schlösser'], ['lights', 'Lichter'], ['switches', 'Schalter'],
        ['fans', 'Ventilatoren'], ['covers', 'Rollläden'], ['scenes', 'Szenen'], ['scripts', 'Skripte'],
        ['buttons', 'Knöpfe'], ['input_booleans', 'Helfer (an/aus)'], ['media_players', 'Medien']];
      var sel = el('bk-entity'); sel.innerHTML = '';
      grp.forEach(function (g) {
        var L = d[g[0]] || []; if (!L.length) return;
        var og = document.createElement('optgroup'); og.dataset.de = g[1]; og.label = wt(g[1]);
        L.forEach(function (e) { var o = document.createElement('option'); o.value = e.entity;
          o.textContent = e.name + ' (' + e.entity + ')'; o.dataset.name = e.name; og.appendChild(o); });
        sel.appendChild(og);
      });
      bauePalette(d);
      var stil = el('bk-stil'); stil.innerHTML = '';
      var bb = ((letzterStand && letzterStand.bausteine) || []).filter(function (x) { return x.baustein === 'basics'; })[0];
      var gek = (bb && bb.themes && bb.themes.length) ? bb.themes.filter(function (t2) { return STIL_NAMEN[t2]; }) : [];
      var liste = gek.length ? gek : Object.keys(STIL_NAMEN);
      liste.forEach(function (t2) { var o = document.createElement('option'); o.value = t2; o.textContent = STIL_NAMEN[t2]; stil.appendChild(o); });
      var hw = el('bk-stil-hinweis');
      if (hw) { hw.textContent = gek.length ? '' : wt('Hier stehen nach dem Kauf nur deine Styles.'); hw.hidden = !!gek.length; }
      el('bk-label').placeholder = wt('automatisch — Name des Geräts');
      baueGitter(); felder(); vorschau();
      el('bk-body').hidden = false; geladen = true;
    }).catch(function () {
      el('bk-meldung').style.color = 'var(--rot)';
      el('bk-meldung').textContent = wt('Konnte Home Assistant nicht erreichen.');
      el('bk-body').hidden = false;
    }).finally(function () { kb.disabled = false; kb.textContent = wt(geladen ? 'Neu laden' : 'Meine Geräte & Sensoren laden'); });
  });
  el('bk-funktion').addEventListener('change', function () { symbolWahl = ''; markiereGitter(); felder(); vorschau(); });
  el('bk-entity').addEventListener('change', function () { symbolWahl = ''; markiereGitter(); felder(); vorschau(); });
  el('bk-label').addEventListener('input', vorschau);
  el('bk-motion').addEventListener('change', vorschau);
  el('bk-farben-eigene').addEventListener('change', function () { el('bk-farben').hidden = !this.checked; vorschau(); });
  el('bk-farbe-an').addEventListener('input', vorschau);
  el('bk-farbe-aus').addEventListener('input', vorschau);

  /* ---- Ein Klick: Code anzeigen und kopieren ---- */
  function kopiereBk() {
    var t2 = el('bk-yaml').textContent;
    var fertig = function () { el('bk-meldung').style.color = 'var(--gruen)'; el('bk-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
    var fallback = function () { var ta = document.createElement('textarea'); ta.value = t2; document.body.appendChild(ta); ta.select(); var ok2 = false; try { ok2 = document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta); if (ok2) { fertig(); } else { el('bk-meldung').style.color = 'var(--rot)'; el('bk-meldung').textContent = wt('Kopieren hat nicht geklappt — bitte den Code oben markieren und von Hand kopieren.'); } };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t2).then(fertig).catch(fallback); } else { fallback(); }
  }
  window.__bkSprache = function () {
    var b = el('bk-laden'); if (b) b.textContent = wt(geladen ? 'Neu laden' : 'Meine Geräte & Sensoren laden');
    var s = el('bk-suche'); if (s) s.placeholder = wt('Suchen …');
    var lb = el('bk-label'); if (lb) lb.placeholder = wt('automatisch — Name des Geräts');
    // Paletten-Überschriften + Gerätegruppen neu beschriften
    Array.prototype.forEach.call(document.querySelectorAll('#bk-palette .bk-pal-kopf'), function (k) {
      if (k.dataset.de) k.textContent = wt(k.dataset.de);
    });
    Array.prototype.forEach.call(document.querySelectorAll('#bk-entity optgroup'), function (g) {
      if (g.dataset.de) g.label = wt(g.dataset.de);
    });
    var auto = document.querySelector('#bk-symgrid button[data-sym=""]');
    if (auto) { auto.textContent = wt('Automatisch').slice(0, 4); auto.title = wt('Automatisch'); }
    felder(); vorschau();
  };
  el('bk-erzeugen').addEventListener('click', function () {
    var fn = el('bk-funktion').value, d = domainJetzt(), los = istStatuslos();
    el('bk-meldung').textContent = '';
    var L = ['type: custom:joamy-button-card', 'stil: ' + el('bk-stil').value];
    if (fn === 'sprung') { L.push('aktion: sprung'); L.push('ziel: ' + yamlEscape(el('bk-ziel').value || '/')); }
    else {
      if (!el('bk-entity').value) { el('bk-meldung').style.color = 'var(--rot)';
        el('bk-meldung').textContent = wt('Erst ein Gerät wählen — oder oben auf „Sprung“ stellen.'); return; }
      L.push('entity: ' + el('bk-entity').value);
    }
    // yamlEscape kennt @ & * - [ { ! | > % ? und Leerzeichen — Eigenbau-Quoting
    // erzeugte bei „@Zuhause" oder „- Küche" YAML, das HA ablehnt (28.07.).
    if (el('bk-label').value) L.push('label: ' + yamlEscape(el('bk-label').value));
    if (symbolWahl) L.push('symbol: ' + symbolWahl);
    if (!los && d !== 'lock' && el('bk-farben-eigene').checked) {
      L.push('farbe_an: "' + el('bk-farbe-an').value + '"');
      L.push('farbe_aus: "' + el('bk-farbe-aus').value + '"');
    }
    if (!los && el('bk-motion').value !== 'std') L.push('motion: ' + el('bk-motion').value);
    if (el('bk-groesse').value === 'kompakt') L.push('groesse: kompakt');
    var ex = [];
    Array.prototype.forEach.call(el('bk-vorschau').querySelectorAll('.bk-chip.auf-karte'), function (c) {
      ex.push({ entity: c.dataset.entity, pos: c.dataset.pos || '', x: c.dataset.x, y: c.dataset.y });
    });
    if (ex.length) { L.push('extras:'); ex.forEach(function (e) {
      L.push('  - entity: ' + e.entity);
      if (e.pos) { L.push('    pos: ' + e.pos); }
      else { L.push('    x: ' + e.x); L.push('    y: ' + e.y); } }); }
    el('bk-ergebnis').hidden = false;
    el('bk-yaml').textContent = L.join(NL);
    kopiereBk();
  });
})();

/* ---- Kalender: Auto-Vorschlag (abwählbar) → Ein-Klick-Code ---- */
(function () {
  if (!document.getElementById('kl-laden')) return;
  var NL = String.fromCharCode(10);
  var geladen = false;
  el('kl-laden').addEventListener('click', function () {
    var b = this; b.disabled = true; b.textContent = wt('Lade …');
    fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      var wrap = el('kl-liste'); wrap.innerHTML = '';
      var L = d.calendars || [];
      L.forEach(function (e) {
        var z = document.createElement('label'); z.className = 'kf-cam';
        var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true; cb.dataset.entity = e.entity;
        var sp = document.createElement('span'); sp.textContent = e.name + ' (' + e.entity + ')';
        z.appendChild(cb); z.appendChild(sp); wrap.appendChild(z);
      });
      if (!L.length) { var p2 = document.createElement('p'); p2.className = 'hinweis';
        p2.textContent = wt('Keine Kalender gefunden — in Home Assistant unter Einstellungen → Integrationen einen „Lokalen Kalender" anlegen.'); wrap.appendChild(p2); }
      var stil = el('kl-stil'); stil.innerHTML = '';
      var bb = ((letzterStand && letzterStand.bausteine) || []).filter(function (x) { return x.baustein === 'kalender'; })[0];
      var gek = (bb && bb.themes && bb.themes.length) ? bb.themes.filter(function (t2) { return STIL_NAMEN[t2]; }) : [];
      var liste = gek.length ? gek : Object.keys(STIL_NAMEN);
      liste.forEach(function (t2) { var o = document.createElement('option'); o.value = t2; o.textContent = STIL_NAMEN[t2]; stil.appendChild(o); });
      var hw = el('kl-stil-hinweis');
      if (hw) { hw.textContent = gek.length ? '' : wt('Hier stehen nach dem Kauf nur deine Styles.'); hw.hidden = !!gek.length; }
      el('kl-body').hidden = false; geladen = true;
    }).catch(function () {
      el('kl-meldung').style.color = 'var(--rot)';
      el('kl-meldung').textContent = wt('Konnte Home Assistant nicht erreichen.');
      el('kl-body').hidden = false;
    }).finally(function () { b.disabled = false; b.textContent = wt(geladen ? 'Neu laden' : 'Meine Kalender laden'); });
  });
  window.__klSprache = function () {
    var b = el('kl-laden'); if (b) b.textContent = wt(geladen ? 'Neu laden' : 'Meine Kalender laden');
  };
  el('kl-erzeugen').addEventListener('click', function () {
    var alle = Array.prototype.slice.call(el('kl-liste').querySelectorAll('input[type=checkbox]'));
    var an = alle.filter(function (c) { return c.checked; });
    el('kl-meldung').textContent = '';
    var L = ['type: custom:joamy-kalender-card', 'stil: ' + el('kl-stil').value];
    // Alle angehakt = Auto-Modus (KEINE entities-Zeile): die Karte findet
    // auch künftige Kalender von selbst. Teilmenge = explizite Liste.
    if (alle.length && an.length && an.length < alle.length) {
      L.push('entities:');
      an.forEach(function (c) { L.push('  - ' + c.dataset.entity); });
    }
    if (!alle.length) { el('kl-meldung').style.color = 'var(--rot)';
      el('kl-meldung').textContent = wt('Keine Kalender gefunden — in Home Assistant unter Einstellungen → Integrationen einen „Lokalen Kalender" anlegen.'); return; }
    if (!an.length) { el('kl-meldung').style.color = 'var(--rot)';
      el('kl-meldung').textContent = wt('Mindestens einen Kalender anhaken.'); return; }
    if (el('kl-groesse').value === 'kompakt') L.push('groesse: kompakt');
    el('kl-ergebnis').hidden = false;
    el('kl-yaml').textContent = L.join(NL);
    var t2 = el('kl-yaml').textContent;
    var fertig = function () { el('kl-meldung').style.color = 'var(--gruen)'; el('kl-meldung').textContent = wt('Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'); };
    var fallback = function () { var ta = document.createElement('textarea'); ta.value = t2; document.body.appendChild(ta); ta.select(); var ok2 = false; try { ok2 = document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta); if (ok2) { fertig(); } else { el('kl-meldung').style.color = 'var(--rot)'; el('kl-meldung').textContent = wt('Kopieren hat nicht geklappt — bitte den Code oben markieren und von Hand kopieren.'); } };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t2).then(fertig).catch(fallback); } else { fallback(); }
  });
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

  var mkGeladen = false;
  // Sprachwechsel: alles nachziehen, was dieses Skript selbst geschrieben hat.
  window.__mkSprache = function () {
    el('mk-laden').textContent = wt(mkGeladen ? 'Lautsprecher neu laden' : 'Meine Lautsprecher laden');
    el('mk-lage-text').textContent = lageText();
    var rows = document.querySelectorAll('#mk-players .kf-cam input[type=text]');
    for (var i = 0; i < rows.length; i++) rows[i].placeholder = wt('Name');
  };
  el('mk-laden').textContent = wt('Meine Lautsprecher laden');
  el('mk-laden').addEventListener('click', function () {
    var b = el('mk-laden'); b.disabled = true; b.textContent = wt('lädt …');
    fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
      lautsprecher = (d && d.media_players) || [];
      var ziel = el('mk-players'); ziel.innerHTML = '';
      if (d && d.fehler) {
        // Der Endpunkt hat geantwortet, aber mit einem echten Fehler — den sagen
        // wir wörtlich, statt fälschlich „richte Lautsprecher ein" zu behaupten.
        var pf = document.createElement('p'); pf.style.color = 'var(--rot)';
        pf.textContent = wt('Konnte Home Assistant nicht erreichen.') + ' (' + d.fehler + ')';
        ziel.appendChild(pf);
      } else if (!lautsprecher.length) {
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
      mkGeladen = true;
      el('mk-body').hidden = false;
      griffZeichnen();
    }).catch(function () {
      el('mk-players').textContent = wt('Konnte Home Assistant nicht erreichen.');
      el('mk-body').hidden = false;
    }).finally(function () { b.disabled = false; b.textContent = wt(mkGeladen ? 'Lautsprecher neu laden' : 'Meine Lautsprecher laden'); });
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
    if (el('mk-groesse') && el('mk-groesse').value === 'kompakt') L.splice(2, 0, 'groesse: kompakt');
    gewaehlt.forEach(function (p) { L.push('  - entity: ' + p.entity); L.push('    name: ' + yamlEscape(p.name)); });
    L.push('drawer:');
    L.push('  seite: ' + lage.seite);
    L.push('  hoehe: ' + Math.round(lage.hoehe));
    el('mk-yaml').textContent = L.join('\\n');
    el('mk-kopieren').click();
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

    async def medienquellen(request: web.Request) -> web.Response:
        try:
            return web.json_response(await installer.medienquellen())
        except Exception as e:
            LOG.error("Medienquellen-Endpunkt fehlgeschlagen: %s", e)
            return web.json_response({"ok": False, "fehler": str(e), "quellen": []}, status=500)

    async def knopf_get(request: web.Request) -> web.Response:
        try:
            return web.json_response(await installer.knopf_status())
        except Exception as e:
            LOG.error("Knopf-Status fehlgeschlagen: %s", e)
            return web.json_response({"ok": False, "verfuegbar": False, "fehler": str(e)}, status=500)

    async def knopf_post(request: web.Request) -> web.Response:
        try:
            daten = await request.json()
            return web.json_response(await installer.knopf_schalten(bool(daten.get("sichtbar"))))
        except Exception as e:
            LOG.error("Knopf-Schalten fehlgeschlagen: %s", e)
            return web.json_response({"ok": False, "fehler": str(e)}, status=500)

    async def anleitung(request: web.Request) -> web.StreamResponse:
        weg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anleitung.mp4")
        if not os.path.exists(weg):
            raise web.HTTPNotFound()
        return web.FileResponse(weg, headers={"Cache-Control": "public, max-age=604800",
                                              "Content-Type": "video/mp4"})

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
    app.router.add_get("/medienquellen", medienquellen)
    app.router.add_get("/knopf", knopf_get)
    app.router.add_post("/knopf", knopf_post)
    app.router.add_get("/anleitung.mp4", anleitung)
    return app
