#!/usr/bin/env bash
# Offline tests for the sync scripts. Usage: sync/tests/test_sync.sh
set -euo pipefail

SYNC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH_BASE="${TEST_TMP_BASE:-/tmp/claude-1000}"
mkdir -p "$SCRATCH_BASE"
T="$(mktemp -d -p "$SCRATCH_BASE")"
trap 'rm -rf "$T"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t \
    GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

fails=0
check() { # check <desc> <command...>
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then echo "ok   $desc"; else echo "FAIL $desc"; fails=$((fails + 1)); fi
}

CFG="$T/my-config"
TGT="$T/target"
mkdir -p "$CFG/rules" "$CFG/docs" "$TGT"
printf 'a\n' > "$CFG/AGENTS.md"
printf 'r\n' > "$CFG/rules/one.md"
printf 'd\n' > "$CFG/docs/x.md"
printf 's\n' > "$CFG/settings.json"
cat > "$CFG/ai-config.paths" <<'EOP'
# comment
AGENTS.md

rules/
docs/x.md
settings.json
missing.md
EOP
printf 'legacy.md\n' > "$CFG/ai-config.migrate"
git -C "$TGT" init -q
git -C "$TGT" commit -q --allow-empty -m init
git -C "$TGT" worktree add -q "$T/linked" -b linked
# Diverged real file, and a skipped one.
mkdir -p "$TGT/docs"
printf 'local edit\n' > "$TGT/docs/x.md"
printf 'mine\n' > "$TGT/settings.json"
printf 'settings.json\n' > "$TGT/.ai-config-skip"
# Legacy link into the config repo, to be migrated.
printf 'l\n' > "$CFG/legacy.md"
ln -s "../my-config/legacy.md" "$TGT/legacy.md"

out="$("$SYNC/sync-to-reference.sh" --config "$CFG" "$TGT" 2>&1)"
check "relative link for file" test "$(readlink "$TGT/AGENTS.md")" = "../my-config/AGENTS.md"
check "relative link for directory" test "$(readlink "$TGT/rules")" = "../my-config/rules"
check "link resolves" test -f "$TGT/rules/one.md"
check "diverged file untouched" test "$(cat "$TGT/docs/x.md")" = "local edit"
check "diverged warning printed" grep -q "NOT touched" <<<"$out"
check ".ai-config-skip honoured" test ! -L "$TGT/settings.json"
check "skip message printed" grep -q "skipped (listed in .ai-config-skip): settings.json" <<<"$out"
check "legacy link migrated" test ! -e "$TGT/legacy.md" -a ! -L "$TGT/legacy.md"
excl="$TGT/.git/info/exclude"
check "exclude block names config dir" grep -q "BEGIN ai-config (managed by my-config/" "$excl"
check "exclude lists linked path" grep -qx "/AGENTS.md" "$excl"
check "exclude omits diverged path" bash -c "! grep -qx '/docs/x.md' '$excl'"
check ".ai-config-source recorded" grep -qxF "$CFG" "$TGT/.ai-config-source"
"$SYNC/sync-to-reference.sh" --config "$CFG" "$TGT" >/dev/null 2>&1
check ".ai-config-source deduped" test "$(grep -cxF "$CFG" "$TGT/.ai-config-source")" = 1
check "exclude block not duplicated" test "$(grep -c '^# BEGIN ai-config' "$excl")" = 1
check "no config -> error" bash -c "cd '$T' && ! '$SYNC/sync-to-reference.sh' '$TGT'"
check "target required" bash -c "! '$SYNC/sync-to-reference.sh' --config '$CFG'"

# AI_CONFIG_DIR and linked worktree.
AI_CONFIG_DIR="$CFG" "$SYNC/sync-to-reference.sh" "$T/linked" >/dev/null 2>&1
check "env config + linked worktree link" test -L "$T/linked/AGENTS.md"

# Pull a real file back.
printf 'edited in target\n' > "$TGT/docs/x.md"
"$SYNC/pull-from-reference.sh" --config "$CFG" "$TGT" >/dev/null 2>&1
check "pull copies real file back" test "$(cat "$CFG/docs/x.md")" = "edited in target"

# Global hook installer against a throwaway HOME.
H="$T/home"
mkdir -p "$H/.claude"
cat > "$H/.claude/settings.json" <<'EOJ'
{"hooks": {"SessionStart": [
  {"hooks": [{"type": "command", "command": "bash ~/.claude/hooks/sync-worktree-ai-config.sh"}]},
  {"hooks": [{"type": "command", "command": "echo other"}]}]}, "keep": 1}
EOJ
HOME="$H" "$SYNC/install-global-worktree-sync.sh" >/dev/null 2>&1
HOME="$H" "$SYNC/install-global-worktree-sync.sh" >/dev/null 2>&1
check "global hook installed" test -x "$H/.claude/hooks/ai-bootstrap-worktree-sync.sh"
check "old entry removed, new once" test "$(grep -c 'ai-bootstrap-worktree-sync' "$H/.claude/settings.json")" = 1
check "old entry gone" bash -c "! grep -q 'sync-worktree-ai-config' '$H/.claude/settings.json'"
check "other entries preserved" grep -q "echo other" "$H/.claude/settings.json"

# Bootstrap dry run.
check "bootstrap dry-run exits 0" "$SYNC/bootstrap.sh" --config "$CFG" --target "$TGT" \
    --dry-run --skip-external --no-copilot --skip-hooks
check "bootstrap requires target" bash -c "! '$SYNC/bootstrap.sh' --config '$CFG'"

if [[ $fails -ne 0 ]]; then echo "$fails test(s) failed"; exit 1; fi
echo "all tests passed"
