# notify-codex-attention

Clickable macOS alerts for Codex CLI approvals, decisions, and completed turns
across terminal applications.

Codex can run for a while before it needs you. This skill shows a native-looking
alert in the upper-right corner of the active display, summarizes the action,
and takes you back to the application that launched that Codex CLI when clicked.

## Features

- Alerts when Codex needs approval, a choice, text input, or a manual UI action
- Completion alerts from the global Codex `notify` callback
- No alerts for ordinary tool calls or file writes while a turn is still running
- Click-to-activate the originating terminal application
- Separate **Needs attention** and **Task complete** states
- Replaces older alerts from the same Codex thread
- Native AppKit overlay that does not depend on Notification Center banners
- `terminal-notifier` and AppleScript fallbacks
- No daemon, network service, or Python package dependencies

## How it works

There are three notification paths:

1. Codex's global `notify` callback sends completed turns and final questions to
   `scripts/notify.py`.
2. A `PermissionRequest` hook sends real approval events to the same script.
3. A short global `AGENTS.md` rule tells Codex to invoke the skill before a
   mid-turn choice, requested input, or manual UI action.

The Python script classifies the event and captures the host application's
inherited macOS bundle ID before launching a small AppKit overlay. That target
is frozen into the alert; clicking does not guess from the most recently used
application. The overlay is compiled locally from the included Swift source,
so the repository does not ship an architecture-specific binary.

## Supported terminal hosts

The notifier targets the application that owns the originating Codex CLI. It
does not inspect or activate the frontmost or most recently used application.

| Host | Bundle ID | Detection |
| --- | --- | --- |
| iTerm2 | `com.googlecode.iterm2` | Inherited bundle ID or `TERM_PROGRAM=iTerm.app` |
| Cursor | `com.todesktop.230313mzl4w4u92` | Inherited bundle ID or Cursor-flavored VS Code environment |
| Visual Studio Code | `com.microsoft.VSCode` | Inherited bundle ID or `TERM_PROGRAM=vscode` |
| Ghostty | `com.mitchellh.ghostty` | Inherited bundle ID or `TERM_PROGRAM=ghostty` |
| Apple Terminal | `com.apple.Terminal` | Inherited bundle ID or `TERM_PROGRAM=Apple_Terminal` |
| Other macOS hosts | Host-provided value | Inherited `__CFBundleIdentifier` |

The captured bundle ID is frozen into each alert at creation time. Clicking the
alert activates that running application, even if another app becomes active in
the meantime. For a host that does not export usable metadata, pass an explicit
`--activate-bundle com.example.Terminal` override.

## Requirements

- macOS
- Codex CLI
- A macOS terminal application or IDE-integrated terminal
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

This creates `scripts/codex-attention-overlay` for the current Mac architecture.
The generated binary is ignored by Git.

### 3. Configure completed-turn notifications

Open `~/.codex/config.toml` and add the following entry. TOML does not expand
`~` or `$HOME`, so use the real absolute path to your home directory:

```toml
notify = ["/usr/bin/python3", "/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py"]

[tui]
notifications = false
```

Codex supports one global `notify` command. If another application already owns
that setting, configure it to chain this script instead of adding a second
`notify` key. Disabling TUI notifications prevents Codex's built-in terminal
alerts from duplicating the custom overlay; it does not disable the external
`notify` callback or lifecycle hooks.

### 4. Configure approval notifications

Create `~/.codex/hooks.json` with the following content. If that file already
exists, merge the `PermissionRequest` entry into its existing `hooks` object
instead of replacing the file. Replace `/Users/YOU` with your absolute home
directory:

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

Restart Codex, run `/hooks`, and trust the exact hook definition. Codex stores
trust against the hook hash and asks for review again if the definition changes.

### 5. Enable choice and input alerts

Add this rule to `~/.codex/AGENTS.md`:

```md
- Before a mid-turn choice, requested input, or manual UI action, use `$notify-codex-attention`. Do not call it for permission approvals or final responses; the `PermissionRequest` hook and global `notify` callback own those.
```

Restart Codex after changing the global configuration.

## Permissions

The primary overlay does not need broad macOS notification access. Review the
global hook with `/hooks`, and approve only the narrow command prefix containing
both `/usr/bin/python3` and the absolute path to `scripts/notify.py`.

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

Click the alert and confirm that the application containing the originating
Codex CLI becomes active.

Inspect host routing without displaying an alert:

```sh
env __CFBundleIdentifier=com.todesktop.230313mzl4w4u92 \
  /usr/bin/python3 scripts/notify.py \
  --kind attention --message "Cursor route" --dry-run
```

The `activate` field should equal the supplied bundle ID. Use
`--activate-bundle com.example.Terminal` only when a terminal host does not
export usable environment metadata.

Test completion-event routing without displaying an alert:

```sh
/usr/bin/python3 scripts/notify.py \
  '{"type":"agent-turn-complete","thread-id":"manual-test","last-assistant-message":"Task complete."}' \
  --dry-run
```

The resolved subtitle should be `任务已完成` and the selected backend should be
`overlay`.

Test permission-event routing without displaying an alert:

```sh
printf '%s' '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"description":"Approve test command"},"session_id":"manual-test"}' | \
  /usr/bin/python3 scripts/notify.py --hook --dry-run
```

The resolved subtitle should be `需要你处理`. `PreToolUse`, `PostToolUse`,
`Stop`, and unrelated payloads are deliberately ignored by hook mode.

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
make build   # compile the AppKit overlay
make check   # compile, check Python syntax, and run a dry-run route test
make clean   # remove generated local artifacts
```
