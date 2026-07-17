ARG BUILD_FROM
FROM $BUILD_FROM

# Nur Python + websockets — die Daemons sind bewusst stdlib-nah gehalten.
# tzdata explizit: datetime.now() muss die Kunden-Zeitzone (TZ-Env vom
# Supervisor) treffen, sonst feuern Zeitpläne in UTC (1-2 h verschoben).
RUN apk add --no-cache python3 py3-pip tzdata \
 && pip3 install --no-cache-dir --break-system-packages websockets

COPY run.sh /
COPY app /app
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
