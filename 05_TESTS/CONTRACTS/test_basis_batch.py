"""Synthetic contract tests; no external or GENOS model calls."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient

from semantic_runtime.basis_links.grouping import inventory
from semantic_runtime.basis_links.contracts import BasisError, digest
from semantic_runtime.basis_links.resolver import snapshot, targets
from semantic_runtime.basis_links.integration import parent_task
from semantic_runtime.basis_links.repository import Repository
from lawrag.pipeline import basis_batch as batch
from test_authority import service, generation, WHO, BODY, review_body
from test_ingress import app

PROVENANCE = {'type': 'MODEL_OBSERVATION', 'method': 'BATCH_DISCOVERY_V1',
              'retrieval_role': 'UNREVIEWED_CANDIDATE'}


def structured(units, blocks):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('CREATE TABLE source_unit(document_id,unit_id,parent_id,json);'
                     'CREATE TABLE source_block(document_id,block_id,unit_id,text);')
    for uid, parent, lo, hi in units:
        db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',
                   ('i', uid, parent, json.dumps({'span': [lo, hi], 'title': uid})))
    for bid, owner in blocks:
        db.execute('INSERT INTO source_block VALUES(?,?,?,?)', ('i', str(bid), owner, '본문 ' + str(bid)))
    return S(db=db, check_unchanged=lambda: None)


def test_parent_merge_and_unclassified_complete_once():
    store = structured([('chapter', None, 0, 6), ('article', 'chapter', 0, 4),
                        ('p1', 'article', 0, 2), ('p2', 'article', 2, 4),
                        ('annex', None, 5, 6)], [(0, 'p1'), (1, 'p1'), (2, 'p2'), (3, 'p2'), (4, 'chapter'), (5, 'annex'), (6, None)])
    result = inventory(store, 'i')
    assert [r['node']['unit_id'] for r in result] == ['article', 'chapter', 'annex', None]
    ids = [p['block_id'] for r in result for p in r['node']['read_segments']]
    assert len(ids) == len(set(ids)) == 7
    assert result[0]['scope_policy'] == 'parent-overlap-v1'
    store.db.close()


def test_nested_parent_overlap_merges_to_larger_real_parent():
    store = structured([('root', None, 0, 6), ('a', 'root', 0, 4),
                        ('a1', 'a', 0, 2), ('a2', 'a', 2, 4), ('b', 'root', 4, 6)],
                       [(i, 'a1' if i < 2 else 'a2' if i < 4 else 'b') for i in range(6)])
    result = inventory(store, 'i')
    assert len(result) == 1 and result[0]['node']['unit_id'] == 'root'
    assert len(result[0]['merged_units']) == 2
    store.db.close()


@pytest.mark.parametrize('units', [[('a', 'missing', 0, 1)],
                                 [('a', 'b', 0, 1), ('b', 'a', 0, 1)],
                                 [('a', None, 1, 2), ('b', 'a', 0, 2)]])
def test_bad_structure_cannot_invent_parent(units):
    store = structured(units, [(0, 'a')])
    with pytest.raises(BasisError):
        inventory(store, 'i')
    store.db.close()


@pytest.mark.parametrize('kind', ['BASIS', 'IMPLEMENTS', 'RELATED'])
def test_candidate_readable_immediately_without_approval(service, kind):
    p = service.propose(WHO, {**BODY, 'kind': kind, 'provenance': PROVENANCE})
    selected = snapshot(service, WHO, ['inside'])
    found = targets(service, WHO, selected)
    assert len(found) == 1 and found[0]['retrieval_role'] == 'UNREVIEWED_CANDIDATE'
    assert found[0]['relation_status'] == 'PROPOSED'
    assert service.repo.head(p['link']['link_id'])['status'] == 'PROPOSED'
    assert len(service.repo.history(p['link']['link_id'])['events']) == 1
    assert not targets(service, {**WHO, 'document_ids': ['inside']}, snapshot(service, {**WHO, 'document_ids': ['inside']}, ['inside']))
    service.review(WHO, review_body(p, 'reject'))
    assert not targets(service, WHO, selected)
    assert not snapshot(service, WHO, ['inside'])['items']


@pytest.mark.parametrize('provenance', [{'type': 'USER_SELECTION'},
    {'type': 'MODEL_OBSERVATION'}, {'type': 'IMPORT', 'method': 'BATCH_DISCOVERY_V1'},
    {**PROVENANCE, 'retrieval_role': 'APPROVED'}])
def test_other_candidates_not_silently_enabled(service, provenance):
    service.propose(WHO, {**BODY, 'provenance': provenance})
    assert not targets(service, WHO, snapshot(service, WHO, ['inside']))


def test_current_generation_and_hash_cannot_be_bypassed(service):
    service.propose(WHO, {**BODY, 'provenance': PROVENANCE})
    selected = snapshot(service, WHO, ['inside'])
    broken = deepcopy(selected)
    broken['items'][0]['binding']['external'][0]['spans'][0]['text'] = 'tampered'
    broken['snapshot_hash'] = digest({k: v for k, v in broken.items() if k != 'snapshot_hash'})
    with pytest.raises(BasisError):
        targets(service, WHO, broken)
    service.sources.store.manifest = {**service.sources.store.manifest, 'generation_id': 'another'}
    assert not targets(service, WHO, snapshot(service, WHO, ['inside']))


def test_incremental_index_and_old_history_preserved(service, monkeypatch):
    p = service.propose(WHO, {**BODY, 'provenance': PROVENANCE})
    history = service.repo.history(p['link']['link_id'])
    monkeypatch.setattr(service.repo, 'links', lambda *a: pytest.fail('full relation scan'))
    assert len(snapshot(service, WHO, ['inside'])['items']) == 1
    assert service.propose(WHO, {**BODY, 'provenance': PROVENANCE}) == p
    assert service.repo.history(p['link']['link_id']) == history
    assert service.repo.db.execute('SELECT count(*) FROM basis_document_lookup').fetchone()[0] == 2


def test_legacy_relation_lookup_backfill(tmp_path, service):
    service.propose(WHO, BODY)
    path = tmp_path / 'legacy.sqlite'
    db = sqlite3.connect(path)
    service.repo.db.backup(db)
    db.executescript('DROP TABLE basis_document_lookup; DROP TABLE basis_lookup_version;')
    db.close()
    repo = Repository(path)
    assert len(repo.links_for_document('risk_team', 'inside')) == 1
    assert repo.db.execute('SELECT count(*) FROM basis_event').fetchone()[0] == 1
    repo.close()


def link_transport(app, monkeypatch):
    from test_legal_agent_double_harness import wire
    runtime = app.state.workflow_runtime
    rag = importlib.import_module(runtime.services.__class__.__module__.rsplit('.', 1)[0] + '.workflow_rag')
    calls = []
    def child(port, action, call_id):
        calls.append(action)
        return port.execute({'operation': 'read_node', 'side': 'external',
                             'args': {'node': port.session.node('outside', '0'), 'cursor': None}})
    monkeypatch.setattr(rag, 'execute', child)
    def send(*, body, ticket):
        value = json.loads(body['messages'][1]['content'])['view']
        internal = next(e for e in value['sources'] if e['side'] == 'internal')
        external = next(e for e in value['sources'] if e['side'] == 'external')
        return wire({'links': [{'internal_ref': internal['evidence_id'],
                               'external_refs': [external['evidence_id']],
                               'kind': 'BASIS', 'reason': '합성 모델의 연결 의견'}], 'notes': ['미승인 후보']})
    monkeypatch.setattr(runtime.services.pipeline.term_agent.transport, 'send_once', send)
    return calls


def test_real_api_discover_sqlite_next_comparison_task(app, monkeypatch):
    calls = link_transport(app, monkeypatch)
    body = {'workflow_id': 'internal_basis_discovery_workflow', 'session_id': 'batch-test',
            'request_id': 'same', 'input': {'internal_document_id': 'inside',
                'scope_policy': 'parent-overlap-v1', 'publish_candidates': True}}
    with TestClient(app) as client:
        response = client.post('/v1/workflows/run', json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['status'] == 'completed', result
        assert result['coverage']['unprocessed'] == 0 and result['basis_link_ids']
        count = len(calls)
        replay = client.post('/v1/workflows/run', json=body).json()
        assert replay['basis_link_ids'] == result['basis_link_ids'] and len(calls) == count
        with app.state.pipeline.basis_factory() as service:
            row = service.list(WHO, 'inside')['items'][0]
        endpoint = row['binding']['internal'][0]
        ctx = S(rag=S(port=S(services=S(pipeline=app.state.pipeline)),
                      evidence=lambda: [{'side': 'internal', **endpoint}]),
                request={'principal': WHO, 'document_ids': WHO['document_ids'], 'as_of': None},
                repo=S(save=lambda state: None))
        action = {'args': {'task': {}}}
        parent_task(ctx, {}, 'external', action)
        assert action['args']['task']['basis_targets'][0]['endpoint']['document_id'] == 'outside'
        assert action['args']['task']['basis_targets'][0]['retrieval_role'] == 'UNREVIEWED_CANDIDATE'
        assert row['link']['status'] == 'PROPOSED'


def prepare_app(app):
    app.state.workflow_runtime.services.release = {'mode': 'local-release'}
    return app


def test_plan_only_latest_scope_and_source_only_run_reuse(app, tmp_path):
    prepare_app(app)
    value, rows = batch.plan(app, 'risk_team', count=3)
    assert [r['document_id'] for r in rows] == ['inside']
    assert len(value['documents']) == 1 and value['documents'][0]['scope_count'] == 1
    before = app.state.pipeline.store.manifest['store_sha256']
    folder = tmp_path / 'job'
    folder.mkdir()
    state = batch.run(app, value, folder, use_llm=False)
    assert state['status'] == 'completed'
    again = batch.run(app, value, folder, use_llm=False)
    assert again['documents'] == state['documents']
    assert (folder / 'LINKS.csv').exists()
    assert app.state.pipeline.store.manifest['store_sha256'] == before
    with pytest.raises(BasisError):
        batch.plan(app, 'risk_team', ids=['outside'])
    with pytest.raises(BasisError):
        batch.plan(app, 'risk_team', ids=['not-visible'])


def test_batch_will_not_send_internal_to_external_model(app, tmp_path):
    prepare_app(app)
    value, _ = batch.plan(app, 'risk_team')
    with pytest.raises(BasisError, match='내부 모델'):
        batch.run(app, value, tmp_path, use_llm=True)
    assert not (tmp_path / 'STATE.json').exists()


def test_batch_crash_then_explicit_resume_no_new_request(app, monkeypatch, tmp_path):
    prepare_app(app)
    value, _ = batch.plan(app, 'risk_team')
    runtime = app.state.workflow_runtime
    original = runtime.execute
    calls = []
    class Crash(BaseException):
        pass
    def interrupted(body, who, **kwargs):
        calls.append((body, kwargs))
        result = original(body, who, **kwargs)
        if len(calls) == 1:
            raise Crash()
        return result
    monkeypatch.setattr(runtime, 'execute', interrupted)
    with pytest.raises(Crash):
        batch.run(app, value, tmp_path, use_llm=False)
    with pytest.raises(BasisError, match='resume'):
        batch.run(app, value, tmp_path, use_llm=False)
    state = batch.run(app, value, tmp_path, resume=True, use_llm=False)
    assert state['status'] == 'completed'
    assert calls[0][0] == calls[1][0] and calls[1][1]['resume'] is True
    assert state['documents']['inside']['usage']['model_reserved'] == 0


def test_partial_not_automatically_rerun(app, monkeypatch, tmp_path):
    prepare_app(app)
    value, _ = batch.plan(app, 'risk_team')
    runtime = app.state.workflow_runtime
    original = runtime.execute
    calls = []
    def partial(body, who, **kwargs):
        calls.append(body)
        result = original(body, who, **kwargs)
        return {**result, 'status': 'partial', 'continuation_available': True}
    monkeypatch.setattr(runtime, 'execute', partial)
    first = batch.run(app, value, tmp_path, use_llm=False)
    second = batch.run(app, value, tmp_path, resume=True, use_llm=False)
    assert first['status'] == second['status'] == 'partial' and len(calls) == 1


def test_plan_hash_and_changed_selection_rejected(app):
    prepare_app(app)
    value, _ = batch.plan(app, 'risk_team')
    altered = deepcopy(value)
    altered['documents'][0]['document_id'] = 'outside'
    with pytest.raises(BasisError):
        batch.verify_plan(app, altered)
    app.state.workflow_runtime.services.profile['max_model_attempts'] += 1
    with pytest.raises(BasisError):
        batch.verify_plan(app, value)


def test_status_during_run_and_state_tamper(app, tmp_path, capsys):
    prepare_app(app)
    value, _ = batch.plan(app, 'risk_team')
    batch.run(app, value, tmp_path, use_llm=False)
    with batch.lock(tmp_path):
        assert batch.main(['status','--job',str(tmp_path)]) == 0
    assert '"status": "completed"' in capsys.readouterr().out
    path = tmp_path/'STATE.json'
    state = json.loads(path.read_text())
    state['status'] = 'invented'
    path.write_text(json.dumps(state))
    with pytest.raises(BasisError,match='상태 해시'):
        batch.run(app, value, tmp_path, use_llm=False)


def test_native_candidate_exact_read_without_approval_or_model(app, tmp_path):
    from semantic_runtime.legal_agent.source_recall import SourceRecall
    from semantic_runtime.legal_agent.law_navigation import Investigation
    from semantic_runtime.basis_links.resolver import acquire
    pipeline = app.state.pipeline
    with pipeline.basis_factory() as authority:
        authority.propose(WHO, {**BODY, 'provenance': PROVENANCE})
    request = {'question': '모의내규 근거 외규', 'document_ids': WHO['document_ids'], 'use_llm': False}
    with pipeline.term_agent.open_session(
            request, query=pipeline.plan(request['question'], WHO['document_ids']), runtime=tmp_path/'native') as session:
        session.sources.source.basis_factory = pipeline.basis_factory
        session.sources.source.basis_principal = WHO
        recall = SourceRecall(session.sources).prepare()
        def no_model(*args, **kwargs):
            pytest.fail('Stored candidate retrieval must not call a model')
        investigation = Investigation(session.sources, request['question'], recall, no_model, 120, None, lambda *_: None)
        acquire(investigation)
        reads = investigation.p['basis_links']['reads']
        assert len(reads) == 1 and next(iter(reads.values()))['status'] == 'COMPLETE'
        evidence = session.work.evidence(next(iter(reads.values()))['evidence_ids'][0])
        assert evidence['document_id'] == 'outside'
        assert any('미승인' in g['reason'] for g in investigation.p['groups'].values())
        before = session.work.budget()
        acquire(investigation)
        assert before == session.work.budget()


def test_shared_sqlite_requires_explicit_external_runtime(app, monkeypatch):
    from semantic_runtime.basis_links.api import enabled_shared_factory
    pipeline = app.state.pipeline
    runtime = app.state.workflow_runtime.services.runtime
    assert enabled_shared_factory(pipeline, runtime) is None
    batch.atomic(runtime/'basis-links/SQLITE_ENABLED.json',
                 {'schema_version':'basis-shared-sqlite-v1','database':'authority.sqlite'})
    with pytest.raises(BasisError, match='외부 공유'):
        enabled_shared_factory(pipeline, runtime)
    # Protocol-only mount double; this does not certify real NFS locking.
    import semantic_runtime.state_sqlite as state_sqlite
    monkeypatch.setattr(state_sqlite, 'network_storage', lambda _: True)
    factory = enabled_shared_factory(pipeline, runtime)
    with factory() as authority:
        row = authority.propose(WHO, {**BODY, 'provenance':PROVENANCE})
        assert authority.repo.head(row['link']['link_id'])['status'] == 'PROPOSED'
