#!/usr/bin/env bash
# Export a config repo's AI-assistant files into a target checkout's working tree.
#
# Usage: sync-to-reference.sh [--config <config-repo>] <target-dir>
#   --config DIR   config repo holding ai-config.paths (default: $AI_CONFIG_DIR, else the
#                  git toplevel of the current directory)
#   target-dir     checkout to link into (required)
#
# Symlinks (not copies) each path listed in <config>/ai-config.paths into the target's
# working tree, so editing either side edits the same file. Idempotent and additive-only:
# never deletes target files this script did not put there (beyond its own stale
# symlinks). Each linked path is also written to the target's .git/info/exclude (a managed
# block) so it stays untracked without relying on a global ignore.
#
# Links are relative, not absolute: the same working tree can be reachable from more than
# one environment at a different absolute path (e.g. a host checkout bind-mounted into a
# devcontainer), and an absolute link is dangling in the other one. A relative link resolves
# to the same bind-mounted file in both, as long as each environment keeps its own config
# clone at the same relative position to the target.
#
# A destination that differs from the config repo's content (an uncommitted local edit) is
# left as-is with a warning; run pull-from-reference.sh to bring that edit back first.
#
# Paths listed (one per line) in a ".ai-config-skip" file at the target root are never
# linked: use it for checkout-specific local config.
#
# Optional <config>/ai-config.migrate lists legacy paths whose symlinks into the config repo
# are removed (same format as ai-config.paths). Skills and agents are not linked here;
# old per-skill bridge links are always cleaned up.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

CONFIG_ARG=""
DEST_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_ARG="${2:?--config needs a directory}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option: $1" >&2; exit 2 ;;
    *) DEST_ARG="$1"; shift ;;
  esac
done
if [[ -z "$DEST_ARG" ]]; then
  echo "error: target directory required" >&2
  usage >&2
  exit 2
fi
SRC_ROOT="$(resolve_config_dir "$CONFIG_ARG")"
DEST_ROOT="$DEST_ARG"
# Canonical form for comparing where links resolve (SRC_ROOT itself may go through a symlink).
SRC_REAL="$(realpath "$SRC_ROOT")"

if [[ ! -d "$DEST_ROOT" ]]; then
  echo "error: target directory not found: $DEST_ROOT" >&2
  exit 1
fi

load_paths "$SRC_ROOT"

