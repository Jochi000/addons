ARG BUILD_FROM
FROM $BUILD_FROM

# Python + aiohttp — die App ist bewusst schlank: ein HTTP-Client (Lizenz-Server
# + Core-API) und ein kleiner Webserver für die Ingress-Seite, sonst stdlib.
# tzdata explizit: Zeitstempel (Backups, Logs) sollen die Kunden-Zeitzone
# treffen (TZ-Env vom Supervisor), nicht UTC.
RUN apk add --no-cache python3 py3-pip tzdata \
 && pip3 install --no-cache-dir --break-system-packages aiohttp

COPY run.sh /
COPY app /app
# JoAmy-Grundbaustein (Hub-Integration): wird beim ersten Start nach
# /config/custom_components/joamy kopiert. EIN Neustart beim Einrichten —
# danach braucht kein Kauf je wieder einen (Hub lädt Karten per Reload).
COPY hub /hub
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
