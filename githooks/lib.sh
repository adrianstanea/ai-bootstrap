# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
# Sourced by the git hook shims; not itself a hook (git only runs files named after a hook).
# shellcheck shell=sh

# ai-bootstrap checkout that holds these hooks.
AI_BOOTSTRAP_ROOT=$(dirname "$(dirname "$(realpath "$0")")")
AI_HOOKS_RUNNER="$AI_BOOTSTRAP_ROOT/hooks/bin/ai-hooks"
export AI_BOOTSTRAP_ROOT AI_HOOKS_RUNNER

# Run the hook the repository installed itself (.git/hooks/<name>, e.g. by pre-commit or
# husky), which core.hooksPath would otherwise silently disable. Args: hook name, hook args.
chain_repo_hook() {
    name=$1
    shift
    hook="$(git rev-parse --git-common-dir)/hooks/$name"
    if [ -x "$hook" ]; then
        "$hook" "$@"
    fi
}
