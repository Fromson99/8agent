"""Migration corruption, source-accounting and no-activation invariants."""
import gzip
import importlib.util
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

REPO = next(p.parent for p in Path(__file__).resolve().parents if p.name == '05_TESTS')
ENGINE = Path(os.environ.get('SEMANTIC_MIGRATION_ENGINE', str(REPO / '02_BACKEND/ENGINES/semantic_migration/1.0.0/engine.py')))
spec = importlib.util.spec_from_file_location('migration_test_engine', ENGINE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def shadow(tmp_path):
    for rel in ['00_SYSTEM/LEGAL_SCHEMA.json', '00_SYSTEM/SCHEMAS/legal-semantic-v2.schema.json',
                '06_TOOLS/AUDIT/legal_semantic_contract.py']:
        dest = tmp_path / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(REPO / rel, dest)
    source = tmp_path / '09_ARTIFACTS/STAGING/input'; source.mkdir(parents=True)
    db = sqlite3.connect(source / 'migration.sqlite')
    db.executescript('CREATE TABLE source_artifact(path TEXT,sha256 TEXT,bytes INTEGER,object_path TEXT); CREATE TABLE observation(document_id TEXT,json TEXT); CREATE TABLE backlog(seq INTEGER PRIMARY KEY,json TEXT);')
    doc = {'doc': '합성 테스트', 'nodes': [{'id': 1, 'parent': None, 'family': 'kr_article', 'surface': '제1조', 'span': [0,2]}],
           'blocks': [{'idx': 0, 'node': 1, 'text': '가나다'}, {'idx': 1, 'node': 1, 'text': '다만 제외'}]}
    spans = [{'id': 'span:1', 'document_id': 'd1', 'node_id': 1, 'block_id': 0, 'start': 0, 'end': 3,
              'text': '가나다', 'text_sha256': m.hashlib.sha256('가나다'.encode()).hexdigest()},
             {'id': 'span:2', 'document_id': 'd1', 'node_id': 1, 'block_id': 0, 'start': 0, 'end': 3,
              'text': '허구값', 'text_sha256': '0'*64}]
    def artifact(path, raw):
        digest = m.hashlib.sha256(raw).hexdigest(); relative = 'objects/' + digest[:2] + '/' + digest
        dest = source / relative; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
        db.execute('INSERT INTO source_artifact VALUES (?,?,?,?)', (path, digest, len(raw), relative))
    artifact('query/structure/d1/result.json', m.enc(doc).encode())
    artifact('source/source-set.lock.json', m.enc({'source_set_sha256':'a'*64,'generation_id':'source-test','export_allowed':False}).encode())
    artifact('semantics/content/legal_graph/CURRENT.json', m.enc({'manifest':'generations/test/manifest.json'}).encode())
    artifact('semantics/content/legal_graph/generations/test/manifest.json', m.enc({'artifacts':{'canonical/clause_spans.jsonl.gz':{'path':'canonical/clause_spans.jsonl.gz','rows':2}}}).encode())
    artifact('semantics/content/legal_graph/generations/test/canonical/clause_spans.jsonl.gz', gzip.compress(('\n'.join(m.enc(s) for s in spans)+'\n').encode()))
    db.commit(); db.close()
    value = {'path':str(source.relative_to(tmp_path)), 'database_sha256':m.sha(source/'migration.sqlite'), 'runtime_id':'b'*64}
    m.write(source/'report.json', {'database_sha256':value['database_sha256'],'runtime_id':value['runtime_id'],'source_artifacts':5})
    value['report_sha256'] = m.sha(source/'report.json')
    return tmp_path, source, value, doc, spans


def execute(shadow, output='01_DATA/SEMANTIC/GENERATIONS/test'):
    root, _, value, _, _ = shadow
    return m.run({'snapshot':value}, {'output_path':output}, {'repository_root':str(root),'mode':'tool'})['store']


def test_full_transfer_is_observation_only_and_covers_sources(shadow):
    root, source, _, _, _ = shadow; before = m.sha(source/'migration.sqlite')
    result = execute(shadow); out = root / result['path']; receipt = m.read(out/'manifest.json')
    assert result['status'] == 'SHADOW' and result['cutover_eligible'] is False
    assert receipt['external_calls'] == 0 and receipt['main_changed'] is False
    assert receipt['clause_span_migration'] == {'input':2,'mapped':1,'unresolved':1}
    assert receipt['entity_rows_by_type'] == {'Evidence':1}
    assert receipt['job_source_blocks'] == 2 and receipt['source_block_coverage_complete']
    assert m.sha(source/'migration.sqlite') == before
    with m.readonly(out/'store.sqlite') as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for _, expected, _, rel in db.execute('SELECT * FROM source_artifact'):
            assert m.sha(out/rel) == expected
        payload = json.loads(db.execute('SELECT input_json FROM authoring_job').fetchone()[0])
        assert [b['text'] for b in payload['blocks']] == ['가나다','다만 제외']
        record = json.loads(db.execute('SELECT json FROM record').fetchone()[0])
        assert record['status'] == 'CANDIDATE' and record['payload']['rules'] == []
        assert record['payload']['provisos'] == []
    assert not (root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').exists()


def test_input_hash_drift_rejected_before_generation(shadow):
    root, _, value, _, _ = shadow; value['database_sha256'] = '0'*64
    with pytest.raises(ValueError, match='hash drift'):
        execute(shadow)
    assert not (root/'01_DATA/SEMANTIC/GENERATIONS/test').exists()


def test_corrupt_archive_rejected_and_failure_preserved(shadow):
    root, source, _, _, _ = shadow
    next((source/'objects').glob('*/*')).write_text('tampered')
    with pytest.raises(ValueError, match='archive hash drift'):
        execute(shadow)
    assert m.read(root/'01_DATA/SEMANTIC/GENERATIONS/test/failure.json')['status'] == 'FAILED'


def test_never_overwrite_generation(shadow):
    root, _, _, _, _ = shadow; result = execute(shadow)
    before = m.sha(root/result['path']/'manifest.json')
    with pytest.raises(FileExistsError):
        execute(shadow)
    assert m.sha(root/result['path']/'manifest.json') == before


def test_active_output_path_rejected(shadow):
    with pytest.raises(ValueError, match='isolated immutable generation'):
        execute(shadow, '01_DATA/ACTIVE/local/new')


def test_archive_path_escape_rejected(shadow):
    root, _, _, _, _ = shadow
    with pytest.raises(ValueError):
        m.inside(root, '../outside')


@pytest.mark.parametrize('change,reason', [({'node_id':99},'SOURCE_MISSING'), ({'end':100},'RANGE_MISMATCH'),
                                         ({'text':'허구'},'QUOTE_MISMATCH')])
def test_span_never_repairs_mismatching_evidence(shadow, change, reason):
    _, _, _, doc, spans = shadow
    doc['_units']={1:doc['nodes'][0]};doc['_blocks']={b['idx']:b for b in doc['blocks']}
    evidence, error = m.span_to_evidence({**spans[0],**change}, 'd1', doc, 'c'*64)
    assert evidence is None and error.endswith(reason)


def test_oversized_article_is_preserved_and_not_dispatchable(shadow):
    root, _, _, doc, _ = shadow; db = m.create_database(root/'large.sqlite')
    doc['blocks'][0]['text'] = '가'*40001
    doc['_units']={1:doc['nodes'][0]};doc['_blocks']={b['idx']:b for b in doc['blocks']}
    db.execute('INSERT INTO document VALUES (?,?,?,?)', ('d1','test','c'*64,'{}'))
    for b in doc['blocks']:
        db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', ('d1',str(b['idx']),'1',b['text'],'c'*64,'{}'))
    stats = m.make_jobs(db,'d1',doc,'c'*64,'a'*64)
    state, raw = db.execute('SELECT state,input_json FROM authoring_job').fetchone()
    assert state == 'NEEDS_SEGMENTATION' and stats['NEEDS_SEGMENTATION'] == 1
    assert len(json.loads(raw)['blocks'][0]['text']) == 40001
    assert db.execute('SELECT COUNT(*) FROM job_block').fetchone()[0] == 2
    db.close()


def test_migration_cannot_issue_canonical_admission():
    with pytest.raises(ValueError, match='observations only'):
        m.insert_observation(None, {'record_kind':'CANONICAL_BUNDLE'}, None, None, None)


def test_quote_does_not_authorize_a_different_structural_range(shadow):
    _, _, _, doc, spans = shadow
    doc['_units']={1:{**doc['nodes'][0],'span':[1,2]}}
    doc['_blocks']={b['idx']:b for b in doc['blocks']}
    evidence, error = m.span_to_evidence(spans[0], 'd1', doc, 'c'*64)
    assert evidence is None and error == 'LEGACY_SPAN_UNIT_MISMATCH'
