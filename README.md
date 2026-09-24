# notify-codex-attention

English | [简体中文](README.zh-CN.md)

Clickable macOS alerts that bring you back to the terminal or IDE running the
Codex CLI session that needs you.

> Stop losing time to a Codex session waiting quietly for approval, a decision,
> or input while you think it is still working.

## Why this exists

Codex is most useful when it can work in the background. The problem is the
handoff: a task can reach an approval prompt, wait for a choice, or finish
without getting your attention. You move on, Codex stays blocked, and the delay
is only discovered much later.

`notify-codex-attention` closes that loop. It tells you exactly when Codex needs
you, summarizes the next action, and lets you click the alert to return to the
application hosting that Codex session. The contribution is not merely another
notification—it removes forgotten waiting time from the Codex workflow.

## What it does

- Alerts on real Codex permission requests
- Alerts when Codex needs a choice, text input, or a manual UI action
- Alerts when a Codex turn finishes
- Distinguishes **Needs attention** from **Task complete**
- Returns to the application that launched the originating Codex CLI
- Ignores ordinary tool calls and file writes while a turn is still running
- Replaces older alerts from the same Codex thread
- Uses a native AppKit overlay, with `terminal-notifier` and AppleScript fallbacks
- Requires no daemon, network service, or third-party Python package

## How it works

Lifecycle events feed a persistent, serialized queue:

1. `PermissionRequest` handles actual approvals; input-tool `PreToolUse` handles questions.
2. `Stop` handles reply endings. The legacy `notify` callback is retained and
   deduplicated by session + turn; prose keywords never imply approval.
3. `UserPromptSubmit`, `Interrupt`, `SessionEnd`, and synchronous input return
   cancel obsolete alerts. A manual skill call is only a fallback for unsupported pauses.

Multiple sessions queue rather than covering each other's overlays. Each alert
shows its project and session. Stop is a stopping attempt, not proof of successful
completion; a short debounce reduces premature alerts if another hook continues.
See [event routing](references/event-routing.md) for exact semantics and limitations.

When an alert is created, the notifier captures the macOS bundle ID inherited
from the application hosting that Codex CLI. The target is frozen into the
alert, so clicking it does not guess from the frontmost or most recently used
application. IDE-integrated terminals and macOS terminal applications are both
supported. If a host does not export usable metadata, use the explicit
`--activate-bundle` override.

## Requirements

- macOS
- Codex CLI
- A terminal application or IDE-integrated terminal
- Xcode Command Line Tools (`swiftc`)

Install the command-line tools if `swiftc` is unavailable:

```sh
xcode-select --install
```

## Installation

### 1. Clone the skill

```sh
git clone https://github.com/DyingCoderLin/notify-codex-attention.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention"
```

### 2. Build the native overlay

```sh
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" build
```

The generated `scripts/codex-attention-overlay` is built for the current Mac
architecture and is intentionally ignored by Git.

### 3. Configure turn-completion alerts

Add the following to `~/.codex/config.toml`. TOML does not expand `~` or
`$HOME`, so replace `/Users/YOU` with the absolute path to your home directory:

```toml
notify = ["/usr/bin/python3", "/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py"]

[tui]
notifications = false
```

Codex supports one global `notify` command. If another application already owns
that setting, configure it to chain this script instead of adding a second
`notify` key. Disabling built-in TUI notifications prevents duplicate alerts;
it does not disable the external callback or lifecycle hooks.

### 4. Configure lifecycle hooks

Preview and merge the hooks without replacing unrelated entries:

```sh
/usr/bin/python3 "$HOME/.codex/skills/notify-codex-attention/scripts/install_hooks.py"
/usr/bin/python3 "$HOME/.codex/skills/notify-codex-attention/scripts/install_hooks.py" --apply
```

Run `/hooks` in Codex and review/trust the new definitions, then reopen existing
sessions. Trust hashes are never changed by the installer. If a client uses an
isolated CODEX_HOME, install into that home too (`--codex-home /absolute/path`).
The per-user notification queue is shared across these homes.

### 5. Configure choice and input alerts

Add this rule to `~/.codex/AGENTS.md`:

```md
- Use `$notify-codex-attention` only for a required manual UI action or plain-text question without a supported input hook. Installed hooks own permission approvals, structured input requests, and reply completion; do not send duplicate manual alerts. Use the actual thread ID, never a shared placeholder.
```

Restart Codex after changing the global configuration.

## Permissions

The primary overlay does not require broad macOS notification access. Review
the global hook with `/hooks`, and approve only the narrow command prefix that
contains `/usr/bin/python3` plus the absolute path to `scripts/notify.py`.

The optional AppleScript and `terminal-notifier` fallbacks may request their own
macOS permissions.

## Verify

Run the build and deterministic test suite:

```sh
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" check
```

Send a live attention alert:

```sh
cd "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention"
/usr/bin/python3 scripts/notify.py \
  --kind attention \
  --message "Codex needs your input" \
  --session-id "manual-test"
```

Click the alert and confirm that you return to the application containing the
originating Codex CLI.

Inspect host routing without displaying an alert:

```sh
/usr/bin/python3 scripts/notify.py \
  --kind attention \
  --message "Route test" \
  --dry-run
```

The `activate` field should contain the originating host's bundle ID. For a host
without usable environment metadata, pass `--activate-bundle` with its bundle
ID, for example `com.example.Terminal`.

## Update

```sh
git -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" pull --ff-only
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" build
```

## Uninstall

Remove only this notifier from the `notify` chain in `~/.codex/config.toml`, its lifecycle
entry from `~/.codex/hooks.json`, and the matching rule from
`~/.codex/AGENTS.md`. Then delete the cloned skill directory.

## Repository layout

```text
.
├── README.md
├── README.zh-CN.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── codex_attention_overlay.swift
│   └── notify.py
├── tests/
│   └── test_notify.py
└── Makefile
```

## Development

```sh
make build   # compile the native overlay
make check   # build, check Python syntax, and run the test suite
make clean   # remove generated local artifacts
```
