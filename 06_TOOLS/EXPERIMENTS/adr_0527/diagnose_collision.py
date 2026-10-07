"""Replay frozen ADR-0526 compiler without writes and report colliding IDs."""
import collections
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
FROZEN = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0526/repaired/revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(FROZEN))
from semantic_runtime import term_references as compiler

DB = ROOT / '01_DATA/TERM_RELEASES/adr0526-frame-anchors-v1/generation.building-gil2qi2j/navigation/navigation.sqlite'
OUT = ROOT / '04_EXPERIMENTS/ADR/ADR-0527-frame-anchor-identity-repair/artifacts/collision-diagnosis.json'


class ReadOnlyRecorder:
    def __init__(self, db):
        self.db = db
        self.seen_ids = set()
        self.collisions = []
        self.attempts = 0

    def executescript(self, sql):
        # The frozen compiler only uses this to create already-existing indexes.
        assert 'CREATE TABLE IF NOT EXISTS reference_target' in sql

    def execute(self, sql, values=()):
        if sql.startswith('INSERT OR IGNORE INTO reference VALUES'):
            ident, document_id, payload = values
            self.attempts += 1
            if ident in self.seen_ids:
                prior = self.db.execute('SELECT json FROM reference WHERE id=?', (ident,)).fetchone()
                if prior is None:
                    raise RuntimeError('failed build lacks first record for ' + ident)
                def compact(raw):
                    obj = json.loads(raw)
                    item = {key: obj.get(key) for key in (
                        'id', 'source_id', 'block_id', 'mention_start', 'mention_end',
                        'mention_text', 'locator', 'document_name_hint', 'origins',
                        'resolution', 'reason', 'unresolved_paths',
                    )}
                    item['targets'] = [
                        {key: target.get(key) for key in ('source_id', 'unit_id', 'unit_path', 'block_ids')}
                        for target in obj.get('targets', [])]
                    return item
                first, later = compact(prior[0]), compact(payload)
                self.collisions.append({'id': ident, 'first': first, 'later': later,
                                        'identical': first == later})
            else:
                self.seen_ids.add(ident)
            return None
        if sql.startswith('INSERT OR IGNORE INTO reference_'):
            return None
        return self.db.execute(sql, values)

    def executemany(self, sql, values):
        assert sql.startswith('INSERT OR IGNORE INTO reference_'), sql
        return None


def main():
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as db:
        recorder = ReadOnlyRecorder(db)
        aliases, delegations, inputs_sha256 = compiler.load_reference_inputs()
        expected, unresolved = compiler.compile_references(recorder, aliases, delegations)
    result = {'schema_version': 'reference-collision-diagnosis-v1',
              'frozen_compiler': str(pathlib.Path(compiler.__file__).relative_to(ROOT)),
              'source_database': str(DB.relative_to(ROOT)),
              'reference_inputs_sha256': inputs_sha256,
              'record_attempts': recorder.attempts, 'compiler_reported': expected,
              'unique_ids': len(recorder.seen_ids), 'collisions': recorder.collisions,
              'collisions_by_origin': dict(collections.Counter(
                  str(c['first']['origins']) + ' -> ' + str(c['later']['origins'])
                  for c in recorder.collisions)),
              'unresolved_attempts': unresolved}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'collisions'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
