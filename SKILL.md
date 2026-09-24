---
name: notify-codex-attention
description: Maintain Codex macOS attention notifications, or send a fallback alert when Codex must pause for a manual UI action or plain-text question that is not represented by an installed input hook.
---

# Notify Codex Attention

Installed hooks own permission approvals (`PermissionRequest`), supported structured
input tools (`PreToolUse` for `request_user_input` / `request_user_input_async`), and
finished replies (`Stop`, with the legacy `notify` callback as a deduplicated fallback).
Do not manually alert for these events, ordinary progress updates, optional offers,
subagent completion, or merely mentioning approval/confirmation in prose.

Only if the user really must act and no supported input hook represents that pause,
run this immediately before presenting the actionable request:

```text
/usr/bin/python3 "$HOME/.codex/skills/notify-codex-attention/scripts/notify.py" --kind attention --message "<concise action>" --session-id "<actual thread id>"
```

Use the canonical installation path and real `CODEX_THREAD_ID` (or known current
thread ID), never an invented shared ID. Keep text non-sensitive and <=160 chars.
If identity is unavailable, skip the fallback. Run outside the sandbox when needed
for macOS UI. Do not block the task or request an extra user approval solely to
send a fallback alert if the existing narrow command permission is unavailable.

Notifications are queued across processes and identified by session + turn + event.
Submitting a new turn, interrupting, or returning from synchronous user input
cancels obsolete queued alerts. Async input returns immediately; its return is not
an acknowledgement. Completion means the reply ended, not that the whole task
succeeded. Stop hooks can request continuation; a brief delay and new-turn
cancellation reduce premature alerts but are not a confirmed-turn-completed API.

For setup/maintenance, use `scripts/install_hooks.py` to preview, or `--apply` to
merge hooks with a backup. Review new hooks in Codex `/hooks`; never write trust
hashes. Preserve an existing global `notify` wrapper (including Computer Use).
Specialized tool paths/clients may omit hooks; test on the actual client. The
fallback remains available for unsupported input paths. See
[implementation notes](references/event-routing.md) for sources and limitations.
