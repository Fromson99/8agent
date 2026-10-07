#!/usr/bin/env python3
"""Apply the pinned GENOS uniqueItems compatibility patch to a matching checkout."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / 'PATCH_PLAN.json').read_text(encoding='utf-8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_file(path, data):
    tmp = path.with_name('.' + path.name + '.uniqueitems-tmp')
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def prepare(root):
    changes = {**PLAN['code'], **PLAN['manifests']}
    paths = list(changes) + ['00_SYSTEM/PIPELINE.json']
    before = {name: (root / name).read_bytes() for name in paths}
    states = {name: 'old' if sha(before[name]) == pin['old'] else
              'new' if sha(before[name]) == pin['new'] else 'different'
              for name, pin in changes.items()}
    if 'different' in states.values() or len(set(states.values())) != 1:
        raise ValueError('code/manifest versions do not match one complete patch state: ' + str(states))
    state = next(iter(states.values()))
    for name, pin in PLAN['code'].items():
        payload = (HERE / 'payload' / name).read_bytes()
        if sha(payload) != pin['new']:
            raise ValueError('patch payload hash mismatch: ' + name)
    pipeline = json.loads(before['00_SYSTEM/PIPELINE.json'])
    affected = {entry['manifest']: entry['sha256'] for entry in pipeline['engines'].values()
                if entry['manifest'] in PLAN['manifests']}
    if set(affected) != set(PLAN['manifests']):
        raise ValueError('pipeline engine set does not match this patch')
    for name, digest in affected.items():
        if digest != PLAN['manifests'][name][state]:
            raise ValueError('pipeline manifest pin mismatch: ' + name)
    if state == 'new':
        return state, before, None
    after = {name: (HERE / 'payload' / name).read_bytes() for name in PLAN['code']}
    for name, pin in PLAN['manifests'].items():
        updated_manifest = before[name].decode('utf-8')
        for code_pin in PLAN['code'].values():
            if code_pin['old'] not in updated_manifest:
                raise ValueError('missing manifest code pin: ' + name)
            updated_manifest = updated_manifest.replace(code_pin['old'], code_pin['new'])
        after[name] = updated_manifest.encode('utf-8')
        if sha(after[name]) != pin['new']:
            raise ValueError('manifest patch hash mismatch: ' + name)
    updated = before['00_SYSTEM/PIPELINE.json'].decode('utf-8')
    for name, pin in PLAN['manifests'].items():
        old, new = '"' + pin['old'] + '"', '"' + pin['new'] + '"'
        if old not in updated:
            raise ValueError('missing pipeline pin: ' + name)
        updated = updated.replace(old, new)
    updated_bytes = updated.encode('utf-8')
    check = json.loads(updated)
    if any(entry['sha256'] != PLAN['manifests'][entry['manifest']]['new']
           for entry in check['engines'].values() if entry['manifest'] in PLAN['manifests']):
        raise ValueError('pipeline replacement failed')
    after['00_SYSTEM/PIPELINE.json'] = updated_bytes
    return state, before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        state, before, after = prepare(root)
        if state == 'new':
            print('ALREADY_APPLIED: code, manifests and pipeline pins match')
            return 0
        if not args.apply:
            print('READY: baseline hashes match; rerun with --apply')
            return 0
        backup = root / 'TRANSFER' / ('uniqueitems-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        if backup.exists():
            raise ValueError('backup directory already exists: ' + str(backup))
        for name, data in before.items():
            dest = backup / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        try:
            for name, data in after.items():
                replace_file(root / name, data)
            after_state, _, _ = prepare(root)
            if after_state != 'new':
                raise ValueError('post-install pin check failed')
        except Exception:
            for name, data in before.items():
                replace_file(root / name, data)
            raise
        print('APPLIED: model schema compatibility patch')
        print('BACKUP:', backup)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print('NOT_APPLIED:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
