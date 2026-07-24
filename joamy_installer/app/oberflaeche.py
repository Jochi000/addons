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

from aiohttp import web

from kern import Installer, LOG_PUFFER

LOG = logging.getLogger("joamy.oberflaeche")

SEITE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JoAmy Installer</title>
<style>
  :root {
    --papier: #f7f1e6; --karte: #fffdf8; --tinte: #3d3126;
    --bronze: #8c6239; --bronze-hell: #a67c52; --linie: #e8dcc8;
    --gruen: #4c7a4c; --rot: #a04338;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--papier); color: var(--tinte);
    font: 16px/1.55 Georgia, 'Times New Roman', serif;
    padding: 24px 16px 48px;
  }
  .rahmen { max-width: 720px; margin: 0 auto; display: grid; gap: 18px; }
  header h1 { font-size: 1.7rem; font-weight: normal; color: var(--bronze); }
  header p { color: #7a6a56; font-style: italic; }
  .karte {
    background: var(--karte); border: 1px solid var(--linie); border-radius: 14px;
    padding: 20px 22px; box-shadow: 0 2px 10px rgba(120, 90, 50, .07);
  }
  .karte h2 {
    font-size: .8rem; letter-spacing: .14em; text-transform: uppercase;
    color: var(--bronze-hell); margin-bottom: 12px; font-weight: normal;
  }
  #code {
    font: 700 3rem/1.1 ui-monospace, 'Courier New', monospace;
    letter-spacing: .12em; color: var(--bronze); text-align: center; padding: 8px 0 2px;
  }
  .code-hinweis { text-align: center; color: #7a6a56; }
  .code-hinweis b { color: var(--tinte); }
  #code-rest { text-align: center; font-size: .85rem; color: #a09380; margin-top: 4px; }
  .zeile { display: flex; justify-content: space-between; gap: 12px;
           padding: 6px 0; border-bottom: 1px dashed var(--linie); }
  .zeile:last-child { border-bottom: 0; }
  .zeile .wert { text-align: right; }
  .punkt { display: inline-block; width: .65em; height: .65em; border-radius: 50%;
           margin-right: .4em; background: #c9b99f; vertical-align: baseline; }
  .punkt.gut { background: var(--gruen); } .punkt.schlecht { background: var(--rot); }
  ul#bausteine { list-style: none; display: grid; gap: 10px; }
  ul#bausteine li {
    border: 1px solid var(--linie); border-radius: 10px; padding: 12px 14px;
    display: grid; gap: 2px; background: #fffaf0;
  }
  ul#bausteine .titel { font-size: 1.05rem; }
  ul#bausteine .titel .theme {
    font: .75rem/1.6 ui-monospace, monospace; color: var(--karte);
    background: var(--bronze-hell); border-radius: 999px; padding: 1px 9px; margin-left: 8px;
    vertical-align: middle;
  }
  ul#bausteine .fuer { color: #7a6a56; font-style: italic; }
  ul#bausteine .meta { font-size: .8rem; color: #a09380; }
  #leer { color: #8a7a63; font-style: italic; }
  button {
    font: inherit; color: var(--karte); background: var(--bronze);
    border: 0; border-radius: 999px; padding: 10px 22px; cursor: pointer; width: 100%;
  }
  button:hover { background: var(--bronze-hell); }
  button:disabled { opacity: .6; cursor: wait; }
  #such-meldung { text-align: center; margin-top: 8px; font-size: .9rem; color: #7a6a56; min-height: 1.4em; }
  pre#logs {
    font: .74rem/1.5 ui-monospace, 'Courier New', monospace; color: #6b5c48;
    background: #fbf7ee; border: 1px solid var(--linie); border-radius: 8px;
    padding: 10px 12px; overflow-x: auto; max-height: 260px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word;
  }
  #fehler { color: var(--rot); font-size: .9rem; margin-top: 8px; }
  /* Kamera-Konfigurator */
  .kf-intro { color: #7a6a56; margin-bottom: 12px; }
  #kf-body { display: grid; gap: 16px; margin-top: 14px; }
  .kf-abschnitt { display: grid; gap: 8px; }
  .kf-titel { font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; color: var(--bronze-hell); }
  .kf-cam { display: grid; grid-template-columns: auto 1fr 1.2fr; gap: 8px; align-items: center;
            border: 1px solid var(--linie); border-radius: 8px; padding: 8px 10px; background: #fffaf0; }
  .kf-cam .eid { font: .78rem/1.4 ui-monospace, monospace; color: #8a7a63; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kf-cam input[type=text] { width: 100%; }
  .kf-abschnitt label { display: flex; align-items: center; gap: 8px; }
  .kf-abschnitt select, .kf-abschnitt input[type=text] {
    font: inherit; font-size: .92rem; padding: 7px 10px; border: 1px solid var(--linie);
    border-radius: 8px; background: var(--karte); color: var(--tinte); }
  #kf-tk-body { display: grid; gap: 10px; margin-top: 6px; padding-left: 24px; }
  #kf-tk-body label { display: grid; gap: 4px; align-items: start; }
  #kf-ergebnis { display: grid; gap: 10px; }
  pre#kf-yaml { font: .82rem/1.5 ui-monospace, 'Courier New', monospace; color: var(--tinte);
    background: #fbf7ee; border: 1px solid var(--linie); border-radius: 8px; padding: 12px 14px;
    overflow-x: auto; white-space: pre; }
  #kf-meldung { text-align: center; font-size: .9rem; color: var(--gruen); min-height: 1.3em; }
  footer { text-align: center; color: #b3a48d; font-size: .8rem; font-style: italic; }
</style>
</head>
<body>
<div class="rahmen">
  <header>
    <h1>JoAmy&nbsp;Installer</h1>
    <p>Einmal koppeln — deine Käufe ziehen ab dann von selbst bei dir ein.</p>
  </header>

  <section class="karte">
    <h2>Kopplungscode</h2>
    <div id="code">—</div>
    <p class="code-hinweis">Diesen Code beim Kauf auf <b>joamy.uk</b> eingeben
       (oder auf <b>joamy.uk/verbinden</b>), um dein Zuhause mit JoAmy zu verbinden.</p>
    <p id="code-rest"></p>
  </section>

  <section class="karte">
    <h2>Status</h2>
    <div class="zeile"><span>Lizenz-Server</span><span class="wert" id="st-server">—</span></div>
    <div class="zeile"><span>Registriert</span><span class="wert" id="st-reg">—</span></div>
    <div class="zeile"><span>Letzte Suche</span><span class="wert" id="st-poll">—</span></div>
    <div class="zeile"><span>Automatischer Neustart</span><span class="wert" id="st-neustart">—</span></div>
    <div id="fehler"></div>
  </section>

  <section class="karte">
    <h2>Installierte Bausteine</h2>
    <p id="leer">Noch nichts eingezogen — nach dem Koppeln erscheint dein erster Kauf hier von ganz allein.</p>
    <ul id="bausteine"></ul>
  </section>

  <section class="karte">
    <h2>Von Hand</h2>
    <button id="suchen">Jetzt nach Käufen suchen</button>
    <div id="such-meldung"></div>
  </section>

  <section class="karte" id="konfig-karte">
    <h2>Kamera-Karte einrichten</h2>
    <p class="kf-intro">Wähle deine Kameras — wir bauen dir den fertigen Code. Den fügst du beim
      Hinzufügen der Karte („Karte hinzufügen“ → ganz unten „Manuell“) einfach ein.</p>
    <button id="kf-laden" type="button">Meine Kameras laden</button>
    <div id="kf-body" hidden>
      <div class="kf-abschnitt">
        <span class="kf-titel">Kameras (anhaken + Namen vergeben)</span>
        <div id="kf-cams"></div>
      </div>
      <div class="kf-abschnitt">
        <label class="kf-titel" for="kf-stil">Style (kannst du später jederzeit über 🎨 wechseln)</label>
        <select id="kf-stil">
          <option value="skizze">Skizze</option><option value="comic">Comic</option>
          <option value="pinnwand">Pinnwand</option><option value="frost">Frost</option>
          <option value="terminal">Terminal</option><option value="riso">Riso</option>
          <option value="almanach">Almanach</option><option value="keramik">Keramik</option>
          <option value="pigment">Pigment</option>
        </select>
      </div>
      <div class="kf-abschnitt">
        <span class="kf-titel">Name vorne auf der Karte</span>
        <input id="kf-name" type="text" maxlength="40" placeholder="z. B. Familie Sommer">
      </div>
      <div class="kf-abschnitt">
        <label><input type="checkbox" id="kf-tk-an"> <b>Türklingel</b> — Meldung „Jemand klingelt gerade“</label>
        <div id="kf-tk-body" hidden>
          <label>Klingel-Sensor (schaltet beim Klingeln auf „an“)
            <select id="kf-tk-sensor"></select></label>
          <label>Kamera an der Tür
            <select id="kf-tk-cam"></select></label>
          <label>Tür-öffnen-Knopf (optional)
            <select id="kf-tk-knopf"><option value="">— keiner —</option></select></label>
        </div>
      </div>
      <div class="kf-abschnitt">
        <label><input type="checkbox" id="kf-ev-an" checked> „Letzte Ereignisse“ anzeigen (sofern die Kamera Aufzeichnungen liefert)</label>
      </div>
      <button id="kf-erzeugen" type="button">Code erzeugen</button>
      <div id="kf-ergebnis" hidden>
        <div class="kf-abschnitt">
          <span class="kf-titel">Fertiger Code — beim Hinzufügen der Karte einfügen</span>
          <pre id="kf-yaml"></pre>
        </div>
        <button id="kf-kopieren" type="button">Code kopieren</button>
        <div id="kf-meldung"></div>
      </div>
    </div>
  </section>

  <section class="karte">
    <h2>Logbuch</h2>
    <pre id="logs">—</pre>
  </section>

  <footer>JoAmy · gebacken mit Ruhe und Bronze</footer>
</div>

<script>
// Erststand kommt server-seitig mit — der Code steht damit schon im HTML.
var stand = __STATUS_JSON__;

function el(id) { return document.getElementById(id); }
function punkt(gut) {
  var s = document.createElement('span');
  s.className = 'punkt ' + (gut === true ? 'gut' : gut === false ? 'schlecht' : '');
  return s;
}
function wort(gut, ja, nein, offen) {
  return gut === true ? ja : gut === false ? nein : (offen || '…');
}

function male(st) {
  el('code').textContent = st.kopplungscode || '— — —';
  el('code-rest').textContent = st.kopplungscode
    ? 'Noch etwa ' + Math.max(1, Math.round(st.code_rest_s / 60)) + ' Minuten gültig — danach holt sich diese Seite automatisch einen frischen.'
    : 'Noch kein Code — der Lizenz-Server war noch nicht erreichbar.';

  var sv = el('st-server'); sv.textContent = '';
  sv.appendChild(punkt(st.server_ok));
  sv.appendChild(document.createTextNode(
    wort(st.server_ok, 'erreichbar', 'nicht erreichbar') + ' (' + st.server_url + ')'));

  var rg = el('st-reg'); rg.textContent = '';
  rg.appendChild(punkt(st.registriert));
  rg.appendChild(document.createTextNode(st.registriert ? 'ja' : 'noch nicht'));

  el('st-poll').textContent = st.letzter_poll || 'noch keine';
  el('st-neustart').textContent = (st.auto_neustart ? 'an' : 'aus')
    + (st.neustart_noetig ? ' · Neustart steht noch aus' : '');
  el('fehler').textContent = st.letzter_fehler ? 'Zuletzt gemeldet: ' + st.letzter_fehler : '';

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
    f.textContent = b.name ? 'Gebacken für ' + b.name : '';
    var m = document.createElement('div'); m.className = 'meta';
    m.textContent = 'Version ' + (b.version || '?')
      + (b.installiert_am ? ' · installiert ' + b.installiert_am.replace('T', ' ') : '');
    li.appendChild(t); if (b.name) li.appendChild(f); li.appendChild(m);
    ul.appendChild(li);
  });
  el('leer').style.display = (st.bausteine || []).length ? 'none' : '';

  el('logs').textContent = (st.logs || []).join('\\n') || '—';
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
  knopf.disabled = true; meldung.textContent = 'Suche läuft …';
  fetch('suchen', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function (erg) {
      meldung.textContent = erg.ok
        ? (erg.neu_installiert && erg.neu_installiert.length
            ? 'Gefunden und installiert: ' + erg.neu_installiert.join(', ') + '.'
            : 'Alles aktuell — kein neuer Kauf gefunden.')
        : ('Das hat nicht geklappt: ' + (erg.fehler || 'unbekannter Fehler'));
    })
    .catch(function () { meldung.textContent = 'Das hat nicht geklappt — Verbindung prüfen.'; })
    .finally(function () { knopf.disabled = false; lade(); });
});

