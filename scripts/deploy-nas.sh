#!/usr/bin/env bash
# 打包 + rsync 到 NAS + docker compose up
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib.sh
source "$ROOT/scripts/lib.sh"
cd "$ROOT"

SSH_HOST="${SONPICK_SSH_HOST:-qnap}"
REMOTE_DIR="${SONPICK_REMOTE_DIR:-/home/admin/Docker/sonpick}"
HEALTH_PORT="${SONPICK_HEALTH_PORT:-8301}"
HEALTH_DELAY="${SONPICK_HEALTH_DELAY:-4}"
PACK_ONLY=0
RSYNC_ONLY=0
NO_BUILD=0
FORCE_BUILD=0
SKIP_FRONTEND=0
CLEAN_DEPLOY=0

usage() {
  cat <<EOF
Usage: $0 [options]

  -b, --force-build   强制 pnpm build 前端
  -p, --pack-only     只生成 deploy/，不 rsync
  -r, --rsync-only    跳过打包构建，直接同步已有 deploy/
  -n, --no-build      远端只 up/restart，不 docker compose build
  -s, --skip-frontend 打包时不构建前端（要求 web/dist 已存在）
  -c, --clean-deploy  成功部署后删除本地 deploy/
  --host HOST         SSH Host（默认 qnap）
  --remote DIR        远端目录（默认 /home/admin/Docker/sonpick）
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -b|--force-build) FORCE_BUILD=1; shift ;;
    -p|--pack-only) PACK_ONLY=1; shift ;;
    -r|--rsync-only) RSYNC_ONLY=1; shift ;;
    -n|--no-build) NO_BUILD=1; shift ;;
    -s|--skip-frontend) SKIP_FRONTEND=1; shift ;;
    -c|--clean-deploy) CLEAN_DEPLOY=1; shift ;;
    --host) SSH_HOST="$2"; shift 2 ;;
    --remote) REMOTE_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

if [[ "$RSYNC_ONLY" -eq 0 ]]; then
  prep_args=()
  [[ "$FORCE_BUILD" -eq 1 ]] && prep_args+=(--force-build)
  [[ "$SKIP_FRONTEND" -eq 1 ]] && prep_args+=(--skip-build)
  if [[ ${#prep_args[@]} -gt 0 ]]; then
    "$ROOT/scripts/prepare-deploy.sh" "${prep_args[@]}"
  else
    "$ROOT/scripts/prepare-deploy.sh"
  fi
else
  [[ -f deploy/web/dist/index.html ]] || die "deploy/web/dist missing; run without --rsync-only first"
  [[ -f deploy/Dockerfile ]] || die "deploy/Dockerfile missing"
  [[ -f deploy/docker-compose.yml ]] || die "deploy/docker-compose.yml missing"
fi

[[ "$PACK_ONLY" -eq 1 ]] && { log "pack done in deploy/"; exit 0; }

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

log "rsync → ${SSH_HOST}:${REMOTE_DIR}/"
rsync -az --delete --human-readable \
  -e "$RSYNC_SSH_CMD" \
  --exclude 'data/' \
  --exclude 'downloads/' \
  --exclude 'logs/' \
  --exclude '.env' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  deploy/ "${SSH_HOST}:${REMOTE_DIR}/"

log "ensure remote .env (never overwrite existing)"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && if [ ! -f .env ]; then if [ -f .env.example ]; then cp .env.example .env; echo '[sonpick] created .env from example'; else printf 'SECRET_KEY=change-me\nADMIN_PASSWORD=admin\n' > .env; echo '[sonpick] created default .env'; fi; fi"

if [[ "$NO_BUILD" -eq 1 ]]; then
  log "remote: docker compose up -d (no rebuild)"
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && docker compose up -d && docker compose ps"
else
  log "remote: docker compose up -d --build"
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && docker compose up -d --build && docker compose ps"
fi

# 容器启动后先等几秒，再轮询健康检查（默认延迟 4s，最多再等 30s）
log "wait ${HEALTH_DELAY}s then health check (http://127.0.0.1:${HEALTH_PORT}/health)"
sleep "$HEALTH_DELAY"
health_ok=0
for i in $(seq 1 30); do
  if ssh "${SSH_OPTS[@]}" "$SSH_HOST" "curl -sfS http://127.0.0.1:${HEALTH_PORT}/health >/dev/null 2>&1"; then
    health_ok=1
    break
  fi
  sleep 1
done
if [[ "$health_ok" -eq 0 ]]; then
  log "health check FAILED after ${HEALTH_DELAY}+30s — dumping logs:"
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd '$REMOTE_DIR' && docker compose logs --tail=80"
  exit 1
fi
log "health check OK"

if [[ "$CLEAN_DEPLOY" -eq 1 ]]; then
  log "remove local deploy/"
  rm -rf deploy/
fi

log "done"
