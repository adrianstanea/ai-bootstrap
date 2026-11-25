#!/usr/bin/env bash
# Bootstrap a project checkout with a config repo's AI-assistant tooling.
#
# Steps (idempotent, safe to re-run):
#   1. sync-to-reference.sh: symlink the config repo's ai-config.paths into the target.
#   2. External skills (<config>/external-skills.json, optional) via `gh skill install` into
#      the target's .claude/skills, re-installed fresh on every run.
#   3. Claude Code plugins from <config>/.claude-plugin/marketplace.json (optional; the
#      marketplace name is read from it; directory marketplace, so edits are live).
#   4. Copilot CLI plugins from the same marketplace (user-level).
#   5. Shared Git hooks and the machine-level worktree sync hook (see --skip-hooks).
#
# Usage: bootstrap.sh --config <config-repo> --target <checkout> [--skip-external]
#                     [--no-copilot] [--copilot-link] [--skip-hooks] [--dry-run] [-h|--help]
#   --config DIR      config repo (default: $AI_CONFIG_DIR)
#   --target DIR      checkout to configure (required)
#   --skip-external   do not install external skills (prints an explicit SKIPPED line)
#   --no-copilot      skip the Copilot CLI plugin step
#   --copilot-link    also symlink plugin skills into <target>/.agents/skills (Copilot setups
#                     without plugin support)
#   --skip-hooks      skip step 5 (it edits the target's git config and ~/.claude)
#   --dry-run         print what would run, change nothing
# Env overrides: GH_BIN, CLAUDE_BIN, COPILOT_BIN, AI_CONFIG_DIR.
# Exit codes: 0 ok, 1 error or a failed install, 2 gh missing/too old (>= 2.90 needed).
#
# Claude plugins are installed at user scope, and skipped when the target's
# .claude/settings.json already lists them in enabledPlugins: that file may be shared from
# the config repo, so a project-scope install would write into its tracked settings.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SELF_DIR/lib.sh"
MARKETPLACE=""
MIN_GH="2.90.0"

TARGET=""
CONFIG_ARG=""
SKIP_EXTERNAL=0
NO_COPILOT=0
COPILOT_LINK=0
SKIP_HOOKS=0
DRY=0

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config) CONFIG_ARG="${2:?--config needs a directory}"; shift 2 ;;
        --target) TARGET="${2:?--target needs a directory}"; shift 2 ;;
        --skip-external) SKIP_EXTERNAL=1; shift ;;
        --no-copilot) NO_COPILOT=1; shift ;;
        --copilot-link) COPILOT_LINK=1; shift ;;
        --skip-hooks) SKIP_HOOKS=1; shift ;;
        --dry-run) DRY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "error: unknown option: $1" >&2; exit 1 ;;
        *) echo "error: unexpected argument: $1 (use --target)" >&2; exit 1 ;;
    esac
done

SUMMARY=()
FAILED=0
note() { SUMMARY+=("$(printf '%-34s %s' "$1" "$2")"); }

# Run a command, or only print it under --dry-run.
run() {
    if [[ $DRY -eq 1 ]]; then
        printf '[dry-run]'; printf ' %q' "$@"; printf '\n'
    else
        "$@"
    fi
}

AI_CONFIG_DIR="$(resolve_config_dir "$CONFIG_ARG")" || exit 1
if [[ -z "$TARGET" ]]; then
    echo "error: --target <checkout> is required" >&2
    exit 1
fi
if [[ ! -e "$TARGET/.git" ]]; then
    echo "error: $TARGET is not a git checkout (no .git)" >&2
    exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"
MANIFEST="$AI_CONFIG_DIR/external-skills.json"
CATALOG="$AI_CONFIG_DIR/.claude-plugin/marketplace.json"
if [[ -f "$CATALOG" ]]; then
    MARKETPLACE="$(python3 -I -c 'import json,sys
print(json.load(open(sys.argv[1]))["name"])' "$CATALOG")"
fi

# --- gh preflight (before anything is changed) --------------------------------------------
GH="${GH_BIN:-gh}"
if [[ $SKIP_EXTERNAL -eq 0 ]]; then
    gh_ver=""
    if command -v "$GH" >/dev/null 2>&1; then
        gh_ver="$("$GH" --version 2>/dev/null | sed -n '1s/^gh version \([0-9.]*\).*/\1/p')"
    fi
    if [[ -z "$gh_ver" || "$(printf '%s\n%s\n' "$MIN_GH" "$gh_ver" | sort -V | head -1)" != "$MIN_GH" ]]; then
        echo "error: gh >= $MIN_GH is required for 'gh skill install' (found: ${gh_ver:-none})." >&2
        echo "  Upgrade: https://github.com/cli/cli#installation (e.g. 'brew upgrade gh' or" >&2
        echo "  'sudo apt update && sudo apt install --only-upgrade gh'), or pass --skip-external." >&2
        exit 2
    fi
