# notify-codex-attention

Clickable macOS alerts for Codex CLI approvals, decisions, and completed turns
in iTerm2.

Codex can run for a while before it needs you. This skill shows a native-looking
alert in the upper-right corner of the active display, summarizes the action,
and takes you back to iTerm2 when clicked.

## Features

- Alerts when Codex needs approval, a choice, text input, or a manual UI action
- Completion alerts from the global Codex `notify` callback
- Click-to-activate iTerm2
- Separate **Needs attention** and **Task complete** states
- Replaces older alerts from the same Codex thread
- Native AppKit overlay that does not depend on Notification Center banners
- `terminal-notifier` and AppleScript fallbacks
- No daemon, network service, or Python package dependencies

## How it works

There are two notification paths:

1. Codex's global `notify` callback sends completed turns and final questions to
   `scripts/notify.py`.
2. A short global `AGENTS.md` rule tells Codex to invoke the skill immediately
   before a mid-turn pause that needs your attention.

The Python script classifies the event and launches a small AppKit overlay. The
overlay is compiled locally from the included Swift source, so the repository
does not ship an architecture-specific binary.

## Requirements

- macOS
- iTerm2
- Codex CLI
- Xcode Command Line Tools (`swiftc`)

Install the command-line tools if `swiftc` is unavailable:

```sh
xcode-select --install
```

## Installation

### 1. Clone the skill

Replace `YOUR_GITHUB_USERNAME` with your GitHub username:

```sh
git clone https://github.com/YOUR_GITHUB_USERNAME/notify-codex-attention.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention"
```

### 2. Build the native overlay

```sh
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" build
```

This creates `scripts/codex-attention-overlay` for the current Mac architecture.
The generated binary is ignored by Git.

### 3. Configure completed-turn notifications

Open `~/.codex/config.toml` and add the following entry. TOML does not expand
`~` or `$HOME`, so use the real absolute path to your home directory:

```toml
notify = ["/usr/bin/python3", "/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py"]
```

Codex supports one global `notify` command. If another application already owns
that setting, configure it to chain this script instead of adding a second
`notify` key.

### 4. Enable mid-turn attention alerts

Add this rule to `~/.codex/AGENTS.md`:

```md
- Before a mid-turn approval, decision, input, or manual-action pause, use `$notify-codex-attention`; the global `notify` callback handles final questions and completed turns.
```

Restart Codex after changing the global configuration.

## Permissions

The primary overlay does not need broad macOS notification access. On first use,
Codex may ask for permission to run the notifier outside its sandbox. Approve
only the narrow command prefix containing both `/usr/bin/python3` and the
absolute path to `scripts/notify.py`.

The optional AppleScript and `terminal-notifier` fallbacks may prompt for their
own macOS permissions.

## Verify the installation

Run the build and deterministic checks:

```sh
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" check
```

Send a live attention alert:

```sh
cd "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention"
/usr/bin/python3 scripts/notify.py \
  --kind attention \
  --message "Please return to Codex" \
  --session-id "manual-test"
```

Click the alert and confirm that iTerm2 becomes active.

Test completion-event routing without displaying an alert:

```sh
/usr/bin/python3 scripts/notify.py \
  '{"type":"agent-turn-complete","thread-id":"manual-test","last-assistant-message":"Task complete."}' \
  --dry-run
```

The resolved subtitle should be `任务已完成` and the selected backend should be
`overlay`.

## Update

```sh
git -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" pull --ff-only
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" build
```

## Uninstall

Remove the `notify` entry from `~/.codex/config.toml`, remove the matching rule
from `~/.codex/AGENTS.md`, and then delete the cloned skill directory.

## Repository layout

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── codex_attention_overlay.swift
│   └── notify.py
└── Makefile
```

## Development

```sh
make build   # compile the AppKit overlay
make check   # compile, check Python syntax, and run a dry-run route test
make clean   # remove generated local artifacts
```
