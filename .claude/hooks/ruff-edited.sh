#!/bin/sh
# PostToolUse hook: lint each Python file in this repo straight after an
# agent edits it. Exit 2 shows the findings to the agent.
f=$(jq -r '.tool_input.file_path // empty')
case "$f" in "$CLAUDE_PROJECT_DIR"/*.py) ;; *) exit 0 ;; esac
[ -x "$CLAUDE_PROJECT_DIR/.venv/bin/ruff" ] || exit 0
out=$("$CLAUDE_PROJECT_DIR/.venv/bin/ruff" check --output-format=concise "$f" 2>&1) && exit 0
printf 'ruff check failed for %s:\n%s\n' "$f" "$out" >&2
exit 2
