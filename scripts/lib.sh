#!/usr/bin/env bash
# shared helpers for release scripts
set -euo pipefail

log() { printf '[%s] %s\n' "sonpick" "$*"; }
die() { printf '[%s] ERROR: %s\n' "sonpick" "$*" >&2; exit 1; }
