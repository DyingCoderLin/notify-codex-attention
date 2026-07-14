from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import notify  # noqa: E402


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
