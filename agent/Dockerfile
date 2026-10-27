FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3978

WORKDIR /app

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/

COPY requirements.txt .
RUN mkdir -p /app/.build /app/.pip-cache \
    && export TMPDIR=/app/.build PIP_CACHE_DIR=/app/.pip-cache \
    && for attempt in 1 2 3 4 5; do \
        if pip install --disable-pip-version-check --index-url "$PIP_INDEX_URL" -r requirements.txt; then \
            rm -rf /app/.build /app/.pip-cache; \
            exit 0; \
        fi; \
        if [ "$attempt" -eq 5 ]; then exit 1; fi; \
        sleep "$((attempt * 30))"; \
    done

COPY . .

EXPOSE 3978

CMD ["python", "start_with_generic_host.py"]
