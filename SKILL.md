---
name: notify-codex-attention
description: Show a clickable native macOS alert that returns to the application hosting Codex CLI before Codex pauses mid-turn for a choice, requested input, or a manual UI action not represented by a Codex permission event.
---

# Notify Codex Attention

Before a mid-turn pause for a choice, requested input, or manual UI action, run
this outside the sandbox, then issue the request:

```text
/usr/bin/python3 "$HOME/.codex/skills/notify-codex-attention/scripts/notify.py" --kind attention --message "<concise action>" --session-id "<thread-or-unique-id>"
```

Resolve the command to the installation's canonical absolute path when invoking
it so a narrowly scoped approval can be reused. Keep the message non-sensitive
and at most 160 characters. Do not call it for permission approvals or a final
response: the `PermissionRequest` hook owns approvals, while the global `notify`
callback owns final questions and completed turns.

The script captures the originating terminal application's bundle ID and shows a
clickable Codex overlay that returns to that application, with
`terminal-notifier` and AppleScript fallbacks. Never block the main task if
delivery fails.
