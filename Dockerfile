FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY src/hotel-servicing-agent/requirements.txt /app/src/hotel-servicing-agent/requirements.txt
RUN python -m pip install --no-cache-dir \
    -r /app/src/hotel-servicing-agent/requirements.txt

COPY src/hotel-servicing-agent /app/src/hotel-servicing-agent
RUN python -m pip install --no-cache-dir --no-deps /app/src/hotel-servicing-agent

COPY agent-instructions.md run.sh startup.sh /app/

RUN addgroup --system agent \
    && adduser --system --ingroup agent --home /app agent \
    && chown -R agent:agent /app \
    && chmod +x /app/run.sh /app/startup.sh

USER agent

EXPOSE 8088

CMD ["/app/startup.sh"]
