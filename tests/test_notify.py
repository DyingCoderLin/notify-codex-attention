from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import notify  # noqa: E402


class ApplicationRoutingTests(unittest.TestCase):
    def test_inherited_bundle_identifies_supported_hosts(self) -> None:
        bundles = (
            "com.googlecode.iterm2",
            "com.todesktop.230313mzl4w4u92",
            "com.microsoft.VSCode",
            "com.mitchellh.ghostty",
            "com.apple.Terminal",
        )
        for bundle_id in bundles:
            with self.subTest(bundle_id=bundle_id):
                self.assertEqual(
                    notify.source_application_bundle_id(
                        {"__CFBundleIdentifier": bundle_id}
                    ),
                    bundle_id,
                )

    def test_helper_bundle_is_normalized_to_host_application(self) -> None:
        self.assertEqual(
            notify.source_application_bundle_id(
                {"__CFBundleIdentifier": "com.microsoft.VSCode.helper"}
            ),
            "com.microsoft.VSCode",
        )

    def test_cursor_is_distinguished_from_vscode_without_bundle_env(self) -> None:
        cursor_env = {
            "TERM_PROGRAM": "vscode",
            "VSCODE_GIT_ASKPASS_NODE": "/Applications/Cursor.app/Contents/MacOS/Cursor",
        }
        self.assertEqual(
            notify.source_application_bundle_id(cursor_env),
            "com.todesktop.230313mzl4w4u92",
        )
        self.assertEqual(
            notify.source_application_bundle_id({"TERM_PROGRAM": "vscode"}),
            "com.microsoft.VSCode",
        )

    def test_term_program_fallbacks_cover_iterm_and_ghostty(self) -> None:
        self.assertEqual(
            notify.source_application_bundle_id({"TERM_PROGRAM": "iTerm.app"}),
            "com.googlecode.iterm2",
        )
        self.assertEqual(
            notify.source_application_bundle_id({"TERM_PROGRAM": "ghostty"}),
            "com.mitchellh.ghostty",
        )

    def test_explicit_override_wins(self) -> None:
        self.assertEqual(
            notify.source_application_bundle_id(
                {"__CFBundleIdentifier": "com.googlecode.iterm2"},
                override="com.todesktop.230313mzl4w4u92",
            ),
            "com.todesktop.230313mzl4w4u92",
        )

    def test_unknown_host_does_not_guess_recent_application(self) -> None:
        self.assertIsNone(notify.source_application_bundle_id({}))

    def test_resolved_bundle_is_frozen_into_overlay_command(self) -> None:
        bundle_id = "com.todesktop.230313mzl4w4u92"
        attempts = notify.notification_commands(
            "attention", "Choose", "bundle-test", bundle_id
        )
        backend, command = attempts[0]
        self.assertEqual(backend, "overlay")
        index = command.index("--activate")
        self.assertEqual(command[index + 1], bundle_id)


class EventRoutingTests(unittest.TestCase):
    def test_permission_request_needs_attention(self) -> None:
        event = {
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"description": "请批准运行测试命令"},
            "session_id": "permission-test",
        }
        self.assertEqual(
            notify.hook_event_details(event),
            ("attention", "请批准运行测试命令", "permission-test"),
        )

    def test_unrelated_hooks_do_not_notify(self) -> None:
        for event_name in ("PreToolUse", "PostToolUse", "Stop", "SessionStart"):
            with self.subTest(event_name=event_name):
                self.assertIsNone(
                    notify.hook_event_details({"hook_event_name": event_name})
                )

    def test_final_choice_needs_attention(self) -> None:
        event = {
            "type": "agent-turn-complete",
            "thread-id": "choice-test",
            "last-assistant-message": "请选择方案 A 或方案 B？",
        }
        self.assertEqual(
            notify.legacy_event_details(event),
            ("attention", "请选择方案 A 或方案 B？", "choice-test"),
        )

    def test_completed_turn_is_complete(self) -> None:
        event = {
            "type": "agent-turn-complete",
            "thread-id": "complete-test",
            "last-assistant-message": "文件修改已经完成。",
        }
        self.assertEqual(
            notify.legacy_event_details(event),
            ("complete", "文件修改已经完成。", "complete-test"),
        )

    def test_unrelated_notify_payload_is_ignored(self) -> None:
        self.assertIsNone(notify.legacy_event_details({"type": "tool-complete"}))


if __name__ == "__main__":
    unittest.main()
