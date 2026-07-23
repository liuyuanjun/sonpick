#!/usr/bin/env bash
# 一键部署到 NAS：同步 compose 文件 → 远端拉取镜像 → 重启 → 健康检查
# 前置：
#   1. GitHub Actions 已按 tag 构建并推送镜像（见 .github/workflows/release.yml）
#   2. NAS 上已能拉取对应 registry（私有 ACR 需先 docker login 一次）
#   3. NAS 上机器相关的定制放 docker-compose.override.yml（本脚本只更新 docker-compose.yml）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib.sh
source "$ROOT/scripts/lib.sh"
cd "$ROOT"

SSH_HOST="${SONPICK_SSH_HOST:-qnap}"
REMOTE_DIR="${SONPICK_REMOTE_DIR:-/home/admin/Docker/sonpick}"
HEALTH_PORT="${SONPICK_HEALTH_PORT:-8301}"
HEALTH_DELAY="${SONPICK_HEALTH_DELAY:-4}"
IMAGE_REPO="${SONPICK_IMAGE_REPO:-}"
VERSION=""

usage() {
  cat <<EOF
Usage: $0 [--version X.Y.Z | --latest] [--host HOST] [--remote DIR]

  --version X.Y.Z   部署指定版本镜像（默认读取 app/main.py 的 APP_VERSION）
  --latest          部署 latest 标签
  --host HOST       SSH Host（默认 qnap，可用 SONPICK_SSH_HOST 覆盖）
  --remote DIR      远端目录（可用 SONPICK_REMOTE_DIR 覆盖）

镜像仓库：默认要求 SONPICK_IMAGE_REPO（如 registry.cn-beijing.aliyuncs.com/<ns>/sonpick），
或设置 SONPICK_ACR_NAMESPACE 自动拼出阿里云仓库地址。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version) VERSION="$2"; shift 2 ;;
    --latest) VERSION="latest"; shift ;;
    --host) SSH_HOST="$2"; shift 2 ;;
    --remote) REMOTE_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  VERSION=$(grep -E 'APP_VERSION\s*=' app/main.py | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
fi
[[ -n "$VERSION" ]] || die "cannot resolve version; pass --version"

if [[ -z "$IMAGE_REPO" ]]; then
  if [[ -n "${SONPICK_ACR_NAMESPACE:-}" ]]; then
    IMAGE_REPO="registry.cn-beijing.aliyuncs.com/${SONPICK_ACR_NAMESPACE}/sonpick"
  else
    die "set SONPICK_IMAGE_REPO (e.g. registry.cn-beijing.aliyuncs.com/<namespace>/sonpick) or SONPICK_ACR_NAMESPACE"
  fi
fi
IMAGE="${IMAGE_REPO}:${VERSION}"

# --- SSH connection multiplexing ---
SSH_SOCK="/tmp/sonpick-${SSH_HOST}-$$"
SSH_OPTS=(-o BatchMode=yes -o ControlMaster=auto -o ControlPath="$SSH_SOCK" -o ControlPersist=300 -o ConnectTimeout=12)
RSYNC_SSH_CMD="ssh ${SSH_OPTS[*]}"

cleanup() {
  local rc=$?
  ssh "${SSH_OPTS[@]}" -O exit "$SSH_HOST" 2>/dev/null || true
  rm -f "$SSH_SOCK"
  exit "$rc"
}
trap cleanup EXIT INT TERM

log "connect → $SSH_HOST"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "echo connected"

log "ensure remote dirs"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "mkdir -p '$REMOTE_DIR/data' '$REMOTE_DIR/downloads' '$REMOTE_DIR/logs'"

log "sync docker-compose.yml → ${SSH_HOST}:${REMOTE_DIR}/"
rsync -az -e "$RSYNC_SSH_CMD" docker-compose.yml "${SSH_HOST}:${REMOTE_DIR}/docker-compose.yml"

log "ensure remote .env (never overwrite existing)"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && if [ ! -f .env ]; then printf 'SECRET_KEY=please-change-me\nADMIN_PASSWORD=please-change-me\n' > .env; echo '[sonpick] created default .env — 请尽快修改'; fi"

log "pin image in remote .env: $IMAGE"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && if grep -q '^SONPICK_IMAGE=' .env; then sed -i 's|^SONPICK_IMAGE=.*|SONPICK_IMAGE=$IMAGE|' .env; else printf '\nSONPICK_IMAGE=$IMAGE\n' >> .env; fi"

log "remote: docker compose pull && up -d"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && docker compose pull && docker compose up -d && docker compose ps"

log "wait ${HEALTH_DELAY}s then health check (http://127.0.0.1:${HEALTH_PORT}/health)"
sleep "$HEALTH_DELAY"
health_ok=0
for _ in $(seq 1 30); do
  if ssh "${SSH_OPTS[@]}" "$SSH_HOST" "curl -sfS http://127.0.0.1:${HEALTH_PORT}/health >/dev/null 2>&1"; then
    health_ok=1
    break
  fi
  sleep 1
done
if [[ "$health_ok" -eq 0 ]]; then
  log "health check FAILED — dumping logs:"
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && docker compose logs --tail=80"
  exit 1
fi

log "deployed $IMAGE — health check OK"
