#!/usr/bin/env bash
# Project-agnostic Claude Code SessionStart hook. Installed to
# ~/.claude/hooks/ai-bootstrap-worktree-sync.sh by install-global-worktree-sync.sh, and
# registered globally (runs for every session on this machine, any project) because
# project hooks cannot bootstrap into a directory without its own .claude/settings.json:
# Claude Code's settings discovery does not walk up parent directories.
#
# Only acts when the session's cwd is a *linked* git worktree (e.g.
# `git worktree add ../foo some-branch`) of a repo whose main checkout has opted in via a
# ".ai-config-source" pointer file (written by sync-to-reference.sh). Every other session
# (main checkout, unrelated project, non-git directory) is a silent, fast no-op. Never
# blocks session start: best-effort only.

# Replaced with the absolute sync directory by install-global-worktree-sync.sh.
SYNC_DIR="@SYNC_DIR@"

toplevel=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
common_dir=$(git rev-parse --git-common-dir 2>/dev/null) || exit 0
main_root=$(cd "$(dirname "$common_dir")" && pwd 2>/dev/null) || exit 0

# Main checkout itself: nothing to do.
[[ "$toplevel" == "$main_root" ]] && exit 0

pointer="$main_root/.ai-config-source"
[[ -f "$pointer" ]] || exit 0

sync_script="$SYNC_DIR/sync-to-reference.sh"
[[ -x "$sync_script" ]] || exit 0

# The pointer may list several config repo paths (the same working tree can be reachable
# from more than one environment); use the first that exists here.
while IFS= read -r ai_config_dir; do
    [[ -n "$ai_config_dir" && -f "$ai_config_dir/ai-config.paths" ]] || continue
    "$sync_script" --config "$ai_config_dir" "$toplevel" >/dev/null 2>&1 || true
    exit 0
done < "$pointer"

exit 0
