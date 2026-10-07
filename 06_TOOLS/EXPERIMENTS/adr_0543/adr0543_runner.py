"""ADR-0543 research runner: hash-checked candidate import, contract tests, corpus recompile.

Subcommands
  tests  <arm>            run the 45 existing reference contracts (+ ADR S2 contracts for composed)
  rebuild <arm> <out>     copy compiler inputs from the frozen generation and recompile references
Baseline imports production `02_BACKEND`; composed imports only the frozen revision snapshot.
No model calls. The frozen generation is opened read-only.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0543-declared-alias-suffix-resolution'
CANDIDATE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0543/composed'
BASE = ROOT / '01_DATA/TERM/relation-subtree-main-serving-20260920-v1/generation/navigation'
EXISTING = ['05_TESTS/CONTRACTS/test_cross_law_references.py', '05_TESTS/CONTRACTS/test_provision_references.py',
            '05_TESTS/CONTRACTS/test_annex_linking.py', '05_TESTS/REGRESSION/core/test_disclosure_structure.py']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def frozen_root():
    manifest = json.loads((CANDIDATE / 'candidate.json').read_text())
    revision = manifest['revisions'][-1]
    for row in revision['files']:
        if sha(ROOT / row['frozen_path']) != row['snapshot_sha256']:
            raise SystemExit('Frozen code drift: ' + row['frozen_path'])
    return CANDIDATE / 'revisions' / revision['revision_id'] / 'snapshot/02_BACKEND', revision


def arm_path(arm):
    if arm == 'baseline':
        return ROOT / '02_BACKEND', None
    if arm == 'composed':
        return frozen_root()
    raise SystemExit('unknown arm ' + arm)


def tests(arm):
    code, revision = arm_path(arm)
    files = list(EXISTING)
    env = dict(os.environ)
    plugin = []
    if arm == 'composed':
        files.append(str(Path(__file__).with_name('test_adr0543_contract.py').relative_to(ROOT)))
        env['ADR0543_FROZEN_ROOT'] = str(code)
        # Frozen modules first, production package for every module the revision did not copy.
        env.update(ADR_FROZEN_ROOT=str(code), ADR_PRODUCTION_ROOT=str(ROOT / '02_BACKEND'),
                   PYTHONPATH=str(Path(__file__).parent))
        plugin = ['-p', 'adr0543_pkgpath']
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *plugin, *files]
    return subprocess.call(cmd, cwd=ROOT, env=env)


def rebuild(arm, out):
    code, revision = arm_path(arm)
    sys.path.insert(0, str(code))
    sys.path.insert(1, str(ROOT / '02_BACKEND'))
    import semantic_runtime
    if arm != 'baseline':
        semantic_runtime.__path__.append(str(ROOT / '02_BACKEND/semantic_runtime'))
    import semantic_runtime.term_references as tr
    assert Path(tr.__file__).resolve().is_relative_to(code.resolve()), tr.__file__
    out = Path(out).resolve()
    assert not out.exists(), 'do not overwrite a rebuild'
    out.parent.mkdir(parents=True, exist_ok=True)
    base_manifest = json.loads((BASE / 'manifest.json').read_text())
    old = sqlite3.connect('file:' + str(BASE / 'navigation.sqlite') + '?mode=ro', uri=True)
    db = sqlite3.connect(out)
    copied = {}
    for table in ('source', 'source_unit_map', 'document_frame'):
        schema = old.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone()[0]
        db.execute(schema)
        cursor = old.execute('SELECT * FROM ' + table)
        count = 0
        while rows := cursor.fetchmany(5000):
            db.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' * len(rows[0])) + ')', rows)
            count += len(rows)
        copied[table] = count
    db.executescript('CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);'
                     'CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));')
    db.commit()
    aliases, delegations, inputs = tr.load_reference_inputs()
    assert inputs == base_manifest['reference_inputs_sha256'], (inputs, base_manifest['reference_inputs_sha256'])
    started = time.monotonic()
    counts = tr.compile_references(db, aliases, delegations)
    seconds = time.monotonic() - started
    db.commit()
    content = hashlib.sha256()
    for (payload,) in db.execute('SELECT json FROM reference ORDER BY id'):
        content.update(payload.encode())
    db.close()
    old.close()
    receipt = {'arm': arm, 'compiler_root': str(code.relative_to(ROOT)),
               'compiler_revision': revision and {k: revision[k] for k in ('revision_id',) if k in revision},
               'term_references_sha256': sha(tr.__file__),
               'term_references_legacy_sha256': sha(Path(tr.__file__).with_name('term_references_legacy.py')),
               'source_db': str((BASE / 'navigation.sqlite').relative_to(ROOT)),
               'source_index_sha256_declared': base_manifest['index_sha256'],
               'reference_inputs_sha256': inputs, 'copied_rows': copied, 'counts': counts,
               'reference_content_sha256': content.hexdigest(), 'seconds': seconds,
               'path': str(out.relative_to(ROOT)), 'model_calls': 0}
    out.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'tests':
        raise SystemExit(tests(sys.argv[2]))
    if cmd == 'rebuild':
        rebuild(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)
