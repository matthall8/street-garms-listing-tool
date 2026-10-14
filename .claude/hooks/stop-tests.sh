#!/bin/sh
# Stop hook: don't let an agent end its turn while the tests fail.
# Exit 2 sends the failure back to the agent. On the follow-up stop
# (stop_hook_active) it exits 0, so a failure it can't fix doesn't loop.
input=$(cat)
[ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
[ -x .venv/bin/python ] || exit 0
out=$(.venv/bin/python -m pytest -q -x 2>&1) && exit 0
printf 'Tests fail; fix them or say why before finishing:\n%s\n' \
  "$(printf '%s\n' "$out" | tail -n 30)" >&2
exit 2
