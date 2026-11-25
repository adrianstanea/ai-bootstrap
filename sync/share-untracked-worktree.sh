#!/usr/bin/env bash
# Share genuinely git-untracked files (not AI-config content -- that's
# sync-to-reference.sh's job) across all of a target repo's registered
# git worktrees.
#
# Usage: share-untracked-worktree.sh [--config <config-repo>] <source-worktree> [--yes]
#                                    [--only <relative-path>]
#   --config DIR   config repo holding ai-config.paths (default: $AI_CONFIG_DIR, else the
#                  git toplevel of the current directory)
#
# Moves each eligible untracked file out of the source worktree into the config
# repo's local-untracked/ directory (keep it gitignored there -- it's the target
# repo's own untracked working state, not content the config repo versions),
# then symlinks it back into every one of the target repo's registered
# worktrees with a *relative* symlink -- needed for the same reason
# sync-to-reference.sh uses relative links: the same worktree can be
# reachable from more than one environment (host vs. a devcontainer bind
# mount) with a different absolute-path view of it.
#
# Run it by hand and review the proposed file list before confirming.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() {
    printf 'Usage: %s [--config <config-repo>] <source-worktree> [--yes] [--only <path>]\n' \
        "$0" >&2
}

config_arg=

confirm=false
only_path=
positional=()
while (($# > 0)); do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        --config)
            if (($# < 2)); then
                usage
                exit 2
            fi
            config_arg=$2
            shift 2
            ;;
        --yes)
            confirm=true
            shift
            ;;
        --only)
            if (($# < 2)); then
                usage
                exit 2
            fi
            only_path=$2
            shift 2
            ;;
        --)
            shift
            positional+=("$@")
            break
            ;;
        -*)
            usage
            exit 2
            ;;
        *)
            positional+=("$1")
            shift
            ;;
    esac
done

if ((${#positional[@]} != 1)); then
    usage
    exit 2
fi

AI_CONFIG_ROOT=$(resolve_config_dir "$config_arg") || exit 1
shared_root="$AI_CONFIG_ROOT/local-untracked"
load_paths "$AI_CONFIG_ROOT" || exit 1

source_dir=$(cd -- "${positional[0]}" && pwd -P) || {
    printf 'Error: source worktree does not exist: %s\n' "${positional[0]}" >&2
    exit 1
}

git -C "$source_dir" rev-parse --show-toplevel >/dev/null || {
    printf 'Error: not inside a Git worktree: %s\n' "$source_dir" >&2
    exit 1
}

worktrees=()
while IFS= read -r -d '' record; do
    case "$record" in
        "worktree "*) worktrees+=("${record#worktree }") ;;
    esac
done < <(git -C "$source_dir" worktree list --porcelain -z)

source_is_registered=false
for worktree in "${worktrees[@]}"; do
    if [[ $worktree == "$source_dir" ]]; then
        source_is_registered=true
        break
    fi
done
if [[ $source_is_registered != true ]]; then
    printf 'Error: source is not a registered worktree: %s\n' "$source_dir" >&2
    exit 1
fi

# Paths listed in ai-config.paths (plus pairing metadata and legacy skill/agent links) are
# never eligible here, even if something temporarily un-links one -- this script must never
# re-absorb AI-config content.
is_ai_config_owned_path() {
    local p
    case "$1" in
        .ai-config-source|.ai-config-skip|\
        .claude/hooks|.claude/hooks/*|.claude/agents|.claude/agents/*|\
        .claude/skills|.claude/skills/*|.agents/skills|.agents/skills/*|\
        .github/skills|.github/skills/*)
            return 0
            ;;
    esac
    for p in "${PATHS[@]}"; do
        [[ "$1" == "$p" || "$1" == "$p"/* ]] && return 0
    done
    return 1
}

is_excluded_path() {
    local relative_path=$1
    local path="/$relative_path/"
    local filename=${relative_path##*/}

    is_ai_config_owned_path "$relative_path" && return 0

    case "$path" in
        */.venv/*|*/venv/*|*/build/*|*/.worktrees/*|*/.claude/worktrees/*|\
        */node_modules/*|*/.pytest_cache/*|*/__pycache__/*|*/.mypy_cache/*|\
        */.ruff_cache/*|*/.cache/*|*/dist/*|*/out/*|*/coverage/*|\
        */_build/*|*/_doxygen/*|*/autogen/*)
            return 0
            ;;
    esac
    case "$filename" in
        .env|.env.*|*.pem|*.key|*.p12|*.local*|*:Zone.Identifier)
            return 0
            ;;
    esac
    case "$relative_path" in
        .claude/scheduled_tasks.lock|.claude/scheduled_tasks.json|\
        .claude/hooks/.state/*|.claude/routines/.state/*|.github/hooks/.state/*)
            return 0
            ;;
    esac
    return 1
}

mapfile -d '' -t untracked < <(
    {
        git -C "$source_dir" ls-files --others --exclude-standard -z
        mapfile -d '' -t ignored_entries < <(
            git -C "$source_dir" ls-files --others --ignored \
                --exclude-standard --directory -z | sort -zu
        )
        expanded_directories=()
        for entry in "${ignored_entries[@]}"; do
            if [[ $entry == */ ]]; then
                directory=${entry%/}
                if is_excluded_path "$directory/placeholder"; then
                    continue
                fi
                already_expanded=false
                for expanded_directory in "${expanded_directories[@]}"; do
                    if [[ $directory == "$expanded_directory/"* ]]; then
                        already_expanded=true
                        break
                    fi
                done
                [[ $already_expanded == false ]] || continue
                expanded_directories+=("$directory")
                find "$source_dir/$directory" \
                    -type d \( \
                        -name .git -o -name .venv -o -name venv -o -name build \
                        -o -name .worktrees -o -name node_modules \
                        -o -name .pytest_cache -o -name __pycache__ \
                        -o -name .mypy_cache -o -name .ruff_cache -o -name .cache \
                        -o -name dist -o -name out -o -name coverage \
                        -o -name _build -o -name _doxygen -o -name autogen \
                        -o -path "$source_dir/.claude/worktrees" \
                    \) -prune -o \( -type f -o -type l \) -print0 |
                    while IFS= read -r -d '' path; do
                        printf '%s\0' "${path#"$source_dir"/}"
                    done
            else
                printf '%s\0' "$entry"
            fi
        done
    } | while IFS= read -r -d '' relative_path; do
        if ! is_excluded_path "$relative_path"; then
            printf '%s\0' "$relative_path"
        fi
    done | sort -zu
)

