# Sonpick runtime image — NO Node.
# Build frontend on the dev machine (pnpm), then copy web/dist.

FROM python:3.12-slim
WORKDIR /app

ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    PIP_DISABLE_PIP_VERSION_CHECK=1


# Debian apt -> 阿里云（兼容 deb822 debian.sources 与 sources.list）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg gcc libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY musicdl/requirements.txt /tmp/musicdl-requirements.txt
RUN pip install --no-cache-dir -r /tmp/musicdl-requirements.txt

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY musicdl/ ./musicdl/
RUN pip install --no-cache-dir -e ./musicdl

COPY app/ ./app/
COPY web/dist ./web/dist

ENV PYTHONUNBUFFERED=1 \
    STORAGE_PATH=/app/downloads \
    DATABASE_PATH=/app/data/music.db \
    DATA_DIR=/app/data \
    TZ=Asia/Shanghai

EXPOSE 8000
VOLUME ["/app/data", "/app/downloads", "/app/logs"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
