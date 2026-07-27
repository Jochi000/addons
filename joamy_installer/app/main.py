"""JoAmy Installer — Einstieg.

Startet drei Dinge:
  1. Registrierung beim Lizenz-Server (Kopplungscode → Log + Ingress-Seite),
  2. die Ingress-Oberfläche auf 0.0.0.0:8321 (= ingress_port in config.yaml),
  3. den Poll-Loop, der neue Käufe erkennt und installiert.

Für den Mock-Test auf dem Entwicklungsrechner sind alle Pfade/Basis-URLs über
ENV stellbar (DATA_DIR, CONFIG_DIR, SUPERVISOR_URL, INGRESS_PORT) — Defaults
sind die echten Add-on-Pfade /data, /config, http://supervisor, 8321.
"""
import asyncio
import logging
import os

from aiohttp import web

from kern import Installer, PufferHandler, lade_optionen
from oberflaeche import baue_web_app

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
_puffer = PufferHandler()
_puffer.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(_puffer)
# Zugriffs-Logs der Ingress-Seite würden das Logbuch fluten (Status-Poll alle 5 s).
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

LOG = logging.getLogger("joamy.main")

PORT = int(os.environ.get("INGRESS_PORT", "8321"))


async def haupt() -> None:
    optionen = lade_optionen()
    LOG.info("JoAmy Installer startet (Server %s, Poll alle %d s). "
             "Home Assistant wird von diesem Add-on NIE neu gestartet.",
             optionen["server_url"], optionen["poll_sekunden"])

    installer = Installer(optionen)
    await installer.start()

    # Zeitschaltuhr-Engine: läuft ALS TASK IM INSTALLER (kein zweites Add-on).
    # Sie wartet selbst darauf, dass der Baustein installiert ist — startet der
    # Kunde ohne Kauf, schläft sie leise und kostet nichts.
    async def zeitschaltuhr_wache() -> None:
        from zeitschaltuhr import ZeitschaltuhrEngine
        from kern import SUPERVISOR_URL, SUPERVISOR_TOKEN
        while True:
            if "zeitschaltuhr" in (installer.status.get("installiert") or {}):
                engine = ZeitschaltuhrEngine(installer.session, SUPERVISOR_URL,
                                             os.environ.get("SUPERVISOR_TOKEN", SUPERVISOR_TOKEN))
                try:
                    await engine.laufe()
                except Exception:
                    LOG.exception("Zeitschaltuhr-Engine gestorben — Neustart in 30 s")
            await asyncio.sleep(30)

    asyncio.get_running_loop().create_task(zeitschaltuhr_wache())

    runner = web.AppRunner(baue_web_app(installer))
    await runner.setup()
    # 0.0.0.0 ist Pflicht: der Ingress-Proxy verbindet sich aus dem
    # Supervisor-Container über das interne hassio-Netz, nicht über 127.0.0.1.
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    LOG.info("Ingress-Oberfläche lauscht auf 0.0.0.0:%d.", PORT)

    await installer.poll_schleife()


if __name__ == "__main__":
    try:
        asyncio.run(haupt())
    except KeyboardInterrupt:
        pass
