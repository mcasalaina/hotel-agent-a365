FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/
COPY requirements.txt .
RUN pip install --disable-pip-version-check --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt
COPY vault_bootstrap.py .
CMD ["python", "vault_bootstrap.py"]
