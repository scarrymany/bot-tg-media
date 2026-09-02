FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY bot ./bot

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV DOWNLOAD_DIR=/data/downloads \
    DB_PATH=/data/bot.db \
    HEARTBEAT_PATH=/tmp/bot-heartbeat \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]

CMD ["python", "-m", "bot"]
