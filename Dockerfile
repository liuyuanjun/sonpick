# syntax=docker/dockerfile:1

# ---------- Stage 1: frontend build ----------
FROM node:22-alpine AS web-builder
WORKDIR /build
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim
WORKDIR /app

# 国内本地构建可传 --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg gcc libffi-dev libssl-dev libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

# 全部 Python 依赖（含精确钉版的 musicdl）统一由 requirements.txt 安装
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r /tmp/requirements.txt

COPY app/ ./app/
COPY --from=web-builder /build/dist ./web/dist

ENV PYTHONUNBUFFERED=1 \
    STORAGE_PATH=/app/downloads \
    DATABASE_PATH=/app/data/music.db \
    DATA_DIR=/app/data \
    TZ=Asia/Shanghai

EXPOSE 8000
VOLUME ["/app/data", "/app/downloads", "/app/logs"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