SKIP_FILE="$DEST_ROOT/.ai-config-skip"
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
  if [[ ! -e "$src" ]]; then
    # A path dropped from this repo leaves our earlier link dangling in the target; remove
    # only symlinks that resolve into this repo, never real files or foreign links.
    if [[ -L "$dest" ]]; then
      resolved="$(cd "$(dirname "$dest")" && realpath -m "$(readlink "$dest")")"
      if [[ "$resolved" == "$SRC_REAL"/* ]]; then
        rm -f "$dest"
        echo "removed dangling link (no longer in this repo): $rel"
        continue
      fi
    fi
    [[ "$rel" == *settings.local.json ]] && echo "skipped (no personal file in this repo): $rel"
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  rel_target="$(realpath --relative-to="$(dirname "$dest")" "$src")"

  if [[ -L "$dest" && "$(readlink "$dest")" == "$rel_target" ]]; then
    echo "already linked: $rel"
    continue
  fi

  # A symlink (even a broken one) is always this script's own prior artifact, never
  # user data -- safe to replace unconditionally, unlike a real file/dir. Needed because
  # the same path can be a dangling symlink in one environment (e.g. a stale absolute
  # target from before this script switched to relative links) while being perfectly
  # valid in another; bash's "-e" is false for a dangling symlink, so without this check
  # the code below would fall through to a plain `ln -s` and fail with "File exists"
  # against the stale link's own directory entry.
  if [[ -L "$dest" ]]; then
    rm -f "$dest"
    ln -s "$rel_target" "$dest"
    echo "linked (replaced stale symlink): $rel"
    continue
  fi

  if [[ -e "$dest" ]]; then
    if diff -rq "$src" "$dest" >/dev/null 2>&1; then
      rm -rf "$dest"
      ln -s "$rel_target" "$dest"
      echo "linked (converted from copy): $rel"
    else
      echo "warning: $rel differs from this repo's content -- NOT touched (looks like an" >&2
      echo "  uncommitted local edit). Run pull-from-reference.sh to bring it back" >&2
      echo "  here first, then re-run this script to finish linking it." >&2
    fi
    continue
  fi

  ln -s "$rel_target" "$dest"
  echo "linked: $rel"
done

# Remove links from older layouts: only symlinks that resolve into the config repo, never
# real files or directories, so separately installed skills survive. The legacy list comes
# from the optional <config>/ai-config.migrate; per-skill bridge links are always handled.
migrate_old_link() {
  local rel="$1" dest="$DEST_ROOT/$1" resolved legacy
  [[ -L "$dest" ]] || return 0
  resolved="$(cd "$(dirname "$dest")" && realpath -m "$(readlink "$dest")")"
  case "$resolved" in
    "$SRC_REAL"/.agents/skills|"$SRC_REAL"/.agents/skills/*|\
    "$SRC_REAL"/.claude/agents|"$SRC_REAL"/.claude/agents/*|\
    "$SRC_REAL"/.claude/skills|"$SRC_REAL"/.claude/skills/*)
      rm -f "$dest"
      echo "removed old link: $rel"
      return 0
      ;;
  esac
  for legacy in "${MIGRATE[@]}"; do
    if [[ "$resolved" == "$SRC_REAL/$legacy" || "$resolved" == "$SRC_REAL/$legacy"/* ]]; then
      rm -f "$dest"
      echo "removed old link: $rel"
      return 0
    fi
  done
}
MIGRATE=()
while IFS= read -r old; do MIGRATE+=("$old"); done < <(read_list "$SRC_ROOT/ai-config.migrate")
for old in ".agents/skills" ".claude/agents" ".claude/skills" ".github/skills" "${MIGRATE[@]}"; do
  migrate_old_link "$old"
done
if [[ -d "$DEST_ROOT/.claude/skills" && ! -L "$DEST_ROOT/.claude/skills" ]]; then
  for link in "$DEST_ROOT"/.claude/skills/*; do
    [[ -L "$link" ]] || continue
    # The old per-skill bridge pointed at the target's own .agents/skills link
    # (../../.agents/skills/<name>), so it never resolves into this repo once that link is gone.
    if [[ "$(readlink "$link")" == "../../.agents/skills/$(basename "$link")" ]]; then
      rm -f "$link"
      echo "removed old link: .claude/skills/$(basename "$link")"
    else
      migrate_old_link ".claude/skills/$(basename "$link")"
    fi
  done
fi
if [[ -d "$DEST_ROOT/.agents/skills" && ! -L "$DEST_ROOT/.agents/skills" ]]; then
  for link in "$DEST_ROOT"/.agents/skills/*; do
    [[ -L "$link" ]] && migrate_old_link ".agents/skills/$(basename "$link")"
  done
fi

# Paths installed outside this script (gh skills, optional Copilot skill links): never
# symlinks made here, but kept out of the target's git status via its local exclude file.
EXTRA_EXCLUDES=(".agents/skills")
if [[ -f "$SRC_ROOT/external-skills.json" ]] && command -v python3 >/dev/null 2>&1; then
  while IFS= read -r d; do
    [[ -n "$d" ]] && EXTRA_EXCLUDES+=(".claude/skills/$d")
  done < <(python3 -I -c 'import json,sys
for s in json.load(open(sys.argv[1]))["skills"]: print(s["dir"])' "$SRC_ROOT/external-skills.json")
fi

# Keep the linked paths untracked in the target without depending on a machine-wide global
# ignore: write them into the target's .git/info/exclude (in the common git dir, so every
# worktree of the target shares it). A managed block is rewritten on each run, so entries
# for paths that are no longer linked drop out and nothing outside the block is touched.
EXCLUDE_BEGIN="# BEGIN ai-config (managed by $(basename "$SRC_REAL")/sync-to-reference.sh)"
EXCLUDE_END="# END ai-config"
if COMMON_DIR="$(git -C "$DEST_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
  EXCLUDE_FILE="$COMMON_DIR/info/exclude"
  mkdir -p "$(dirname "$EXCLUDE_FILE")"
  touch "$EXCLUDE_FILE"

  block="$EXCLUDE_BEGIN"$'\n'
  for rel in "${PATHS[@]}" ".ai-config-source" ".ai-config-skip"; do
    if [[ "$rel" != ".ai-config-source" && "$rel" != ".ai-config-skip" ]]; then
      is_skipped "$rel" && continue
      [[ -L "$DEST_ROOT/$rel" ]] || continue
    fi
    block+="/$rel"$'\n'
  done
  for rel in "${EXTRA_EXCLUDES[@]}"; do
    block+="/$rel"$'\n'
  done
  block+="$EXCLUDE_END"

  tmp="$(mktemp)"
  # A BEGIN marker without a matching END must not swallow the rest of the file: buffer the
  # block, drop it only once END is seen, else keep its lines and drop just the stray marker.
  awk -v b="$EXCLUDE_BEGIN" -v e="$EXCLUDE_END" '
    $0 == b { if (n) for (i = 1; i <= n; i++) if (i > 1) print buf[i]; n = 1; buf[1] = $0; next }
    n && $0 == e { n = 0; next }
    n { buf[++n] = $0; next }
    { print }
    END { for (i = 2; i <= n; i++) print buf[i] }
  ' "$EXCLUDE_FILE" > "$tmp"
  printf '%s\n' "$block" >> "$tmp"
  cat "$tmp" > "$EXCLUDE_FILE"
  rm -f "$tmp"
  echo "synced: ignore entries in $EXCLUDE_FILE"
else
  echo "warning: $DEST_ROOT is not a git checkout -- skipped .git/info/exclude update" >&2
fi

# Machine/environment-specific pairing pointer, not a generic copied path: records this
# ai-config repo's own absolute location so the global worktree-sync hook
# (global/sync-worktree-ai-config.sh, installed via install-global-worktree-sync.sh) can find it from any linked worktree of the
# target repo without hardcoding a path to any specific ai-config repo.
#
# A list, one path per line, not a single overwritten value: the same working tree is
# often reachable from more than one environment with a different absolute-path view of
# it (e.g. a host checkout bind-mounted into a devcontainer at /workspaces/...). Appending
# (deduplicated) instead of overwriting means both environments' paths coexist here, and
# the hook that reads this file tries each line until one resolves on whichever
# environment is currently running -- rather than the two environments repeatedly
# clobbering each other's entry on every sync.
POINTER="$DEST_ROOT/.ai-config-source"
touch "$POINTER"
if ! grep -qxF "$SRC_ROOT" "$POINTER"; then
  echo "$SRC_ROOT" >> "$POINTER"
fi
echo "synced: .ai-config-source (added $SRC_ROOT if not already listed)"

echo "Done. Processed $(IFS=,; echo "${#PATHS[@]}") paths against $DEST_ROOT"
echo
echo "Note: share-untracked-worktree.sh (sharing genuinely git-untracked files"
echo "across worktrees) is a separate, deliberate step -- not run automatically here."
echo "Its eligibility scope is 'everything untracked', which can include real"
echo "in-progress work, not just files you intend to share; run it by hand and review"
echo "its proposed file list before confirming."
