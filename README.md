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

Three paths feed the same notifier:

1. A global Codex `notify` callback handles completed turns and final questions.
2. A `PermissionRequest` hook handles real approval prompts.
3. A short global `AGENTS.md` rule handles mid-turn choices, requested input,
   and manual UI actions.

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

### 4. Configure approval alerts

Create `~/.codex/hooks.json` with the following content. If the file already
exists, merge the `PermissionRequest` entry into its existing `hooks` object.
Replace `/Users/YOU` with your absolute home directory:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 \"/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py\" --hook",
            "timeout": 10,
            "statusMessage": "Sending Codex attention notification"
          }
        ]
      }
    ]
  }
}
```

Restart Codex, run `/hooks`, and trust the exact hook definition. Codex records
trust against the hook hash and asks for review again if the definition changes.

### 5. Configure choice and input alerts

Add this rule to `~/.codex/AGENTS.md`:

```md
- Before a mid-turn choice, requested input, or manual UI action, use `$notify-codex-attention`. Do not call it for permission approvals or final responses; the `PermissionRequest` hook and global `notify` callback own those.
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

Remove the `notify` entry from `~/.codex/config.toml`, the `PermissionRequest`
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
