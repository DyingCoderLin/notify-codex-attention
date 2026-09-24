# Event routing and evidence

Research date: 2026-09-24. Local CLI: 0.156.1.

- [codex-redline phone_hook.py](https://github.com/prikevs/codex-redline/blob/4dabe54a2a72ab259e16ce41337c5d96f8908a73/phone_hook.py)
  forwards only Stop/UserPromptSubmit, session_id, turn_id and last_assistant_message.
- [phone-replies.mjs](https://github.com/prikevs/codex-redline/blob/4dabe54a2a72ab259e16ce41337c5d96f8908a73/src/phone-replies.mjs)
  validates IDs, limits to a bound thread, deduplicates thread+turn, rejects blank
  replies and queues playback. It does not implement Codex yes/no approval detection.
  We independently implement persistent multi-session queuing, rather than its
  single-bound-thread telephone interface.
- [Official hooks documentation](https://developers.openai.com/codex/hooks):
  PermissionRequest means approval is about to be requested; PreToolUse identifies
  the actual tool; Stop is a stopping attempt and can be continued by another hook.
  SessionEnd is session teardown, not reply completion. Some specialized tool paths
  bypass hooks. Hook output is always advisory `{}`, never an approval decision.

## Semantics

| Input | Action |
| --- | --- |
| PermissionRequest | Queue attention; use approval description, never command body |
| PreToolUse of request_user_input / request_user_input_async | Queue actual first question |
| PostToolUse of synchronous input | Cancel that input request |
| PostToolUse of approved command | Cancel matching permission request where identifiers/arguments match |
| Stop with nonblank reply | Queue reply-ended after 2 seconds |
| agent-turn-complete | Same completion key as Stop; one notification per session/turn |
| UserPromptSubmit | Track turn; cancel previous pending/displayed alerts in that session |
| Interrupt / SessionEnd | Cancel affected alerts |
| Other events / empty reply / missing IDs | No alert |

The SQLite queue stores short notification text and identities locally under
`~/.codex/state/attention` (override with `CODEX_ATTENTION_STATE_DIR`), with private permissions. Events older
than seven days are removed on the next event. A file lock serializes UI workers;
separate sessions never overwrite each other. Dead workers' in-flight events get
at most one retry on the next new notification. No always-running daemon is installed.

A notification shows project and a short session ID. Clicking returns to the
originating application; selecting an exact terminal tab is not supported. A
successful UI process exit does not prove the user read the notification. Native
fallback delivery and macOS focus behavior still depend on the client environment.

The 2-second Stop delay is a debounce, not proof that all other hooks accepted
stopping. A delayed continuation can still produce an early reply-ended alert.
Permission hooks also precede the final approval decision: other hooks/automatic
approval may consume the request; quick matching tool returns cancel the alert.
Async input has no documented answer hook here, so it remains until a later
completion/new turn/interrupt. This implementation does not scrape transcripts,
inspect arbitrary terminal text, or infer requests from yes/no keywords.

Separate CODEX_HOME directories require their own hooks.json installation. They
share the default per-user queue, so multiple client homes still serialize alerts.
