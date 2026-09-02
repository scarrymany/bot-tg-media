FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user; /data is chowned below, before VOLUME.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app

COPY pyproject.toml README.md ./
COPY bot ./bot

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV DOWNLOAD_DIR=/data/downloads \
    DB_PATH=/data/bot.db \
    HEARTBEAT_PATH=/tmp/bot-heartbeat \
    PYTHONUNBUFFERED=1

# Ownership has to be set before VOLUME: Docker seeds a fresh named volume
# from the image directory, ownership included. An existing bot-data volume
# created by an older root image keeps its root ownership - see README.
RUN mkdir -p /data/downloads && chown -R app:app /data

VOLUME ["/data"]

USER app

CMD ["python", "-m", "bot"]
