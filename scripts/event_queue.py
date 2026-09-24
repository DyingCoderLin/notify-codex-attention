"""Local event identity, cancellation and serialized delivery (no transcript access)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

INPUT_TOOLS = {'request_user_input', 'request_user_input_async'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def input_tool(event):
    return str(event.get('tool_name', '')).rsplit('.', 1)[-1] in INPUT_TOOLS


class EventQueue:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ.get('CODEX_ATTENTION_STATE_DIR', str(Path.home() / '.codex' / 'state' / 'attention')))
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(self.directory / 'events.sqlite3'), timeout=3)
        os.chmod(self.directory / 'events.sqlite3', 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS turns(session TEXT PRIMARY KEY, turn TEXT);
        CREATE TABLE IF NOT EXISTS events(
          key TEXT PRIMARY KEY, session TEXT, turn TEXT, category TEXT,
          call_id TEXT, payload TEXT, status TEXT, created REAL, ready REAL,
          attempts INTEGER DEFAULT 0);
        ''')

    def ingest(self, event, details, bundle=None, now=None):
        now = time.time() if now is None else now
        session = event.get('session_id') or event.get('thread-id') or os.environ.get('CODEX_THREAD_ID')
        turn = event.get('turn_id') or event.get('turn-id')
        name = event.get('hook_event_name', '')
        # Never merge unknown sessions into one shared "current" notification.
        if not session:
            return False
        with self.db:
            self.db.execute('DELETE FROM events WHERE created < ?', (now - 7 * 86400,))
            if name == 'UserPromptSubmit':
                if not turn:
                    return False
                previous = self.db.execute('SELECT turn FROM turns WHERE session=?', (session,)).fetchone()
                if not previous or previous['turn'] != turn:
                    self.db.execute("UPDATE events SET status='cancelled' WHERE session=? AND status IN ('pending','showing')", (session,))
                self.db.execute('INSERT OR REPLACE INTO turns VALUES (?,?)', (session, turn))
                return False
            if name in ('Interrupt', 'SessionEnd'):
                self.db.execute("UPDATE events SET status='cancelled' WHERE session=? AND (? IS NULL OR turn=?) AND status IN ('pending','showing')", (session, turn, turn))
                return False
            if name == 'PostToolUse':
                # Synchronous input returned: the user already answered. Async input
                # returns immediately, so its PostToolUse is not an acknowledgement.
                category = 'input' if input_tool(event) else 'permission'
                if str(event.get('tool_name', '')).endswith('request_user_input_async'):
                    return False
                call_id = event.get('tool_use_id') or digest([event.get('tool_name'), event.get('tool_input')])
                self.db.execute("UPDATE events SET status='cancelled' WHERE session=? AND turn=? AND category=? AND call_id=? AND status IN ('pending','showing')", (session, turn, category, call_id))
                # PermissionRequest may omit tool_use_id even when PostToolUse has it.
                if category == 'permission':
                    self.db.execute("UPDATE events SET status='cancelled' WHERE session=? AND turn=? AND category=? AND call_id=? AND status IN ('pending','showing')", (session, turn, category, digest([event.get('tool_name'), event.get('tool_input')])))
                return False
            if details is None:
                return False
            kind, message, _ = details
            category = 'complete' if name == 'Stop' or event.get('type') == 'agent-turn-complete' else ('input' if input_tool(event) else 'permission' if name == 'PermissionRequest' else 'manual')
            if category != 'manual' and not turn:
                # Structured notifications must carry actual turn identity.
                return False
            current = self.db.execute('SELECT turn FROM turns WHERE session=?', (session,)).fetchone()
            if current and turn and current['turn'] != turn:
                return False
            call_id = event.get('tool_use_id') or digest([event.get('tool_name'), event.get('tool_input')])
            identity = 'complete' if category == 'complete' else call_id if category in ('input', 'permission') else str(uuid.uuid4())
            key = digest([session, turn, category, identity])
            if category == 'complete':
                self.db.execute("UPDATE events SET status='cancelled' WHERE session=? AND turn=? AND category!='complete' AND status IN ('pending','showing')", (session, turn))
            project = Path(str(event.get('cwd') or os.getcwd())).name
            label = f'{project} · {str(session)[:8]}'
            payload = json.dumps({'kind': kind, 'message': f'[{label}] {message}', 'session': session, 'bundle': bundle}, ensure_ascii=False)
            # A small settling delay lets quick approvals/answers and continued Stop
            # turns cancel obsolete alerts before they reach the screen.
            delay = 2 if category == 'complete' else 1
            if category in ('permission', 'input'):
                self.db.execute("DELETE FROM events WHERE key=? AND status='cancelled'", (key,))
            cursor = self.db.execute("INSERT OR IGNORE INTO events(key,session,turn,category,call_id,payload,status,created,ready) VALUES (?,?,?,?,?,?,'pending',?,?)", (key, session, turn, category, call_id, payload, now, now + delay))
            return cursor.rowcount == 1

    def next_event(self):
        return self.db.execute("SELECT * FROM events WHERE status='pending' ORDER BY created, rowid LIMIT 1").fetchone()

    def status(self, key):
        row = self.db.execute('SELECT status FROM events WHERE key=?', (key,)).fetchone()
        return row['status'] if row else 'cancelled'

    def finish(self, key, status):
        with self.db:
            self.db.execute("UPDATE events SET status=? WHERE key=? AND status!='cancelled'", (status, key))
