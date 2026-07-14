#!/usr/bin/env python3
"""Post clickable macOS notifications for Codex lifecycle hooks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping


TITLE = "Codex"
MAX_MESSAGE_LENGTH = 160
OVERLAY = Path(__file__).with_name("codex-attention-overlay")
CURSOR_BUNDLE_ID = "com.todesktop.230313mzl4w4u92"
TERMINAL_BUNDLE_IDS = {
    "apple_terminal": "com.apple.Terminal",
    "cursor": CURSOR_BUNDLE_ID,
    "ghostty": "com.mitchellh.ghostty",
    "iterm.app": "com.googlecode.iterm2",
    "vscode": "com.microsoft.VSCode",
}
SUBTITLES = {
    "complete": "任务已完成",
    "attention": "需要你处理",
}
ATTENTION_PATTERNS = (
    r"[?？]\s*$",
    r"(?:请|需要你|麻烦你).{0,24}(?:选择|确认|决定|点击|输入|回复|批准|允许)",
    r"(?:是否|要不要|可以吗|同意吗|yes\s*/?\s*no)",
    r"(?:choose|select|confirm|approve|allow|permission|your input|required action)",
)
ICON_CANDIDATES = (
    "/Applications/ChatGPT.app/Contents/Resources/icon-codex-dark-color.png",
    "/Applications/ChatGPT.app/Contents/Resources/icon-codex-light.png",
    "/Applications/Codex.app/Contents/Resources/icon-codex-dark-color.png",
    "/Applications/Codex.app/Contents/Resources/app.icns",
)


def clean_message(value: Any, fallback: str) -> str:
    text = str(value or "")
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"^[\s>#*+\-\d.]+", "", text, flags=re.MULTILINE)
    text = text.replace("`", "").replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = fallback
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…"
    return text


def needs_attention(message: str) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in ATTENTION_PATTERNS)


def icon_path() -> Path | None:
    for candidate in ICON_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path.resolve()
    return None


def icon_url() -> str | None:
    path = icon_path()
    return path.as_uri() if path else None


def valid_bundle_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value))


def canonical_terminal_bundle_id(value: str) -> str | None:
    if not valid_bundle_id(value):
        return None
    for bundle_id in TERMINAL_BUNDLE_IDS.values():
        if value == bundle_id or value.startswith(bundle_id + "."):
            return bundle_id
    return value


def source_application_bundle_id(
    environment: Mapping[str, str] | None = None,
    override: str | None = None,
) -> str | None:
    env = environment if environment is not None else os.environ

    if override:
        return canonical_terminal_bundle_id(override)

    explicit = env.get("CODEX_ATTENTION_BUNDLE_ID", "").strip()
    if explicit and (bundle_id := canonical_terminal_bundle_id(explicit)):
        return bundle_id

    inherited = env.get("__CFBundleIdentifier", "").strip()
    if inherited and (bundle_id := canonical_terminal_bundle_id(inherited)):
        return bundle_id

    term_program_raw = env.get("TERM_PROGRAM", "").strip()
    term_program = term_program_raw.casefold()
    if term_program == "vscode":
        cursor_environment = any(
            (key.startswith("CURSOR_") and bool(value))
            or (key.startswith("VSCODE_") and "cursor.app" in value.casefold())
            for key, value in env.items()
        )
        return CURSOR_BUNDLE_ID if cursor_environment else TERMINAL_BUNDLE_IDS["vscode"]

    if term_program in TERMINAL_BUNDLE_IDS:
        return TERMINAL_BUNDLE_IDS[term_program]
    return canonical_terminal_bundle_id(term_program_raw)


def notification_commands(
    kind: str,
    message: str,
    session_id: str | None,
    activate_bundle: str | None = None,
) -> list[tuple[str, list[str]]]:
    group_id = re.sub(r"[^0-9A-Za-z_-]", "-", session_id or "current")[:80]
    group = f"codex-attention-{group_id}"
    attempts: list[tuple[str, list[str]]] = []

    if OVERLAY.is_file() and os.access(OVERLAY, os.X_OK):
        command = [
            str(OVERLAY),
            "--title",
            TITLE,
            "--subtitle",
            SUBTITLES[kind],
            "--message",
            message,
            "--group",
            group,
            "--timeout",
            "18",
        ]
        if activate_bundle:
            command.extend(["--activate", activate_bundle])
        if (path := icon_path()) is not None:
            command.extend(["--icon", str(path)])
        attempts.append(("overlay", command))

    executable = shutil.which("terminal-notifier")
    if not executable and Path("/opt/homebrew/bin/terminal-notifier").is_file():
        executable = "/opt/homebrew/bin/terminal-notifier"
    if executable:
        command = [
            executable,
            "-title",
            TITLE,
            "-subtitle",
            SUBTITLES[kind],
            "-message",
            message,
            "-group",
            group,
            "-ignoreDnD",
        ]
        if activate_bundle:
            command.extend(["-activate", activate_bundle])
        if (icon := icon_url()) is not None:
            command.extend(["-appIcon", icon])
        attempts.append(("terminal-notifier", command))

    apple_script = (
        "on run argv\n"
        "display notification (item 3 of argv) with title (item 1 of argv) "
        "subtitle (item 2 of argv)\n"
        "end run"
    )
    attempts.append(("applescript", [
        "/usr/bin/osascript",
        "-e",
        apple_script,
        "--",
        TITLE,
        SUBTITLES[kind],
        message,
    ]))
    return attempts


def deliver_notification(
    kind: str,
    message: str,
    session_id: str | None,
    activate_bundle: str | None,
) -> tuple[bool, str | None, list[str]]:
    errors: list[str] = []
    for backend, command in notification_commands(kind, message, session_id, activate_bundle):
        if backend == "overlay":
            try:
                subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True, backend, errors
            except OSError as exc:
                errors.append(f"{backend}: {exc}")
                continue
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{backend}: {exc}")
            continue

        output = "\n".join(part for part in (result.stderr, result.stdout) if part).strip()
        connection_failed = backend == "applescript" and re.search(
            r"connection (?:invalid|to notification center invalid)|ServerConnectionFailure",
            output,
            flags=re.IGNORECASE,
        )
        if result.returncode == 0 and not connection_failed:
            return True, backend, errors
        errors.append(f"{backend}: {output or f'exit {result.returncode}'}")
    return False, None, errors


def permission_request_details(event: dict[str, Any]) -> tuple[str, str, str | None]:
    tool_name = str(event.get("tool_name") or "tool")
    tool_input = event.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    description = tool_input.get("description")

    fallbacks = {
        "Bash": "需要批准 Codex 执行命令",
        "apply_patch": "需要批准 Codex 修改文件",
    }
    fallback = fallbacks.get(tool_name, f"需要批准 Codex 使用工具 {tool_name}")
    return "attention", clean_message(description, fallback), event.get("session_id")


def hook_event_details(event: dict[str, Any]) -> tuple[str, str, str | None] | None:
    event_name = event.get("hook_event_name")
    if event_name == "PermissionRequest":
        return permission_request_details(event)
    return None


def legacy_event_details(event: dict[str, Any]) -> tuple[str, str, str | None] | None:
    if event.get("type") != "agent-turn-complete":
        return None
    message = clean_message(event.get("last-assistant-message"), "Codex 已完成当前任务")
    kind = "attention" if needs_attention(message) else "complete"
    return kind, message, event.get("thread-id")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", nargs="?", help="Legacy Codex notify JSON payload")
    parser.add_argument("--hook", action="store_true", help="Read a Codex lifecycle-hook event from stdin")
    parser.add_argument("--kind", choices=tuple(SUBTITLES), default="attention")
    parser.add_argument("--message", help="Short user-facing task summary")
    parser.add_argument("--session-id", help="Identifier used to replace duplicate session alerts")
    parser.add_argument("--activate-bundle", help="Override the originating macOS application bundle ID")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved notification without sending")
    return parser.parse_args(argv)


def load_json(raw: str, source: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"notify-codex-attention: invalid {source} JSON: {exc}", file=sys.stderr)
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    hook_mode = args.hook
    details: tuple[str, str, str | None] | None = None

    if hook_mode:
        event = load_json(sys.stdin.read(), "hook")
        details = hook_event_details(event) if event else None
    elif args.payload:
        event = load_json(args.payload, "notify")
        details = legacy_event_details(event) if event else None
    else:
        fallback = "Codex 需要你返回处理当前任务" if args.kind == "attention" else "Codex 已完成当前任务"
        details = (args.kind, clean_message(args.message, fallback), args.session_id or os.environ.get("CODEX_THREAD_ID"))

    if details is None:
        if hook_mode:
            print("{}")
        return 0

    kind, message, session_id = details
    message = clean_message(message, "Codex 需要你处理当前任务" if kind == "attention" else "Codex 已完成当前任务")
    activate_bundle = source_application_bundle_id(override=args.activate_bundle)
    attempts = notification_commands(
        kind,
        message,
        str(session_id) if session_id else None,
        activate_bundle,
    )

    if args.dry_run:
        print(json.dumps({
            "backend": attempts[0][0],
            "title": TITLE,
            "subtitle": SUBTITLES[kind],
            "message": message,
            "activate": activate_bundle,
            "command": attempts[0][1],
            "fallbacks": [name for name, _ in attempts[1:]],
        }, ensure_ascii=False, indent=2))
        return 0

    delivered, _, errors = deliver_notification(
        kind,
        message,
        str(session_id) if session_id else None,
        activate_bundle,
    )
    if not delivered:
        print("notify-codex-attention: " + "; ".join(errors), file=sys.stderr)

    if hook_mode:
        print("{}")
        return 0
    return 0 if delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())
