#!/usr/bin/env bash
# 版本发布辅助脚本：改版本号（app/main.py + setup_app.py + web/package.json）、
# 检查/补插 CHANGELOG 段落、git commit、打 tag、推送。
#
# 用法：
#   scripts/version.sh current                      # 查看当前版本与发布状态
#   scripts/version.sh set <版本号>                  # 只改文件 + 校验 CHANGELOG
#   scripts/version.sh set <版本号> -m "提交信息"    # 改文件并 commit + 打 tag
#   scripts/version.sh set <版本号> -m "..." --push  # 以上全部 + 推送分支和 tag
#
# 幂等可重入：已完成的步骤自动跳过，任何一步失败后重跑同一命令即可续跑。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MAIN_PY="app/main.py"
SETUP_PY="setup_app.py"
PKG_JSON="web/package.json"
CHANGELOG="CHANGELOG.md"

die() { echo "[version] ERROR: $*" >&2; exit 1; }
info() { echo "[version] $*"; }

read_main_version() { grep -m1 '^APP_VERSION = ' "$MAIN_PY" | cut -d'"' -f2; }
read_setup_version() { grep -m1 'version=' "$SETUP_PY" | cut -d'"' -f2; }
read_pkg_version() { grep -m1 '"version":' "$PKG_JSON" | cut -d'"' -f4; }

check_semver() {
  [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]] || die "版本号格式不合法: ${1}（应为 MAJOR.MINOR.PATCH 或 MAJOR.MINOR.PATCH-rcN）"
}

set_version_files() {
  local v="$1"
  V="$v" perl -pi -e 's/^APP_VERSION = "[^"]*"$/APP_VERSION = "$ENV{V}"/' "$MAIN_PY"
  V="$v" perl -pi -e 's/^(\s*)version="[^"]*",$/$1version="$ENV{V}",/' "$SETUP_PY"
  V="$v" perl -pi -e 's/"version": "[^"]*"/"version": "$ENV{V}"/' "$PKG_JSON"
}

verify_consistent() {
  local v="$1"
  local a b c
  a="$(read_main_version)"; b="$(read_setup_version)"; c="$(read_pkg_version)"
  [ "$a" = "$v" ] && [ "$b" = "$v" ] && [ "$c" = "$v" ] \
    || die "版本不一致: main.py=${a} setup_app.py=${b} package.json=${c}（期望 ${v}）"
  info "三处版本号一致: $v"
}

ensure_changelog() {
  local v="$1"
  if grep -qE "^## ${v}([[:space:]]|$)" "$CHANGELOG"; then
    info "CHANGELOG 已包含 ## ${v} 段落"
    return 0
  fi
  awk -v v="$v" '
    /^# Changelog/ && !done {
      print; print ""; print "## " v; print ""; print "### 变更"; print "- TODO: 补充本版要点"
      done=1; next
    }
    { print }
  ' "$CHANGELOG" > "$CHANGELOG.tmp"
  mv "$CHANGELOG.tmp" "$CHANGELOG"
  info "!! CHANGELOG 缺少 ## ${v} 段落，已自动插入模板，请补充本版要点后再提交"
  return 1
}

current_branch() { git symbolic-ref --short HEAD 2>/dev/null || echo main; }

cmd_current() {
  local a b c head_tag head_short
  a="$(read_main_version)"; b="$(read_setup_version)"; c="$(read_pkg_version)"
  head_short="$(git rev-parse --short HEAD)"
  echo "app/main.py:      $a"
  echo "setup_app.py:     $b"
  echo "web/package.json: $c"
  if [ "$a" = "$b" ] && [ "$b" = "$c" ]; then
    echo "一致性:           OK"
    grep -qE "^## ${a}([[:space:]]|$)" "$CHANGELOG" && echo "CHANGELOG:        已有 ## $a 段落" || echo "CHANGELOG:        缺少 ## $a 段落"
    if git rev-parse -q --verify "refs/tags/v${a}" >/dev/null; then
      local tag_target
      tag_target="$(git rev-list -n1 "v${a}")"
      [ "$tag_target" = "$(git rev-parse HEAD)" ] && echo "本地 tag:         v${a}（指向 HEAD）" || echo "本地 tag:         v${a}（未指向 HEAD: ${head_short}）"
    else
      echo "本地 tag:         v${a} 不存在"
    fi
  else
    echo "一致性:           不一致！运行 scripts/version.sh set <版本号> 修复"
  fi
  echo "HEAD:             $head_short $(git log -1 --pretty=%s)"
}

