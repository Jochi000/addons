"""JoAmy Automatiken — Einstieg. Startet die gekauften/aktivierten Bausteine.

joamy-automatiken.json (vom JoAmy-Assistenten erzeugt):
{
  "steckdosen_scheduler": { "aktiv": true },
  "helligkeit": {
    "aktiv": true,
    "zonen": [ { "id": "flur", "name": "Flur",
                 "lights": ["light.flur"],
                 "presence": ["binary_sensor.flur_motion"],
                 "lux": "sensor.flur_lux" | null,
                 "lux_an_unter": 30, "aus_nach_s": 180 } ]
  }
}
"""
import asyncio
import logging

from ha import HaClient, lade_automatiken_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
LOG = logging.getLogger("joamy.main")


async def haupt():
    ha = HaClient()
    aufgaben = [asyncio.create_task(ha.verbinde_dauerhaft())]
    await ha.bereit.wait()

    # Konfig-Kette: Datei (ZIP-Einbau) → Dashboard-Config (Komfort-Übertragung
    # legt joamy_automatiken direkt im Dashboard „zuhause-joamy" ab).
    cfg = lade_automatiken_config()
    if not cfg:
        try:
            dash = await ha.frage("lovelace/config", url_path="zuhause-joamy")
            cfg = (dash or {}).get("joamy_automatiken") or {}
            if cfg:
                LOG.info("Konfiguration aus dem Dashboard geladen.")
        except Exception as e:
            LOG.warning("Dashboard-Konfig nicht lesbar: %s", e)

    if (cfg.get("steckdosen_scheduler") or {}).get("aktiv"):
        from steckdosen_scheduler import SteckdosenScheduler
        aufgaben.append(asyncio.create_task(
            SteckdosenScheduler(ha, cfg.get("steckdosen_scheduler") or {}).laufe()))
        LOG.info("Baustein aktiv: Steckdosen-Zeitpläne")

    if (cfg.get("helligkeit") or {}).get("aktiv"):
        from helligkeit import HelligkeitsRegler
        aufgaben.append(asyncio.create_task(
            HelligkeitsRegler(ha, cfg.get("helligkeit") or {}).laufe()))
        LOG.info("Baustein aktiv: Licht-Automatik (%d Zonen)",
                 len((cfg.get("helligkeit") or {}).get("zonen") or []))

    if len(aufgaben) == 1:
        LOG.warning("Kein Baustein aktiviert — Add-on läuft im Leerlauf.")

    await asyncio.gather(*aufgaben)


if __name__ == "__main__":
    asyncio.run(haupt())