if [[ -n $only_path ]]; then
    if [[ $only_path == /* || $only_path == .. || $only_path == ../* || \
        $only_path == */../* || $only_path == */.. ]]; then
        printf 'Error: --only requires a repository-relative path without ..\n' >&2
        exit 2
    fi
    selected=()
    for relative_path in "${untracked[@]}"; do
        if [[ $relative_path == "$only_path" ]]; then
            selected+=("$relative_path")
        fi
    done
    if ((${#selected[@]} == 0)); then
        printf 'No eligible untracked file matches: %q\n' "$only_path" >&2
        exit 1
    fi
    untracked=("${selected[@]}")
fi

if ((${#untracked[@]} == 0)); then
    printf 'No eligible untracked files in %s\n' "$source_dir"
    exit 0
fi

is_expected_link() {
    local path=$1
    local relative_path=$2
    local link_target
    local expected

    [[ -L $path ]] || return 1
    link_target=$(readlink -- "$path" && printf '.') || return 1
    link_target=${link_target%.}
    expected=$(realpath --relative-to="$(dirname -- "$path")" "$shared_root/$relative_path" 2>/dev/null) || return 1
    [[ $link_target == "$expected"$'\n' || $link_target == "$expected" ]]
}

is_tracked_path() {
    local worktree=$1
    local relative_path=$2
    local key="$worktree/$relative_path"
    [[ ${tracked_paths["$key"]+present} ]]
}

declare -A tracked_paths=()
tracked_path=
prefix=
part=
remaining=
for worktree in "${worktrees[@]}"; do
    while IFS= read -r -d '' tracked_path; do
        prefix=
        remaining=$tracked_path
        while [[ $remaining == */* ]]; do
            part=${remaining%%/*}
            prefix=${prefix:+$prefix/}$part
            tracked_paths["$worktree/$prefix"]=1
            remaining=${remaining#*/}
        done
        prefix=${prefix:+$prefix/}$remaining
        tracked_paths["$worktree/$prefix"]=1
    done < <(git -C "$worktree" ls-files -z)
done

has_safe_parent_directories() {
    local base=$1
    local relative_path=$2
    local parent_path=${relative_path%/*}
    local current=$base
    local part
    local remaining

    [[ $parent_path != "$relative_path" ]] || return 0
    remaining=$parent_path
    while [[ $remaining == */* ]]; do
        part=${remaining%%/*}
        current="$current/$part"
        if [[ -e $current || -L $current ]]; then
            [[ -d $current && ! -L $current ]] || return 1
        fi
        remaining=${remaining#*/}
    done
    current="$current/$remaining"
    if [[ -e $current || -L $current ]]; then
        [[ -d $current && ! -L $current ]] || return 1
    fi
}

eligible=()
conflicts=()
for relative_path in "${untracked[@]}"; do
    source_path="$source_dir/$relative_path"
    shared_path="$shared_root/$relative_path"
    source_conflicts=()
    has_missing_destination=false

    if is_expected_link "$source_path" "$relative_path"; then
        if [[ ! -e $shared_path && ! -L $shared_path ]]; then
            source_conflicts+=("$relative_path (shared target is missing)")
        fi
    elif [[ ! -e $source_path && ! -L $source_path ]]; then
        source_conflicts+=("$relative_path (source file is missing)")
    elif [[ -e $shared_path || -L $shared_path ]]; then
        source_conflicts+=("$relative_path (shared target already exists)")
    fi

    for worktree in "${worktrees[@]}"; do
        target_path="$worktree/$relative_path"
        if ! has_safe_parent_directories "$worktree" "$relative_path"; then
            conflicts+=("$relative_path (parent is not a real directory in $worktree)")
            continue
        fi
        if is_expected_link "$target_path" "$relative_path"; then
            continue
        fi
        if [[ $worktree == "$source_dir" ]]; then
            continue
        fi
        if [[ -e $target_path || -L $target_path ]]; then
            conflicts+=("$relative_path (destination exists in $worktree)")
            continue
        fi
        if is_tracked_path "$worktree" "$relative_path"; then
            conflicts+=("$relative_path (tracked path in $worktree)")
            continue
        fi
        has_missing_destination=true
    done

    if ((${#source_conflicts[@]} > 0)); then
        conflicts+=("${source_conflicts[@]}")
    elif [[ $has_missing_destination == true ]]; then
        eligible+=("$relative_path")
    fi
done

if ((${#conflicts[@]} > 0)); then
    printf 'Skipping %d conflicting destination(s); unaffected worktrees can still be linked:\n' \
        "${#conflicts[@]}" >&2
    limit=20
    for ((index = 0; index < ${#conflicts[@]} && index < limit; index++)); do
        printf '  %s\n' "${conflicts[index]}" >&2
    done
    if ((${#conflicts[@]} > limit)); then
        printf '  ... and %d more conflict(s)\n' \
            "$((${#conflicts[@]} - limit))" >&2
    fi
fi

if ((${#eligible[@]} == 0)); then
    printf 'No conflict-free files to share; nothing was moved.\n' >&2
    exit 1
fi

printf 'Will share %d untracked file(s) across %d worktree(s):\n' \
    "${#eligible[@]}" "${#worktrees[@]}"
limit=20
for ((index = 0; index < ${#eligible[@]} && index < limit; index++)); do
    printf '  %q\n' "${eligible[index]}"
done
if ((${#eligible[@]} > limit)); then
    printf '  ... and %d more file(s)\n' "$((${#eligible[@]} - limit))"
fi
if [[ $confirm != true ]]; then
    if [[ ! -t 0 ]]; then
        printf 'Error: run interactively or pass --yes to proceed.\n' >&2
        exit 2
    fi
    read -r -p 'Move files into shared storage and symlink them? [y/N] ' answer
    case "$answer" in
        [yY]|[yY][eE][sS]) ;;
        *) printf 'Cancelled; no files were moved.\n'; exit 0 ;;
    esac
fi

mkdir -p -- "$shared_root"
for relative_path in "${eligible[@]}"; do
    source_path="$source_dir/$relative_path"
    shared_path="$shared_root/$relative_path"

    if ! is_expected_link "$source_path" "$relative_path"; then
        mkdir -p -- "${shared_path%/*}"
        mv -- "$source_path" "$shared_path"
    fi

    for worktree in "${worktrees[@]}"; do
        target_path="$worktree/$relative_path"
        if ! is_expected_link "$target_path" "$relative_path"; then
            if [[ -e $target_path || -L $target_path ]]; then
                printf 'Leaving existing destination unchanged: %s (%s)\n' \
                    "$worktree" "$relative_path" >&2
                continue
            fi
            if ! has_safe_parent_directories "$worktree" "$relative_path"; then
                printf 'Leaving destination with unsafe parent unchanged: %s (%s)\n' \
                    "$worktree" "$relative_path" >&2
                continue
            fi
            if is_tracked_path "$worktree" "$relative_path"; then
                printf 'Leaving tracked destination unchanged: %s (%s)\n' \
                    "$worktree" "$relative_path" >&2
                continue
            fi
            mkdir -p -- "${target_path%/*}"
            rel_target="$(realpath --relative-to="${target_path%/*}" "$shared_path")"
            ln -s -- "$rel_target" "$target_path"
        fi
    done
done

printf 'Shared untracked files under %s\n' "$shared_root"
