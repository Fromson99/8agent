"""ADR-0546: research generations that differ from the active one only in reference rows.

Hardlink tree (cp -al) of the frozen generation; only navigation.sqlite and three manifests are
unlinked and rewritten, so no shared original file is ever modified in place.
usage: build_generations.py <arm> <reference-source.sqlite> <expected-reference-content-sha256>
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0546-reference-fix-recall-replay'
BASE = R / '01_DATA/TERM/relation-subtree-main-serving-20260920-v1/generation'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def content_sha(db):
    h = hashlib.sha256()
    for (payload,) in db.execute('SELECT json FROM reference ORDER BY id'):
        h.update(payload.encode())
    return h.hexdigest()


def rewrite(path, value):
    """Replace a hardlinked file with a new inode; the shared original stays untouched."""
    path.unlink()
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main(arm, source, expected):
    out = A / 'artifacts/generations' / arm / 'generation'
    assert not out.exists(), 'do not overwrite a research generation'
    out.parent.mkdir(parents=True)
    subprocess.run(['cp', '-al', str(BASE), str(out)], check=True)
    nav = out / 'navigation/navigation.sqlite'
    nav.unlink()
    shutil.copyfile(BASE / 'navigation/navigation.sqlite', nav)
    db = sqlite3.connect(nav)
    db.execute('ATTACH ? AS r', ('file:' + str(Path(source).resolve()) + '?mode=ro',))
    before = {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('reference', 'reference_end')}
    db.execute('DELETE FROM reference')
    db.execute('DELETE FROM reference_end')
    db.execute('INSERT INTO reference(id,document_id,json) SELECT id,document_id,json FROM r.reference')
    db.execute('INSERT INTO reference_end(source_id,reference_id) SELECT source_id,reference_id FROM r.reference_end')
    db.commit()
    db.execute('DETACH r')
    after = {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('reference', 'reference_end')}
    unresolved = db.execute("SELECT count(*) FROM reference WHERE json_extract(json,'$.resolution')='UNRESOLVED'").fetchone()[0]
    got = content_sha(db)
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    assert got == expected, (got, expected)
    index_sha = sha(nav)
    nm = json.loads((BASE / 'navigation/manifest.json').read_text())
    nm['index_sha256'] = index_sha
    nm['counts']['reference'] = after['reference']
    nm['unresolved_references'] = unresolved
    nm['research_reference_replacement'] = {
        'adr': 'ADR-0546', 'arm': arm, 'tables': ['reference', 'reference_end'],
        'source': str(Path(source).resolve().relative_to(R)), 'reference_content_sha256': got,
        'original_index_sha256': json.loads((BASE / 'navigation/manifest.json').read_text())['index_sha256'],
        'serving_generation': False, 'quality_certified': False}
    rewrite(out / 'navigation/manifest.json', nm)
    fm = json.loads((BASE / 'fulltext/manifest.json').read_text())
    fm['navigation_index_sha256'] = index_sha
    rewrite(out / 'fulltext/manifest.json', fm)
    gm = json.loads((BASE / 'manifest.json').read_text())
    gm['navigation']['manifest_sha256'] = sha(out / 'navigation/manifest.json')
    rewrite(out / 'manifest.json', gm)
    receipt = {'arm': arm, 'path': str(out.relative_to(R)), 'reference_rows_before': before, 'reference_rows_after': after,
               'unresolved_references': unresolved, 'reference_content_sha256': got, 'index_sha256': index_sha,
               'rewritten_files': ['navigation/navigation.sqlite', 'navigation/manifest.json', 'fulltext/manifest.json', 'manifest.json'],
               'hardlinked_unchanged': 'all other files (cp -al)', 'model_calls': 0}
    (A / 'artifacts' / f'generation-{arm}.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main(*sys.argv[1:4])
