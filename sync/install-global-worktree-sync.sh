#!/usr/bin/env bash
# One-time, per-machine installer. Copies global/sync-worktree-ai-config.sh to
# ~/.claude/hooks/ai-bootstrap-worktree-sync.sh and registers it as a global SessionStart
# hook in ~/.claude/settings.json. The settings file is merged, never overwritten, and an
# entry for the old name (sync-worktree-ai-config.sh) is removed. Safe to re-run.
#
# Usage: install-global-worktree-sync.sh [-h|--help]

set -euo pipefail

case "${1:-}" in
    -h|--help) sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "") ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_HOOK="$SCRIPT_DIR/global/sync-worktree-ai-config.sh"
DEST_HOOK="$HOME/.claude/hooks/ai-bootstrap-worktree-sync.sh"
OLD_HOOK="$HOME/.claude/hooks/sync-worktree-ai-config.sh"
SETTINGS="$HOME/.claude/settings.json"

mkdir -p "$HOME/.claude/hooks"
sed "s|@SYNC_DIR@|$SCRIPT_DIR|" "$SRC_HOOK" > "$DEST_HOOK"
chmod +x "$DEST_HOOK"
echo "installed: $DEST_HOOK"
if [[ -f "$OLD_HOOK" ]]; then
    rm -f "$OLD_HOOK"
    echo "removed old hook file: $OLD_HOOK"
fi

python3 -I - "$SETTINGS" <<'PYEOF'
import json
import os
import sys

settings_path = sys.argv[1]
command = "bash ~/.claude/hooks/ai-bootstrap-worktree-sync.sh"
old_command = "bash ~/.claude/hooks/sync-worktree-ai-config.sh"

if os.path.exists(settings_path):
    with open(settings_path) as f:
        data = json.load(f)
else:
    data = {}

changed = False
hooks = data.setdefault("hooks", {})
session_start = hooks.setdefault("SessionStart", [])

for entry in list(session_start):
    kept = [h for h in entry.get("hooks", []) if h.get("command") != old_command]
    if len(kept) != len(entry.get("hooks", [])):
        changed = True
        if kept:
            entry["hooks"] = kept
        else:
            session_start.remove(entry)
        print("removed: old SessionStart hook entry")

already_present = any(
    h.get("command") == command
    for entry in session_start
    for h in entry.get("hooks", [])
)

if already_present:
    print("already registered: SessionStart hook")
else:
    session_start.append({"hooks": [{"type": "command", "command": command}]})
    changed = True
    print(f"registered: SessionStart hook in {settings_path}")

if changed:
    with open(settings_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
PYEOF

echo "Done. New linked-worktree sessions in any project with a .ai-config-source pointer"
echo "in their main checkout will now auto-sync AI config on SessionStart."
