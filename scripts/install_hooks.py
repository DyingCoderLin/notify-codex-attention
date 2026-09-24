#!/usr/bin/env python3
"""Merge notification hooks without replacing unrelated hooks or trust state."""
import argparse
import json
from pathlib import Path
import os
import tempfile
import time

EVENTS = {
    'PermissionRequest': None,
    'PreToolUse': r'(^|\.)request_user_input(_async)?$',
    'PostToolUse': None,
    'UserPromptSubmit': None,
    'Stop': None,
    'Interrupt': None,
    'SessionEnd': None,
}


def merged_hooks(value, script):
    value = json.loads(json.dumps(value))
    command = f'/usr/bin/python3 "{script}" --hook'
    for event, matcher in EVENTS.items():
        groups = value.setdefault('hooks', {}).setdefault(event, [])
        for group in groups:
            group['hooks'] = [h for h in group.get('hooks', []) if h.get('command') != command]
        groups[:] = [g for g in groups if g.get('hooks')]
        group = {'hooks': [{'type': 'command', 'command': command, 'timeout': 10,
                            'statusMessage': 'Sending Codex attention notification'}]}
        if event == 'Interrupt':
            group['hooks'][0]['timeout'] = 3
        if matcher:
            group['matcher'] = matcher
        groups.append(group)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = args.codex_home / 'hooks.json'
    raw = target.read_text() if target.exists() else '{}\n'
    result = json.dumps(merged_hooks(json.loads(raw), Path(__file__).with_name('notify.py').resolve()), ensure_ascii=False, indent=2) + '\n'
    if not args.apply:
        print(result, end='')
        return
    if result != raw:
        backup = target.with_name(f'hooks.json.before-attention-{time.time_ns()}')
        backup.write_text(raw)
        backup.chmod(0o600)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.attention-hooks-')
        with os.fdopen(fd, 'w') as file:
            file.write(result)
        os.replace(temporary, target)
        print(f'Backup: {backup}')
    print('Hooks installed. Review/trust new definitions in Codex /hooks, then reopen existing sessions. No trust hashes were changed.')


if __name__ == '__main__':
    main()
