#!/usr/bin/env bash
# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
#
# Point a checkout (and its linked worktrees) at a shared Git hooks directory.
#
# Usage: install-git-hooks.sh [--hooks-dir <dir>] [--config <config-repo>] [<target>]
#   --hooks-dir DIR  hooks directory (default: <ai-bootstrap>/githooks, next to this script)
#   --config DIR     config repo; its .pre-commit-config.yaml is validated when present
#   target           checkout to configure (default: .)
#
# The pre-commit config is validated and its hook environments installed only when the
# target or the config repo has a .pre-commit-config.yaml (target wins).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hooks_dir="$SCRIPT_DIR/../githooks"
config_dir=""
target="."

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hooks-dir) hooks_dir="${2:?--hooks-dir needs a directory}"; shift 2 ;;
        --config) config_dir="${2:?--config needs a directory}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "error: unknown option: $1" >&2; exit 2 ;;
        *) target="$1"; shift ;;
    esac
done

[[ -d "$hooks_dir" ]] || { echo "error: hooks directory not found: $hooks_dir" >&2; exit 1; }
hooks_dir="$(cd "$hooks_dir" && pwd)"
git -C "$target" rev-parse --git-common-dir >/dev/null

pc_config=""
if [[ -f "$target/.pre-commit-config.yaml" ]]; then
    pc_config="$target/.pre-commit-config.yaml"
elif [[ -n "$config_dir" && -f "$config_dir/.pre-commit-config.yaml" ]]; then
    pc_config="$config_dir/.pre-commit-config.yaml"
fi
if [[ -n "$pc_config" ]]; then
    uvx pre-commit validate-config "$pc_config"
    uvx pre-commit install-hooks --config "$pc_config"
fi

git -C "$target" config --local core.hooksPath "$hooks_dir"
printf 'Activated Git hooks for %s and its linked worktrees: %s\n' "$target" "$hooks_dir"
