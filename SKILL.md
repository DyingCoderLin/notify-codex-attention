---
name: notify-codex-attention
description: Show a clickable native macOS alert immediately before Codex pauses mid-turn in iTerm2 for approval, a decision, requested input, or a manual UI action.
---

# Notify Codex Attention

Before a mid-turn pause for user action, run this outside the sandbox, then issue
the request:

```text
/usr/bin/python3 "$HOME/.codex/skills/notify-codex-attention/scripts/notify.py" --kind attention --message "<concise action>" --session-id "<thread-or-unique-id>"
```

Resolve the command to the installation's canonical absolute path when invoking
it so a narrowly scoped approval can be reused. Keep the message non-sensitive
and at most 160 characters. Do not call it for a final response; the global
`notify` callback handles final questions and completed turns. Keep
`PermissionRequest` as a compatibility fallback.

The script shows a clickable Codex overlay that activates iTerm2, with
`terminal-notifier` and AppleScript fallbacks. Never block the main task if
delivery fails.
