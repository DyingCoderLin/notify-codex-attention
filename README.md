# Codex Attention Notifications

A personal Codex skill for clickable, native-looking macOS alerts when Codex
needs input or finishes a turn in iTerm2.

The primary backend is a small AppKit overlay. Clicking it activates iTerm2. If
the overlay is unavailable, the notifier falls back to `terminal-notifier` and
then AppleScript.

## Requirements

- macOS
- iTerm2
- Codex CLI
- Xcode Command Line Tools (`swiftc`)

## Install

Clone the repository into the global skills directory and build the local
overlay:

```sh
git clone <your-repository-url> ~/.codex/skills/notify-codex-attention
cd ~/.codex/skills/notify-codex-attention
make build
```

Add the notifier to `~/.codex/config.toml`, replacing `/Users/YOU` with the
absolute path to your home directory:

```toml
notify = ["/usr/bin/python3", "/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py"]
```

If another tool already owns the Codex `notify` callback, configure that tool to
chain this script instead of defining a second `notify` key.

For mid-turn approval and input alerts, add this rule to a global `AGENTS.md`:

```md
- Before a mid-turn approval, decision, input, or manual-action pause, use `$notify-codex-attention`; the global `notify` callback handles final questions and completed turns.
```

The first native notification may require a narrowly scoped Codex approval for
the Python script. macOS may also ask for Automation permission when the fallback
backends are used.

## Verify

Run the reproducible checks:

```sh
make check
```

Send a live attention alert:

```sh
/usr/bin/python3 scripts/notify.py \
  --kind attention \
  --message "Please return to Codex" \
  --session-id "manual-test"
```

Test completion-event routing without displaying an alert:

```sh
/usr/bin/python3 scripts/notify.py \
  '{"type":"agent-turn-complete","thread-id":"manual-test","last-assistant-message":"Task complete."}' \
  --dry-run
```

## Repository layout

- `SKILL.md`: Codex skill instructions
- `agents/openai.yaml`: skill UI and invocation policy
- `scripts/notify.py`: event parsing and backend selection
- `scripts/codex_attention_overlay.swift`: native clickable overlay source
- `Makefile`: local build and checks

The compiled overlay is intentionally ignored because it is architecture-specific.
