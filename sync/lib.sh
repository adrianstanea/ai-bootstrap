#!/usr/bin/env bash
# Shared helpers for the sync scripts; sourced, never run directly.
#
# Config repo resolution: --config <dir>, else env AI_CONFIG_DIR, else the git toplevel of
# the current directory. The path list lives in <config>/ai-config.paths (one repo-relative
# path per line; '#' comments and blank lines ignored; trailing '/' optional). Legacy links
# to migrate away come from the optional <config>/ai-config.migrate (same format).

# resolve_config_dir [explicit-dir]: print the absolute config repo path or fail.
resolve_config_dir() {
    local dir="${1:-${AI_CONFIG_DIR:-}}"
    if [[ -z "$dir" ]]; then
        dir="$(git rev-parse --show-toplevel 2>/dev/null)" || {
            echo "error: no config repo: pass --config <dir>, set AI_CONFIG_DIR, or run" >&2
            echo "  inside the config repo's git checkout" >&2
            return 1
        }
    fi
    [[ -d "$dir" ]] || { echo "error: config directory not found: $dir" >&2; return 1; }
    (cd "$dir" && pwd)
}

# read_list <file>: print normalized entries (no comments, blanks, or trailing slash).
read_list() {
    local file="$1" line
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        while [[ "$line" == */ ]]; do line="${line%/}"; done
        [[ -n "$line" ]] && printf '%s\n' "$line"
    done < "$file"
    return 0
}

# load_paths <config-dir>: fill the global PATHS array from ai-config.paths (required).
load_paths() {
    local file="$1/ai-config.paths" p
    if [[ ! -f "$file" ]]; then
        echo "error: manifest not found: $file" >&2
        return 1
    fi
    PATHS=()
    while IFS= read -r p; do PATHS+=("$p"); done < <(read_list "$file")
    return 0
}
