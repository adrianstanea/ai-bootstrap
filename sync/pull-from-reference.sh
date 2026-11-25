#!/usr/bin/env bash
# Reverse of sync-to-reference.sh: pull the config repo's paths from a checkout's working
# tree back into the config repo, e.g. after editing a hook directly in the synced target.
#
# Usage: pull-from-reference.sh [--config <config-repo>] <source-dir>
#   --config DIR   config repo holding ai-config.paths (default: $AI_CONFIG_DIR, else the
#                  git toplevel of the current directory)
#   source-dir     checkout to pull from (required)
#
# Copies listed paths from the source's working tree on top of the config repo. Never
# commits and never deletes files here; review with `git status` / `git diff` afterwards.
# Paths in the source's ".ai-config-skip" file are never pulled. Paths that are already
# symlinks are reported and skipped: they are the same file already.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

CONFIG_ARG=""
SRC_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_ARG="${2:?--config needs a directory}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option: $1" >&2; exit 2 ;;
    *) SRC_ARG="$1"; shift ;;
  esac
done
if [[ -z "$SRC_ARG" ]]; then
  echo "error: source directory required" >&2
  usage >&2
  exit 2
fi
DEST_ROOT="$(resolve_config_dir "$CONFIG_ARG")"
SRC_ROOT="$SRC_ARG"

if [[ ! -d "$SRC_ROOT" ]]; then
  echo "error: source directory not found: $SRC_ROOT" >&2
  exit 1
fi

load_paths "$DEST_ROOT"

SKIP_FILE="$SRC_ROOT/.ai-config-skip"
is_skipped() {
  local rel="$1"
  [[ -f "$SKIP_FILE" ]] || return 1
  grep -qxF "$rel" "$SKIP_FILE"
}

for rel in "${PATHS[@]}"; do
  if is_skipped "$rel"; then
    echo "skipped (listed in .ai-config-skip): $rel"
    continue
  fi
  src="$SRC_ROOT/$rel"
  dest="$DEST_ROOT/$rel"
  [[ -e "$src" ]] || continue

  if [[ -L "$src" ]]; then
    echo "already linked, nothing to pull: $rel"
    continue
  fi

  mkdir -p "$(dirname "$dest")"
  if [[ -d "$src" ]]; then
    mkdir -p "$dest"
    cp -r "$src/." "$dest/"
  else
    cp "$src" "$dest"
  fi
  echo "pulled: $rel"
done

echo
echo "Done. Review with: git -C \"$DEST_ROOT\" status / git -C \"$DEST_ROOT\" diff"
echo "Then commit yourself."
