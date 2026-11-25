#!/usr/bin/env bash
#
# Copyright (c) 2026 Adrian Stanea
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Interactively stage and commit logical groups of changes described by a
# plan file. Never adds a Co-authored-by trailer; always commits with
# --signoff. See ../SKILL.md for the workflow this script is part of.
#
# Usage:
#   interactive-commit.sh <plan-file>
#
# Plan file format (see ../assets/commit-plan.example.txt):
#   Blocks separated by a line of exactly "---".
#   First line of each block: one or more paths/globs, space separated.
#   Remaining lines: the proposed commit message (subject + body).

set -euo pipefail

plan_file="${1:?usage: $0 <plan-file>}"

if [[ ! -f "$plan_file" ]]; then
    echo "error: plan file not found: $plan_file" >&2
    exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "error: not inside a git repository" >&2
    exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "== Repository status before starting =="
git status --short
echo

if ! git diff --cached --quiet; then
    echo "Unstaging pre-existing staged changes so each commit below contains"
    echo "exactly its own group's paths (nothing left over from before)."
    git reset >/dev/null
    echo
fi

# Split the plan file into one temp file per block (on lines that are
# exactly "---"). Blocks are written to files, not bash variables/command
# substitution, because $(...) silently strips NUL bytes and newlines
# don't uniquely mark block boundaries within a multi-line message body.
block_dir="$(mktemp -d)"
trap 'rm -rf "$block_dir"' EXIT

awk -v dir="$block_dir" '
    BEGIN { n = 0; out = sprintf("%s/%04d", dir, n) }
    /^---$/ { n++; out = sprintf("%s/%04d", dir, n); next }
    { print > out }
' "$plan_file"

mapfile -t block_files < <(find "$block_dir" -maxdepth 1 -type f | sort)

commit_index=0
total=${#block_files[@]}

for block_file in "${block_files[@]}"; do
    commit_index=$((commit_index + 1))

    paths_line="$(head -n1 "$block_file")"
    message="$(tail -n +2 "$block_file")"
    # Trim a single leading/trailing blank line from the message.
    message="$(printf '%s' "$message" | sed -e '1{/^$/d}' -e '${/^$/d}')"

    [[ -z "${paths_line// /}" ]] && continue

    echo "=============================================================="
    echo "Commit ${commit_index}/${total}"
    echo "Paths: ${paths_line}"
    echo "--------------------------------------------------------------"
    echo "Proposed message:"
    echo "${message}"
    echo "--------------------------------------------------------------"

    # shellcheck disable=SC2086
    git add -- ${paths_line}

    echo "Diff to be committed:"
    git --no-pager diff --cached -- ${paths_line} || true
    echo "--------------------------------------------------------------"

    while true; do
        read -r -p "Commit as-is [y], edit message [e], skip [s], abort [q]? " choice
        case "$choice" in
            y|Y)
                tmp_msg="$(mktemp)"
                printf '%s\n' "$message" >"$tmp_msg"
                git commit --signoff --file="$tmp_msg"
                rm -f "$tmp_msg"
                break
                ;;
            e|E)
                tmp_msg="$(mktemp)"
                printf '%s\n' "$message" >"$tmp_msg"
                "${EDITOR:-nano}" "$tmp_msg"
                git commit --signoff --file="$tmp_msg"
                rm -f "$tmp_msg"
                break
                ;;
            s|S)
                echo "Skipping this group (leaving changes staged for later)."
                git reset -- ${paths_line}
                break
                ;;
            q|Q)
                echo "Aborting. Remaining working-tree changes left untouched."
                exit 1
                ;;
            *)
                echo "Please answer y, e, s, or q."
                ;;
        esac
    done
    echo
done

echo "== Final repository status =="
git status --short
