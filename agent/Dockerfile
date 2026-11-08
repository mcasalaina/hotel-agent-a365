FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3978

WORKDIR /app

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/

COPY requirements.txt .
RUN pip install --disable-pip-version-check --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt

COPY . .

EXPOSE 3978

CMD ["python", "start_with_generic_host.py"]
