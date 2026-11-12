#!/usr/bin/env python3
"""Stage named code changes, alone or together, on the selected MAIN.

A code change lives in 09_ARTIFACTS/CODE_CHANGES/<name>/: change.json, src/ (whole replacement files)
and diff.patch. Each one is written against a MAIN release, so any subset can be staged:

  .venv/bin/python 06_TOOLS/maintenance/code_change.py stage --out OUT named-article-hyphen search-group-relax
  .venv/bin/python 06_TOOLS/maintenance/code_change.py stage --out OUT named-article-hyphen   # one change alone

Two changes that replace the same file cannot be combined here: make a new change holding the merged
file. A change whose base file differs from the selected MAIN must be rebased the same way.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHANGES = ROOT/'09_ARTIFACTS/CODE_CHANGES'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message):
    sys.exit('code_change: '+message)


def load(names):
    active = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text(encoding='utf-8'))
    code = ROOT/'08_DEPLOYMENT/RELEASES'/active['release_id']/'code'
    owners, changes = {}, []
    for name in names:
        folder = CHANGES/name
        if not (folder/'change.json').is_file():
            fail(f'no change named {name} in {CHANGES.relative_to(ROOT)}')
        change = json.loads((folder/'change.json').read_text(encoding='utf-8'))
        for row in change['files']:
            if row['path'] in owners:
                fail(f"{name} and {owners[row['path']]} both replace {row['path']}: make a new change holding the merged file")
            owners[row['path']] = name
            source = folder/'src'/pathlib.PurePath(row['path']).name
            if sha256(source) != row['sha256']:
                fail(f'{source.relative_to(ROOT)} changed after the change was recorded')
            base = code/row['path']
            if base.is_file() and sha256(base) != row['base_sha256']:
                fail(f"{row['path']} differs from {active['release_id']}: {name} needs a rebased change")
        changes.append({**change, 'folder': folder})
    return active, changes


def stage(args):
    active, changes = load(args.changes)
    command = [sys.executable, str(ROOT/'06_TOOLS/maintenance/main_release.py'), 'stage', '--out', args.out, '--name', args.name]
    if any(c.get('sql_change') for c in changes):
        command.append('--allow-sql-change')
    for change in changes:
        for row in change['files']:
            source = change['folder']/'src'/pathlib.PurePath(row['path']).name
            command += ['--product', row['path']+'='+str(source.relative_to(ROOT))]
    tests = list(dict.fromkeys(t for c in changes for t in c.get('tests', [])))
    if args.dry_run:
        print(' '.join(command))
        print('\n'.join(tests))
        return
    if subprocess.call(command, cwd=ROOT):
        fail('main_release stage failed')
    out = ROOT/args.out
    (out/(args.name+'-changes.json')).write_text(json.dumps({'base_release': active['release_id'], 'changes': args.changes},
                                                            ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out/(args.name+'-tests.txt')).write_text('\n'.join(tests)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('stage')
    command.add_argument('--out', required=True)
    command.add_argument('--name', default='staged')
    command.add_argument('--dry-run', action='store_true')
    command.add_argument('changes', nargs='+')
    stage(parser.parse_args())


if __name__ == '__main__':
    main()
