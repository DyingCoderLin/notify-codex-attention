from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from event_queue import EventQueue
import notify
from install_hooks import merged_hooks


def stop(session='s1', turn='t1'):
    return dict(hook_event_name='Stop', session_id=session, turn_id=turn, last_assistant_message='done', cwd='/work/project')


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.q = EventQueue(self.temp.name)

    def tearDown(self):
        self.q.db.close()
        self.temp.cleanup()

    def ingest(self, event):
        details = notify.legacy_event_details(event) if 'type' in event else notify.hook_event_details(event)
        return self.q.ingest(event, details)

    def test_stop_and_legacy_callback_deduplicate(self):
        self.assertTrue(self.ingest(stop()))
        self.assertFalse(self.ingest({'type':'agent-turn-complete', 'thread-id':'s1', 'turn-id':'t1', 'last-assistant-message':'done'}))
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM events').fetchone()[0], 1)

    def test_reverse_order_also_deduplicates(self):
        self.assertTrue(self.ingest({'type':'agent-turn-complete', 'thread-id':'s1', 'turn-id':'t1', 'last-assistant-message':'done'}))
        self.assertFalse(self.ingest(stop()))

    def test_parallel_sessions_same_turn_do_not_overwrite(self):
        self.ingest(stop())
        self.ingest(stop('s2'))
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM events').fetchone()[0], 2)
        payload = json.loads(self.q.next_event()['payload'])
        self.assertIn('project · s1', payload['message'])

    def test_new_turn_cancels_only_its_session_and_rejects_stale_stop(self):
        self.ingest(stop())
        self.ingest(stop('s2'))
        self.ingest(dict(hook_event_name='UserPromptSubmit',session_id='s1',turn_id='t2'))
        self.assertFalse(self.ingest(stop()))
        self.assertEqual(self.q.next_event()['session'], 's2')
        self.assertTrue(self.ingest(stop(turn='t2')))

    def test_duplicate_prompt_does_not_cancel_current_turn(self):
        prompt = dict(hook_event_name='UserPromptSubmit',session_id='s1',turn_id='t1')
        self.ingest(prompt)
        self.ingest(stop())
        self.ingest(prompt)
        self.assertIsNotNone(self.q.next_event())

    def test_input_return_cancels_sync_but_not_async(self):
        for tool in ('request_user_input', 'functions.request_user_input_async'):
            event = dict(hook_event_name='PreToolUse', session_id=tool,turn_id='t1', tool_use_id='call', tool_name=tool, tool_input={'questions':[{'title':'Which option?'}]})
            self.assertTrue(self.ingest(event))
            self.ingest(dict(event,hook_event_name='PostToolUse'))
            status = self.q.db.execute('SELECT status FROM events WHERE session=?',(tool,)).fetchone()[0]
            self.assertEqual(status, 'pending' if tool.endswith('async') else 'cancelled')

    def test_permission_return_cancels_and_repeat_request_can_notify(self):
        event = dict(hook_event_name='PermissionRequest',session_id='s1',turn_id='t1',tool_name='Bash',tool_input={'command':'true','description':'approve'})
        self.assertTrue(self.ingest(event))
        self.assertFalse(self.ingest(event))
        self.ingest(dict(event,hook_event_name='PostToolUse',tool_use_id='call1'))
        self.assertIsNone(self.q.next_event())
        self.assertTrue(self.ingest(event))

    def test_multiple_approvals_in_one_turn(self):
        for command in ('one','two'):
            self.assertTrue(self.ingest(dict(hook_event_name='PermissionRequest',session_id='s1',turn_id='t1',tool_name='Bash',tool_input={'command':command})))
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM events').fetchone()[0], 2)

    def test_interrupt_cancels_showing_event(self):
        self.ingest(stop())
        key = self.q.next_event()['key']
        self.q.finish(key, 'showing')
        self.ingest(dict(hook_event_name='Interrupt',session_id='s1',turn_id='t1'))
        self.assertEqual(self.q.status(key), 'cancelled')
        self.q.finish(key, 'delivered')
        self.assertEqual(self.q.status(key), 'cancelled')

    def test_completion_cancels_pending_questions(self):
        self.ingest(dict(hook_event_name='PermissionRequest',session_id='s1',turn_id='t1'))
        self.ingest(stop())
        self.assertEqual(self.q.next_event()['category'],'complete')

    def test_blank_missing_identity_and_unrelated_events_ignored(self):
        with patch.dict('os.environ', {'CODEX_THREAD_ID':''}):
            for event in (dict(stop(),last_assistant_message=' '),dict(stop(),session_id=None),dict(stop(),turn_id=None),dict(stop(),hook_event_name='SubagentStop'),dict(stop(),hook_event_name='SessionStart')):
                self.assertFalse(self.ingest(event))
        self.assertIsNone(self.q.next_event())

    def test_keywords_never_infer_approval(self):
        for text in ('permission checks passed', '是否匹配已确认', 'choose() test passed', 'yes/no parser fixed?'):
            self.assertEqual(notify.legacy_event_details({'type':'agent-turn-complete','last-assistant-message':text})[0], 'complete')

    def test_state_survives_reopen(self):
        self.ingest(stop())
        other = EventQueue(self.temp.name)
        try:
            self.assertFalse(other.ingest(stop(),notify.hook_event_details(stop())))
            self.assertEqual(other.next_event()['session'],'s1')
        finally:
            other.db.close()

    def test_concurrent_producers_exactly_once_per_identity(self):
        def produce(i):
            q = EventQueue(self.temp.name)
            try:
                event = stop('s'+str(i % 4))
                return q.ingest(event,notify.hook_event_details(event))
            finally:
                q.db.close()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(produce, range(32)))
        self.assertEqual(sum(results),4)

    def test_failed_delivery_can_be_seen(self):
        self.ingest(stop())
        key = self.q.next_event()['key']
        self.q.finish(key,'failed')
        self.assertEqual(self.q.status(key),'failed')


