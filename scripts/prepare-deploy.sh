#!/usr/bin/env bash
# 本地打包运行包到 deploy/（不 rsync）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib.sh
source "$ROOT/scripts/lib.sh"
cd "$ROOT"

FORCE_BUILD=0
SKIP_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --force-build) FORCE_BUILD=1 ;;
    --skip-build) SKIP_BUILD=1 ;;
    -h|--help)
      echo "Usage: $0 [--force-build|--skip-build]"
      exit 0
      ;;
  esac
done

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  if [[ "$FORCE_BUILD" -eq 1 || ! -f web/dist/index.html ]]; then
    prefer_pnpm_build "$ROOT/web"
  else
    log "reuse existing web/dist (pass --force-build to rebuild)"
  fi
fi

[[ -f web/dist/index.html ]] || die "web/dist/index.html missing; build frontend first"

log "sync code into deploy/"
mkdir -p deploy/web/dist deploy/data deploy/downloads deploy/logs
rsync -a --delete --exclude '__pycache__/' --exclude '*.pyc' app/ deploy/app/
rsync -a --delete web/dist/ deploy/web/dist/
rsync -a --delete \
  --exclude '__pycache__/' --exclude '*.pyc' --exclude '.git/' \
  --exclude 'docs/' --exclude '*.egg-info/' \
  musicdl/ deploy/musicdl/
cp -f requirements.txt deploy/requirements.txt
cp -f Dockerfile deploy/Dockerfile

[[ -f docker-compose.prod.yml ]] || die "docker-compose.prod.yml missing"
cp -f docker-compose.prod.yml deploy/docker-compose.yml

cat > deploy/.env.example <<'ENV'
SECRET_KEY=please-change-me-to-a-long-random-string
ADMIN_PASSWORD=please-change-me
ENV

touch deploy/data/.gitkeep deploy/downloads/.gitkeep deploy/logs/.gitkeep

if grep -q 'APP_VERSION' app/main.py; then
  ver=$(grep -E 'APP_VERSION\s*=' app/main.py | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
  echo "$ver" > deploy/VERSION
  log "packed version $ver"
fi

log "deploy/ ready"