// ---- Kamera-Karten-Konfigurator ----
(function () {
  var ent = { cameras: [], binary_sensors: [], buttons: [] };
  function fuelle(sel, arr, leer) {
    sel.innerHTML = '';
    if (leer) { var o = document.createElement('option'); o.value = ''; o.textContent = leer; sel.appendChild(o); }
    arr.forEach(function (e) { var o = document.createElement('option'); o.value = e.entity; o.textContent = e.name + ' (' + e.entity + ')'; sel.appendChild(o); });
  }
  function nameVon(entity) { var f = ent.cameras.filter(function (c) { return c.entity === entity; })[0]; return f ? f.name : entity.replace('camera.', ''); }
  function yamlEscape(s) {
    s = String(s == null ? '' : s);
    var c = s.charAt(0);
    var braucht = s === '' || s !== s.trim() || s.indexOf(':') >= 0 || s.indexOf('#') >= 0 ||
      c === '"' || c === "'" || c === '@' || c === '&' || c === '*' || c === '-' ||
      c === '[' || c === '{' || c === '!' || c === '|' || c === '>' || c === '%' || c === '?';
    if (!braucht) return s;
    return "'" + s.split("'").join("''") + "'";
  }
  if (el('kf-laden')) {
    el('kf-laden').addEventListener('click', function () {
      var b = el('kf-laden'); b.disabled = true; b.textContent = 'lädt …';
      fetch('entities', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
        ent = d || { cameras: [], binary_sensors: [], buttons: [] };
        var cams = el('kf-cams'); cams.innerHTML = '';
        if (!(ent.cameras || []).length) {
          cams.innerHTML = '<p style="color:#a04338">Keine camera.*-Entitäten gefunden' + (ent.fehler ? ': ' + ent.fehler : '') + '. (Kameras erst in Home Assistant einrichten.)</p>';
        }
        (ent.cameras || []).forEach(function (c) {
          var row = document.createElement('div'); row.className = 'kf-cam';
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true;
          var eid = document.createElement('span'); eid.className = 'eid'; eid.textContent = c.entity;
          var nm = document.createElement('input'); nm.type = 'text'; nm.value = c.name; nm.setAttribute('data-entity', c.entity); nm.placeholder = 'Name';
          cb.setAttribute('data-entity', c.entity);
          row.appendChild(cb); row.appendChild(eid); row.appendChild(nm); cams.appendChild(row);
        });
        fuelle(el('kf-tk-sensor'), ent.binary_sensors || [], '— wählen —');
        fuelle(el('kf-tk-cam'), ent.cameras || [], '— wählen —');
        fuelle(el('kf-tk-knopf'), ent.buttons || [], '— keiner —');
        el('kf-body').hidden = false;
      }).catch(function () {
        el('kf-cams').innerHTML = '<p style="color:#a04338">Konnte Home Assistant nicht erreichen.</p>'; el('kf-body').hidden = false;
      }).finally(function () { b.disabled = false; b.textContent = 'Kameras neu laden'; });
    });
    el('kf-tk-an').addEventListener('change', function () { el('kf-tk-body').hidden = !this.checked; });
    el('kf-erzeugen').addEventListener('click', function () {
      var cams = [];
      var rows = document.querySelectorAll('#kf-cams .kf-cam');
      for (var i = 0; i < rows.length; i++) {
        var cb = rows[i].querySelector('input[type=checkbox]'); if (!cb.checked) continue;
        var nm = rows[i].querySelector('input[type=text]');
        cams.push({ entity: cb.getAttribute('data-entity'), name: (nm.value.trim() || nameVon(cb.getAttribute('data-entity'))) });
      }
      el('kf-ergebnis').hidden = false; el('kf-meldung').textContent = '';
      if (!cams.length) { el('kf-yaml').textContent = '# Bitte mindestens eine Kamera anhaken.'; return; }
      var L = [];
      L.push('type: custom:joamy-kamera-card');
      L.push('stil: ' + el('kf-stil').value);
      var nm2 = el('kf-name').value.trim();
      if (nm2) L.push('title: ' + yamlEscape(nm2));
      L.push('cameras:');
      cams.forEach(function (c) { L.push('  - entity: ' + c.entity); L.push('    name: ' + yamlEscape(c.name)); });
      if (el('kf-tk-an').checked) {
        L.push('doorbell:'); L.push('  enabled: true');
        var rs = el('kf-tk-sensor').value; if (rs) L.push('  ringEntity: ' + rs);
        var rc = el('kf-tk-cam').value; if (rc) L.push('  camera: ' + rc);
        var rk = el('kf-tk-knopf').value; if (rk) L.push('  unlockButton: ' + rk);
      }
      L.push('events:'); L.push('  enabled: ' + (el('kf-ev-an').checked ? 'true' : 'false'));
      if (el('kf-ev-an').checked) L.push('  count: 20');
      el('kf-yaml').textContent = L.join('\\n');
    });
    el('kf-kopieren').addEventListener('click', function () {
      var t = el('kf-yaml').textContent;
      var fertig = function () { el('kf-meldung').style.color = 'var(--gruen)'; el('kf-meldung').textContent = 'Kopiert! Jetzt beim „Karte hinzufügen“ → „Manuell“ einfügen.'; };
      var fallback = function () { var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); fertig(); } catch (e) {} document.body.removeChild(ta); };
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t).then(fertig).catch(fallback); } else { fallback(); }
    });
  }
})();

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

    app = web.Application()
    app.router.add_get("/", seite)
    app.router.add_get("/status", status)
    app.router.add_post("/suchen", suchen)
    app.router.add_get("/logs", logs)
    app.router.add_get("/entities", entities)
    return app