class InstallTests(unittest.TestCase):
    def test_idempotent_and_preserves_other_hooks(self):
        other = {'hooks':[{'type':'command','command':'unrelated'}]}
        original = {'hooks':{'Stop':[other]},'description':'keep'}
        merged = merged_hooks(original,Path('/skill/notify.py'))
        self.assertEqual(merged,merged_hooks(merged,Path('/skill/notify.py')))
        self.assertEqual(merged['hooks']['Stop'][0],other)
        self.assertEqual(original,{'hooks':{'Stop':[other]},'description':'keep'})

class WorkerTests(unittest.TestCase):
    def test_workers_serialize_actual_children_and_skip_cancelled_events(self):
        with tempfile.TemporaryDirectory() as directory:
            q = EventQueue(directory)
            for session in ('a','b','cancelled'):
                event = stop(session)
                q.ingest(event,notify.hook_event_details(event))
            q.ingest(dict(hook_event_name='SessionEnd',session_id='cancelled'),None)
            with q.db:
                q.db.execute('UPDATE events SET ready=0')
            q.db.close()
            log = Path(directory) / 'children.log'
            script = ('import sys,time; f=open(sys.argv[1],"a"); '
                      'f.write("start "+sys.argv[2]+"\\n"); f.flush(); '
                      'time.sleep(.15); f.write("end "+sys.argv[2]+"\\n"); f.close()')
            def commands(kind,message,session,bundle):
                return [('overlay',[sys.executable,'-c',script,str(log),session])]
            with patch.object(notify,'EventQueue',side_effect=lambda:EventQueue(directory)), patch.object(notify,'notification_commands',side_effect=commands):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    self.assertEqual(list(pool.map(lambda _:notify.drain_queue(),range(2))),[0,0])
            self.assertEqual(log.read_text().splitlines(),['start a','end a','start b','end b'])

    def test_hook_protocol_errors_never_block_codex(self):
        import subprocess
        result = subprocess.run([sys.executable,str(Path(notify.__file__)),'--hook'],input='{bad json',text=True,capture_output=True)
        self.assertEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout),{})


if __name__ == '__main__':
    unittest.main()
