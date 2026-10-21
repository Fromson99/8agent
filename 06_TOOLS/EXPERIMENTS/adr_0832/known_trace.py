"""Offline diagnostic only: never modify the failed journal or call a model."""
from pathlib import Path
import hashlib, json, sqlite3, sys

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0832-compact-evidence-delivery'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
C = R / '02_BACKEND/lawrag/research/candidates/adr_0832/connected'
rev = read(C / 'candidate.json')['revisions'][-1]['revision_id']
code = C / 'revisions' / rev / 'snapshot'
sys.path.insert(0, str(code / '02_BACKEND'))
sys.dont_write_bytecode = True
from semantic_runtime.legal_agent.bounded_source_session import compact_assessment_evidence
from semantic_runtime.legal_agent.unified_publication import _ref
from semantic_runtime.legal_agent.errors import ContractError

p = R / read(A / 'artifacts/design/known-failure.json')['journal']
before = sha(p)
original = sqlite3.connect('file:' + str(p) + '?mode=ro', uri=True)
original.row_factory = sqlite3.Row
db = sqlite3.connect(':memory:')
original.backup(db)
db.row_factory = sqlite3.Row
# Retrospective diagnostic fixture only. Production append-only guards remain.
for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
    db.execute('DROP TRIGGER "' + row[0].replace('"', '""') + '"')
ref = dict(db.execute("SELECT kind,entity_id,version,payload_hash FROM entity_version WHERE entity_id='case:ASSESS'").fetchone())
ref['choice_id'] = db.execute("SELECT id FROM domain_choice WHERE stage='ASSESS'").fetchone()[0]
def rejected():
    try:
        _ref(db, ref, 'ASSESS')
    except ContractError as exc:
        assert str(exc) == 'judgment source was not delivered in a successful model call'
        return True
    return False
assert rejected()
acquired = []
for row in db.execute('SELECT * FROM evidence_unit'):
    e = dict(row)
    e['metadata'] = json.loads(e.pop('metadata_json'))
    e['spans'] = [dict(s) for s in db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal', (e['evidence_id'],))]
    e['text'] = '\n'.join(s['text'] for s in e['spans'])
    acquired.append(e)
views = [(r['view_id'], json.loads(r['body_json'])) for r in db.execute('SELECT * FROM model_view')]
view_id, view = next((i, v) for i, v in views if v.get('source_stage') == 'memory-assess')
assert db.execute("SELECT count(*) FROM model_attempt WHERE view_id=? AND status='SUCCEEDED'", (view_id,)).fetchone()[0] == 1
projected = compact_assessment_evidence(view, acquired)
assert len(projected) == len(view['evidence_options']) == 4
data = R / read(A / 'artifacts/design/data-binding.json')['path']
source = sqlite3.connect('file:' + str(data / 'store.sqlite') + '?mode=ro', uri=True)
for e in projected:
    for s in e['spans']:
        raw = source.execute('SELECT text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?', (e['document_id'], s['block_id'])).fetchone()
        assert raw and raw[1] == e['source_artifact_hash']
        assert hashlib.sha256(raw[0].encode()).hexdigest() == s['block_hash']
        assert raw[0][s['start_cp']:s['end_cp']] == s['text']
        assert hashlib.sha256(s['text'].encode()).hexdigest() == s['span_hash']
    values = {**e, 'metadata_json': json.dumps(e['metadata'], ensure_ascii=False), 'created_seq': 1}
    cols = [r[1] for r in db.execute('PRAGMA table_info(evidence_unit)')]
    db.execute('INSERT OR IGNORE INTO evidence_unit (' + ','.join(cols) + ') VALUES (' + ','.join('?' for _ in cols) + ')', [values[c] for c in cols])
    for ordinal, s in enumerate(e['spans']):
        values = {**s, 'evidence_id': e['evidence_id'], 'ordinal': ordinal}
        cols = [r[1] for r in db.execute('PRAGMA table_info(evidence_span)')]
        db.execute('INSERT OR IGNORE INTO evidence_span (' + ','.join(cols) + ') VALUES (' + ','.join('?' for _ in cols) + ')', [values[c] for c in cols])
    db.execute('INSERT OR IGNORE INTO evidence_dependency VALUES (?,?,?,?)', (ref['kind'], ref['entity_id'], ref['version'], e['evidence_id']))
    db.execute('INSERT INTO presentation VALUES (?,?,?)', (view_id, e['evidence_id'], e['text_hash']))
db.execute('DELETE FROM presentation WHERE view_id<>?', (view_id,))
_ref(db, ref, 'ASSESS')
db.execute("UPDATE model_attempt SET status='FAILED' WHERE view_id=?", (view_id,))
assert rejected()
assert sha(p) == before
result = {'status': 'PASS', 'kind': 'known failure offline reconstruction; not a product resume or fresh model result',
          'original_failure_reproduced': True, 'exact_option_spans': len(projected), 'original_span_checks': True,
          'own_assessment_delivery_passes_unchanged_guard': True, 'failed_attempt_rejected': True,
          'journal_unchanged': True, 'journal_sha256': before, 'real_model_calls': 0, 'code_root': str(code.relative_to(R))}
(A / 'artifacts/run-001/known-trace.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