fi

# --- 1. Sync config files -----------------------------------------------------------------
echo "== 1/5 sync config into $TARGET"
if [[ $DRY -eq 1 ]]; then
    echo "[dry-run] $SELF_DIR/sync-to-reference.sh --config $AI_CONFIG_DIR $TARGET (not run)"
    note "config symlinks" "dry-run"
else
    "$SELF_DIR/sync-to-reference.sh" --config "$AI_CONFIG_DIR" "$TARGET"
    note "config symlinks" "synced"
fi

# --- 2. External skills -------------------------------------------------------------------
echo "== 2/5 external skills"
if [[ $SKIP_EXTERNAL -eq 1 ]]; then
    echo "SKIPPED external skills (--skip-external)"
    note "external skills" "SKIPPED"
elif [[ ! -f "$MANIFEST" ]]; then
    echo "SKIPPED external skills: no $MANIFEST"
    note "external skills" "SKIPPED (no manifest)"
else
    while IFS=$'\t' read -r repo skill pin dir; do
        [[ "$pin" == "-" ]] && pin=""
        cmd=("$GH" skill install "$repo" "$skill" --agent claude-code --scope project --force)
        [[ -n "$pin" ]] && cmd+=(--pin "$pin")
        echo "-> $repo $skill${pin:+ (pinned $pin)}"
        if [[ $DRY -eq 1 ]]; then
            printf '[dry-run] (cd %q &&' "$TARGET"; printf ' %q' "${cmd[@]}"; printf ')\n'
            note "skill $dir" "dry-run"
        elif (cd "$TARGET" && "${cmd[@]}" </dev/null) >/dev/null 2>&1; then
            note "skill $dir" "installed${pin:+ @$pin}"
        else
            echo "error: failed to install $repo $skill" >&2
            note "skill $dir" "FAILED"
            FAILED=1
        fi
    done < <(python3 -I -c 'import json,sys
for s in json.load(open(sys.argv[1]))["skills"]:
    print("\t".join([s["repo"], s["skill"], s.get("pin") or "-", s["dir"]]))' "$MANIFEST")
fi

# --- plugin list from the catalog ---------------------------------------------------------
PLUGINS=()
if [[ -f "$CATALOG" ]]; then
    while IFS= read -r p; do PLUGINS+=("$p"); done < <(python3 -I -c 'import json,sys
for p in json.load(open(sys.argv[1]))["plugins"]: print(p["name"])' "$CATALOG")
fi

# Add (or refresh) the directory marketplace and install every plugin with a harness CLI.
# Args: label, binary, extra install args... ; reads $ENABLED_IN_PROJECT for Claude.
plugin_step() {
    local label="$1" bin="$2" scope_args="$3" skip_enabled="$4" p id action=""
    if [[ ${#PLUGINS[@]} -eq 0 || -z "$MARKETPLACE" ]]; then
        echo "SKIPPED $label plugins: no plugins in $CATALOG"
        note "$label plugins" "SKIPPED (no catalog)"
        return
    fi
    local listing
    listing="$("$bin" plugin marketplace list 2>/dev/null || true)"
    if grep -q "$MARKETPLACE" <<<"$listing" \
        && grep -A3 "$MARKETPLACE" <<<"$listing" | grep -qF "$AI_CONFIG_DIR"; then
        run "$bin" plugin marketplace update "$MARKETPLACE" >/dev/null 2>&1 || true
        action="refreshed"
    elif grep -q "$MARKETPLACE" <<<"$listing"; then
        # Registered from another source (e.g. a GitHub copy); edits here must be served live.
        action="re-registered from this checkout"
        run "$bin" plugin marketplace remove "$MARKETPLACE" >/dev/null 2>&1 || true
        if ! run "$bin" plugin marketplace add "$AI_CONFIG_DIR"; then
            echo "error: $label marketplace add failed" >&2
            note "$label marketplace" "FAILED"; FAILED=1; return
        fi
    else
        action="added"
        if ! run "$bin" plugin marketplace add "$AI_CONFIG_DIR"; then
            echo "error: $label marketplace add failed" >&2
            note "$label marketplace" "FAILED"; FAILED=1; return
        fi
    fi
    note "$label marketplace" "$MARKETPLACE $([[ $DRY -eq 1 ]] && echo dry-run || echo "$action")"
    for p in "${PLUGINS[@]}"; do
        id="$p@$MARKETPLACE"
        if [[ $skip_enabled -eq 1 ]] && grep -q "\"$id\"[[:space:]]*:[[:space:]]*true" \
            "$TARGET/.claude/settings.json" 2>/dev/null; then
            note "$label plugin $p" "enabled in project settings"
        elif [[ $DRY -eq 0 ]] && "$bin" plugin list 2>/dev/null | grep "$id" | grep -qv "disabled"; then
            note "$label plugin $p" "already installed"
        elif run "$bin" plugin install "$id" $scope_args; then
            note "$label plugin $p" "$([[ $DRY -eq 1 ]] && echo dry-run || echo installed)"
        else
            echo "error: $label install of $id failed" >&2
            note "$label plugin $p" "FAILED"; FAILED=1
        fi
    done
}

# --- 3. Claude Code -----------------------------------------------------------------------
echo "== 3/5 Claude Code plugins"
CLAUDE="${CLAUDE_BIN:-${CLAUDE_CODE_EXECPATH:-claude}}"
if command -v "$CLAUDE" >/dev/null 2>&1; then
    plugin_step "claude" "$CLAUDE" "--scope user" 1
else
    echo "SKIPPED Claude plugins: claude CLI not found (set CLAUDE_BIN)"
    note "claude plugins" "SKIPPED (no claude CLI)"
fi

# --- 4. Copilot CLI -----------------------------------------------------------------------
echo "== 4/5 Copilot CLI plugins"
COPILOT="${COPILOT_BIN:-copilot}"
if [[ $NO_COPILOT -eq 1 ]]; then
    echo "SKIPPED Copilot plugins (--no-copilot)"
    note "copilot plugins" "SKIPPED (--no-copilot)"
elif command -v "$COPILOT" >/dev/null 2>&1; then
    plugin_step "copilot" "$COPILOT" "" 0
else
    echo "SKIPPED Copilot plugins: copilot CLI not found (set COPILOT_BIN)"
    note "copilot plugins" "SKIPPED (no copilot CLI)"
fi

if [[ $COPILOT_LINK -eq 1 ]]; then
    echo "-> linking plugin skills into $TARGET/.agents/skills"
    n=0
    for skill_dir in "$AI_CONFIG_DIR"/plugins/*/skills/*/; do
        [[ -f "$skill_dir/SKILL.md" ]] || continue
        name="$(basename "$skill_dir")"
        dest="$TARGET/.agents/skills/$name"
        if [[ -e "$dest" && ! -L "$dest" ]]; then
            echo "warning: $dest exists and is not a symlink -- NOT touched" >&2
            continue
        fi
        run mkdir -p "$TARGET/.agents/skills"
        run ln -sfn "$(realpath --relative-to="$TARGET/.agents/skills" "${skill_dir%/}")" "$dest"
        n=$((n + 1))
    done
    note "copilot skill links" "$n linked (.agents/skills)"
fi

# --- 5. Git hooks and machine-level sync --------------------------------------------------
echo "== 5/5 git hooks and global worktree sync"
if [[ $SKIP_HOOKS -eq 1 || $DRY -eq 1 ]]; then
    echo "SKIPPED git hooks / global sync (--skip-hooks or --dry-run)"
    note "git hooks, global sync" "SKIPPED"
else
    hook_args=(--config "$AI_CONFIG_DIR" "$TARGET")
    if [[ -f "$TARGET/.pre-commit-config.yaml" || -f "$AI_CONFIG_DIR/.pre-commit-config.yaml" ]] \
        && ! command -v uvx >/dev/null 2>&1; then
        echo "error: uvx is required to validate the pre-commit config (install uv or --skip-hooks)" >&2
        note "git hooks, global sync" "FAILED (no uvx)"; FAILED=1
    else
        bash "$SELF_DIR/install-git-hooks.sh" "${hook_args[@]}"
        "$SELF_DIR/install-global-worktree-sync.sh"
        note "git hooks, global sync" "installed"
    fi
fi

echo
echo "Summary for $TARGET"
printf '  %s\n' "${SUMMARY[@]}"
if [[ $FAILED -ne 0 ]]; then
    echo "Completed with failures." >&2
    exit 1
fi
echo "Done. Start (or restart) a Claude Code / Copilot session in the target."
