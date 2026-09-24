#!/usr/bin/env python3
"""Post clickable macOS notifications for Codex lifecycle hooks."""

from __future__ import annotations

import argparse
import fcntl
import time
from event_queue import EventQueue, input_tool
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
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
    "complete": "本轮回复已结束",
    "attention": "需要你处理",
}
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
    if event_name == "PreToolUse" and input_tool(event):
        arguments = event.get("tool_input") or {}
        if not isinstance(arguments, dict):
            return None
        questions = arguments.get("questions")
        if not isinstance(questions, list) or not questions:
            return None
        question = questions[0] if isinstance(questions[0], dict) else {}
        return "attention", clean_message(question.get("question") or question.get("title"), "Codex 等待你回答问题"), event.get("session_id")
    if event_name == "Stop":
        message = event.get("last_assistant_message")
        if isinstance(message, str) and message.strip():
            return "complete", clean_message(message, "本轮回复已结束"), event.get("session_id")
    return None


def legacy_event_details(event: dict[str, Any]) -> tuple[str, str, str | None] | None:
    if event.get("type") != "agent-turn-complete":
        return None
    raw = event.get("last-assistant-message")
    if not isinstance(raw, str) or not raw.strip():
        return None
    message = clean_message(raw, "本轮回复已结束")
    return "complete", message, event.get("thread-id")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", nargs="?", help="Legacy Codex notify JSON payload")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
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


def drain_queue() -> int:
    queue = EventQueue()
    # Blocking lock is intentional: a producer racing with the previous worker's
    # exit always gets another drain pass. UI children must not inherit this lock.
    with (queue.directory / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with queue.db:
            queue.db.execute("UPDATE events SET status='pending' WHERE status='showing' AND attempts<2")
            queue.db.execute("UPDATE events SET status='failed' WHERE status='showing'")
        while True:
            row = queue.next_event()
            if row is None:
                break
            if row['ready'] > time.time():
                time.sleep(min(.2, row['ready'] - time.time()))
                continue
            with queue.db:
                queue.db.execute("UPDATE events SET status='showing', attempts=attempts+1 WHERE key=? AND status='pending'", (row['key'],))
            payload = json.loads(row['payload'])
            delivered = False
            for backend, command in notification_commands(payload['kind'], payload['message'], payload['session'], payload['bundle']):
                if queue.status(row['key']) == 'cancelled':
                    break
                try:
                    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    deadline = time.monotonic() + (22 if backend == 'overlay' else 10)
                    while child.poll() is None:
                        if queue.status(row['key']) == 'cancelled' or time.monotonic() > deadline:
                            child.terminate()
                            try:
                                child.wait(timeout=1)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait()
                            break
                        time.sleep(.1)
                    delivered = child.returncode == 0
                    if delivered:
                        break
                except OSError:
                    continue
            queue.finish(row['key'], 'delivered' if delivered else 'failed')
    queue.db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.worker:
        return drain_queue()
    event = {}
    hook_mode = args.hook
    details: tuple[str, str, str | None] | None = None

    if hook_mode:
        event = load_json(sys.stdin.read(), "hook")
        details = hook_event_details(event) if event else None
    elif args.payload:
        event = load_json(args.payload, "notify")
        details = legacy_event_details(event) if event else None
    else:
        fallback = "Codex 需要你返回处理当前任务" if args.kind == "attention" else "Codex 本轮回复已结束"
        details = (args.kind, clean_message(args.message, fallback), args.session_id or os.environ.get("CODEX_THREAD_ID"))

    if (args.hook or args.payload) and not event:
        if hook_mode:
            print("{}")
        return 0
    activate_bundle = source_application_bundle_id(override=args.activate_bundle)
    if not args.dry_run:
        if not args.hook and not args.payload:
            event = {"session_id": details[2], "cwd": os.getcwd()}
        queue = EventQueue()
        try:
            added = queue.ingest(event or {}, details, activate_bundle)
            if added:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        finally:
            queue.db.close()
        if hook_mode:
            print("{}")
        return 0

    if details is None:
        if hook_mode:
            print("{}")
        return 0

    kind, message, session_id = details
    message = clean_message(message, "Codex 需要你处理当前任务" if kind == "attention" else "Codex 本轮回复已结束")
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

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"notify-codex-attention: {type(exc).__name__}: {exc}", file=sys.stderr)
        if "--hook" in sys.argv:
            print("{}")
        raise SystemExit(0 if "--hook" in sys.argv else 1)
