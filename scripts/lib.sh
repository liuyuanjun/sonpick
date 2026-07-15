#!/usr/bin/env bash
# shared helpers for release scripts
set -euo pipefail

log() { printf '[%s] %s\n' "sonpick" "$*"; }
die() { printf '[%s] ERROR: %s\n' "sonpick" "$*" >&2; exit 1; }

has_cmd() {
  local p
  p=$(command -v "$1" 2>&1) || return 1
  [[ -n "$p" ]]
}

prefer_pnpm_build() {
  local web_dir="$1"
  (
    cd "$web_dir"
    if has_cmd pnpm; then
      log "frontend build: pnpm"
      if [[ ! -d node_modules ]]; then
        pnpm install
      else
        log "reuse web/node_modules"
      fi
      if [[ -x node_modules/.bin/vite ]] || [[ -f node_modules/vite/bin/vite.js ]]; then
        pnpm run build || node node_modules/vite/bin/vite.js build
      else
        pnpm install
        pnpm run build || node node_modules/vite/bin/vite.js build
      fi
    elif has_cmd yarn; then
      log "frontend build: yarn (fallback)"
      [[ -d node_modules ]] || yarn install
      yarn build
    elif [[ -f node_modules/vite/bin/vite.js ]] && has_cmd node; then
      log "frontend build: local vite.js"
      node node_modules/vite/bin/vite.js build
    elif has_cmd npm; then
      log "frontend build: npm (fallback)"
      [[ -d node_modules ]] || npm install
      npm run build
    else
      die "no pnpm/yarn/npm/node+vite available to build frontend"
    fi
  )
}
