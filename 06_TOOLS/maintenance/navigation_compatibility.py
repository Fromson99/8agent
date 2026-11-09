#!/usr/bin/env python3
"""Register serving code versions whose Oracle navigation rows are identical.

Why: the Dataiku loader stores derived navigation rows (structure surfaces,
units, coordinates, members, term labels) and records the hashes of the
navigation compiler files it ran. Serving refuses rows from other compiler
bytes, because lookup keys are digests of normalized text and a different
derivation would make lookups silently empty. Any edit to those files would
then break serving of every existing Oracle publication, even a refactor.

This tool runs the real publisher row functions over the fixed reference
generation with one code version and hashes every produced row (in order).
Versions with the same fingerprint go into one group of
00_SYSTEM/ORACLE/navigation_compatibility.json; serving accepts rows across a
group. The engine preflight fails while the current code is unregistered.

  register --code-root DIR [--publisher-root DIR] --source TEXT [--new-derivation]
      Add DIR's version to the group with the same fingerprint. A new
      fingerprint means existing publications must be republished: refused
      unless --new-derivation is given (it then starts a separate group).
  check --code-root DIR     Fast: is DIR's version registered? (no data read)
  verify --code-root DIR    Recompute DIR's fingerprint and compare with its group.

After editing navigation_match.py, structure_navigation.py or
inherited_navigation.py: run register, then repin the engines.
`verify` also catches changes in other files the publisher uses
(normalization helpers, coordinate parser, row ids) and belongs in releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
REGISTRY = '00_SYSTEM/ORACLE/navigation_compatibility.json'
SCHEMA = 'navigation-compatibility-v1'
MODULES = {
    'semantic_runtime.navigation_match': '02_BACKEND/semantic_runtime/navigation_match.py',
    'semantic_runtime.structure_navigation': '02_BACKEND/semantic_runtime/structure_navigation.py',
    'semantic_runtime.inherited_navigation': '02_BACKEND/semantic_runtime/inherited_navigation.py',
}
PUBLISHER = '02_BACKEND/lawrag/pipeline/oracle_query_navigation_publish.py'
REFERENCE = '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
# Informational: other files the publisher's derivation reads. `verify` covers
# them through the fingerprint; only MODULES are recorded by the loader.
ALSO_USED = ('02_BACKEND/lawrag/core/legal_coordinate.py', '02_BACKEND/semantic_runtime/multi_entry_navigation.py',
             '02_BACKEND/semantic_runtime/oracle_query_catalog.py', '02_BACKEND/semantic_runtime/oracle_dp_io.py',
             '02_BACKEND/semantic_runtime/term_index.py')

# Runs in a separate isolated interpreter: semantic_runtime and lawrag.core
# come from the code version under test, lawrag.pipeline (the publisher) from
# the publisher root. Only row hashes leave the process.
WORKER = r'''
import hashlib, importlib, itertools, json, os, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
generation = Path(sys.argv[2])
from lawrag.pipeline import oracle_query_navigation_publish as P
modules = json.loads(sys.argv[3])
loaded = {}
for name in modules:
    loaded[name] = os.path.realpath(importlib.import_module(name).__file__)
import lawrag.core.legal_coordinate as coordinate
manifest = json.loads((generation/'manifest.json').read_text())
cache = generation/manifest['glossary']['cache']
sections = {
    'structures': lambda: P.structures(str(generation/'store.sqlite')),
    'navigation': lambda: P.navigation(str(generation/'navigation/navigation.sqlite'), str(generation/'store.sqlite')),
    'glossary': lambda: itertools.chain.from_iterable(P.glossary(str(p)) for p in sorted(cache.glob('*.sqlite'))),
}
out = {'files': loaded, 'publisher_file': os.path.realpath(P.__file__),
       'coordinate_file': os.path.realpath(coordinate.__file__), 'sections': {}}
for name, rows in sections.items():
    h = hashlib.sha256(); count = 0; kinds = {}
    for row in rows():
        h.update(row['sha256'].encode()); count += 1; kinds[row['kind']] = kinds.get(row['kind'], 0) + 1
    out['sections'][name] = {'rows': count, 'sha256': h.hexdigest(), 'kinds': dict(sorted(kinds.items()))}
print(json.dumps(out))
'''


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def version(code_root):
    return {name: sha(Path(code_root) / relative) for name, relative in MODULES.items()}


def load(path):
    path = Path(path)
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema_version') != SCHEMA or value.get('modules') != MODULES:
        raise SystemExit(f'INVALID REGISTRY {path}')
    return value


def save(path, value):
    path = Path(path)
    temp = path.with_name('.' + path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def group_of(registry, modules):
    for group in (registry or {}).get('groups', []):
        if any(v['modules'] == modules for v in group['versions']):
            return group
    return None


def fingerprint(code_root, publisher_root, reference):
    code_root, publisher_root = Path(code_root).resolve(), Path(publisher_root).resolve()
    for required in (code_root / '02_BACKEND/semantic_runtime', code_root / '02_BACKEND/lawrag/core',
                     publisher_root / PUBLISHER, reference / 'manifest.json'):
        if not required.exists():
            raise SystemExit(f'MISSING {required}')
    with tempfile.TemporaryDirectory(prefix='navcompat-') as temp:
        backend = Path(temp) / '02_BACKEND'
        (backend / 'lawrag').mkdir(parents=True)
        (backend / 'semantic_runtime').symlink_to(code_root / '02_BACKEND/semantic_runtime', target_is_directory=True)
        shutil.copyfile(code_root / '02_BACKEND/lawrag/__init__.py', backend / 'lawrag/__init__.py')
        (backend / 'lawrag/core').symlink_to(code_root / '02_BACKEND/lawrag/core', target_is_directory=True)
        (backend / 'lawrag/pipeline').symlink_to(publisher_root / '02_BACKEND/lawrag/pipeline', target_is_directory=True)
        run = subprocess.run([sys.executable, '-I', '-B', '-c', WORKER, str(backend), str(reference), json.dumps(list(MODULES))],
                             capture_output=True, text=True, timeout=1800, cwd=temp)
        if run.returncode:
            raise SystemExit('FINGERPRINT FAILED\n' + run.stderr[-4000:])
        result = json.loads(run.stdout.strip().splitlines()[-1])
    # The worker imported through symlinks; confirm it read the intended bytes.
    for name, relative in MODULES.items():
        if sha(result['files'][name]) != sha(code_root / relative):
            raise SystemExit(f'WRONG MODULE LOADED {name}')
    if sha(result['publisher_file']) != sha(publisher_root / PUBLISHER):
        raise SystemExit('WRONG PUBLISHER LOADED')
    if sha(result['coordinate_file']) != sha(code_root / '02_BACKEND/lawrag/core/legal_coordinate.py'):
        raise SystemExit('WRONG COORDINATE PARSER LOADED')
    return hashlib.sha256(canonical(result['sections']).encode()).hexdigest(), result['sections']


def reference_binding(path):
    return {'generation': REFERENCE, 'manifest_sha256': sha(path / 'manifest.json')}


def describe(code_root, publisher_root, source):
    code_root = Path(code_root).resolve()
    try:
        shown = str(code_root.relative_to(REPO))
    except ValueError:
        shown = str(code_root)
    return {'modules': version(code_root), 'source': source, 'code_root': shown,
            'also_used_sha256': {n: sha(code_root / n) for n in ALSO_USED if (code_root / n).is_file()},
            'publisher_sha256': sha(Path(publisher_root) / PUBLISHER),
            'registered_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}


def command_register(args):
    registry_path = Path(args.registry)
    registry = load(registry_path)
    modules = version(args.code_root)
    if group_of(registry, modules):
        print('NAVIGATION_COMPATIBILITY REGISTERED', ','.join(v[:12] for v in modules.values()))
        return 0
    reference = REPO / REFERENCE
    publisher_sha = sha(Path(args.publisher_root) / PUBLISHER)
    if registry is not None:
        if registry['reference'] != reference_binding(reference):
            raise SystemExit('REFERENCE GENERATION CHANGED: fingerprints are only comparable on the recorded reference')
        if registry['publisher']['sha256'] != publisher_sha:
            raise SystemExit('PUBLISHER CHANGED: the loader row format changed; republish and start a new registry')
    value, sections = fingerprint(args.code_root, args.publisher_root, reference)
    entry = describe(args.code_root, args.publisher_root, args.source)
    if registry is None:
        registry = {'schema_version': SCHEMA, 'modules': MODULES,
                    'purpose': ('Serving accepts Oracle navigation rows built by any code version in the same group: '
                                'running the publisher on the reference generation produced identical rows.'),
                    'tool': '06_TOOLS/maintenance/navigation_compatibility.py',
                    'publisher': {'path': PUBLISHER, 'sha256': publisher_sha},
                    'reference': reference_binding(reference), 'groups': []}
    group = next((g for g in registry['groups'] if g['fingerprint'] == value), None)
    if group is None:
        if registry['groups'] and not args.new_derivation:
            print('NAVIGATION_COMPATIBILITY DERIVATION_CHANGED: rows differ from every registered version.')
            print('Existing Oracle publications must be republished with this code before serving it.')
            print('Re-run with --new-derivation only when that republish is planned.')
            for name, row in sections.items():
                print(' ', name, row['rows'], row['sha256'][:16])
            return 3
        group = {'fingerprint': value, 'sections': sections, 'versions': []}
        registry['groups'].append(group)
    group['versions'].append(entry)
    save(registry_path, registry)
    print('NAVIGATION_COMPATIBILITY ADDED', value[:16], ','.join(v[:12] for v in modules.values()), args.source)
    return 0


def command_check(args):
    registry = load(args.registry)
    modules = version(args.code_root)
    if registry and group_of(registry, modules):
        print('NAVIGATION_COMPATIBILITY REGISTERED', ','.join(v[:12] for v in modules.values()))
        return 0
    print('NAVIGATION_COMPATIBILITY UNREGISTERED', ','.join(v[:12] for v in modules.values()))
    print('Run: 06_TOOLS/maintenance/navigation_compatibility.py register --code-root <root> --source "<why>"')
    return 1


def command_verify(args):
    registry = load(args.registry)
    modules = version(args.code_root)
    group = group_of(registry, modules)
    if group is None:
        return command_check(args)
    if registry['publisher']['sha256'] != sha(Path(args.publisher_root) / PUBLISHER):
        raise SystemExit('PUBLISHER CHANGED: verify needs the recorded publisher')
    value, sections = fingerprint(args.code_root, args.publisher_root, REPO / REFERENCE)
    if value != group['fingerprint']:
        print('NAVIGATION_COMPATIBILITY VERIFY_FAILED: rows differ from the registered group although the '
              'compiler files are unchanged (a helper the publisher uses changed).')
        for name, row in sections.items():
            print(' ', name, row['rows'], row['sha256'][:16], 'expected', group['sections'][name]['sha256'][:16])
        return 4
    print('NAVIGATION_COMPATIBILITY VERIFIED', value[:16], {k: v['rows'] for k, v in sections.items()})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('register', 'check', 'verify'):
        p = sub.add_parser(name)
        p.add_argument('--code-root', type=Path, default=REPO)
        p.add_argument('--registry', type=Path, default=None, help='default: <code-root>/' + REGISTRY)
        if name != 'check':
            p.add_argument('--publisher-root', type=Path, default=REPO)
        if name == 'register':
            p.add_argument('--source', required=True)
            p.add_argument('--new-derivation', action='store_true')
    args = parser.parse_args(argv)
    args.registry = args.registry or Path(args.code_root) / REGISTRY
    return {'register': command_register, 'check': command_check, 'verify': command_verify}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