cmd_set() {
  local v="$1" msg="$2" push="$3"; shift 3
  local includes=("$@")
  check_semver "$v"

  # 1. 版本文件（幂等：值相同则 sed 不产生变化）
  set_version_files "$v"
  verify_consistent "$v"

  # 2. CHANGELOG（缺段落时插模板并给出提醒；不阻断流程）
  local changelog_inserted=0
  ensure_changelog "$v" || changelog_inserted=1

  # 3. commit（未提供 -m 则跳过；没有变化则自动跳过）
  if [ -n "$msg" ]; then
    local add_paths=("$MAIN_PY" "$SETUP_PY" "$PKG_JSON" "$CHANGELOG")
    [ -f AGENTS.md ] && add_paths+=(AGENTS.md)
    git add "${add_paths[@]}" ${includes[@]+"${includes[@]}"}
    if git diff --cached --quiet; then
      info "无待提交变化，跳过 commit"
    else
      git commit -m "$msg"
      info "已提交: $msg"
    fi
  else
    if ! git diff --quiet -- "$MAIN_PY" "$SETUP_PY" "$PKG_JSON"; then
      info "!! 版本文件有未提交改动（未提供 -m，跳过 commit/tag 步骤）"
    fi
  fi

  # 4. tag（已存在则跳过；存在但不在 HEAD 时提醒）
  #    仅在版本文件与 CHANGELOG 均已提交、且 CHANGELOG 非刚插入的模板时创建，
  #    避免 tag 指向不含本次版本改动的旧 HEAD 或未写完的 CHANGELOG。
  local tag="v$v" tag_ready=1
  if [ "$changelog_inserted" = "1" ]; then
    info "!! CHANGELOG 刚插入模板尚未补充，跳过打 tag（补充并提交后重跑同一命令续跑）"
    tag_ready=0
  elif ! git diff --quiet -- "$MAIN_PY" "$SETUP_PY" "$PKG_JSON" "$CHANGELOG" \
    || ! git diff --cached --quiet -- "$MAIN_PY" "$SETUP_PY" "$PKG_JSON" "$CHANGELOG"; then
    info "!! 版本文件/CHANGELOG 有未提交改动，跳过打 tag（提交后重跑同一命令续跑）"
    tag_ready=0
  fi
  if [ "$tag_ready" = "0" ]; then
    :
  elif git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    if [ "$(git rev-list -n1 "$tag")" != "$(git rev-parse HEAD)" ]; then
      info "!! tag $tag 已存在但不指向 HEAD（$(git rev-parse --short HEAD)），如需移动请先删除: git tag -d $tag"
    else
      info "tag $tag 已存在，跳过"
    fi
  else
    git tag "$tag"
    info "已创建 tag $tag"
  fi
  if [ -n "$(git status --porcelain)" ]; then
    info "!! 工作区仍有未提交/未跟踪文件，tag 指向的提交可能不包含它们："
    git status --short | sed 's/^/[version]   /'
  fi

  # 5. push（幂等：远端已有 tag 则跳过 tag 推送；tag 缺失或不指向 HEAD 时不推）
  if [ "$push" = "1" ]; then
    local branch
    branch="$(current_branch)"
    git push origin "$branch"
    info "已推送分支 $branch"
    if ! git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
      info "!! 本地 tag $tag 不存在，跳过 tag 推送（解决上述提醒后重跑同一命令）"
    elif [ "$(git rev-list -n1 "$tag")" != "$(git rev-parse HEAD)" ]; then
      info "!! tag $tag 不指向 HEAD，跳过 tag 推送；确需移动请先 git tag -d $tag 再重跑"
    elif git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
      info "远端已有 ${tag}，跳过 tag 推送"
    else
      git push origin "$tag"
      info "已推送 tag $tag"
    fi
    info "完成。请确认 release workflow: gh run list --limit 3"
  else
    info "未加 --push，未推送。推送请重跑: scripts/version.sh set $v --push"
  fi
}

cmd="${1:-}"
case "$cmd" in
  current)
    cmd_current
    ;;
  set)
    [ $# -ge 2 ] || die "用法: scripts/version.sh set <版本号> [-m 提交信息] [--push] [--include <路径>...]"
    version="$2"; shift 2
    msg=""; push="0"; includes=()
    while [ $# -gt 0 ]; do
      case "$1" in
        -m|--message) msg="${2:?-m 需要提交信息}"; shift 2 ;;
        --push) push="1"; shift ;;
        --include) includes+=("${2:?--include 需要路径}"); shift 2 ;;
        *) die "未知参数: $1" ;;
      esac
    done
    # 提交信息里没带版本号时自动补上，保持仓库习惯
    if [ -n "$msg" ] && [[ "$msg" != *"($version)"* ]]; then
      msg="$msg ($version)"
    fi
    cmd_set "$version" "$msg" "$push" ${includes[@]+"${includes[@]}"}
    ;;
  *)
    echo "用法:"
    echo "  scripts/version.sh current"
    echo "  scripts/version.sh set <版本号> [-m 提交信息] [--push] [--include <路径>...]"
    exit 1
    ;;
esac
