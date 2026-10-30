from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest
from ontology_dashboard_demo import create_demo
from ontology_dashboard_model import binding, project, component_diff, scenario
from semantic_runtime.legal_agent.errors import ContractError


@pytest.fixture
def demo():
    api, owner = create_demo()
    yield api, owner
    owner.cleanup()


def test_approval_and_transfer_never_activate(demo):
    api, _ = demo
    d = api.load('cb-demo-review')
    head = api.workflow.repo.head(d['bundle_id'])
    api.review(binding(d), True, '원문 대조 확인')
    approved = api.load(d['bundle_id'])
    key, request = api.prepare_transfer(binding(approved), 'TEST-META-1', '합성 이관 요청')
    assert api.workflow.store.get(key) == request
    assert request['status'] == 'PREPARED_NOT_APPLIED'
    assert request['model_reference_verification'] == 'OPERATOR_SUPPLIED_NOT_VERIFIED'
    assert request['approval_ref'] == approved['approval']
    assert api.workflow.repo.head(d['bundle_id']) == head


def test_unapproved_transfer_is_rejected(demo):
    api, _ = demo
    with pytest.raises(ContractError):
        api.prepare_transfer(binding(api.load('cb-demo-review')), 'ref', 'note')


@pytest.mark.parametrize('operation', ['approve', 'save', 'transfer'])
def test_stale_screen_cannot_write(demo, operation):
    api, _ = demo
    d = api.load('cb-demo-approved')
    api.save(binding(d), d['proposal'])
    with pytest.raises(ContractError):
        if operation == 'approve': api.review(binding(d), True, 'old screen')
        elif operation == 'save': api.save(binding(d), d['proposal'])
        else: api.prepare_transfer(binding(d), 'ref', 'note')


def test_source_change_withholds_rows_and_blocks_actions(demo):
    api, _ = demo
    d = api.load('cb-demo-review')
    api.workflow.source_reader = lambda a: 'changed source'
    assert api.listing() == []
    with pytest.raises(ContractError): api.review(binding(d), True, 'not allowed')


def test_invalid_quote_not_saved_and_head_preserved(demo):
    api, _ = demo
    d = api.load('cb-demo-review')
    head = api.workflow.repo.head(d['bundle_id'])
    changed = deepcopy(d['proposal'])
    changed['components'][0]['basis'][0]['quote'] = 'not in original'
    with pytest.raises(ContractError): api.save(binding(d), changed)
    assert binding(api.load(d['bundle_id'])) == binding(d)
    assert api.workflow.repo.head(d['bundle_id']) == head


def test_projection_uses_only_explicit_edges_and_preserves_source(demo):
    api, _ = demo
    d = api.load('cb-demo-review'); before = deepcopy(d)
    p = project(d, api.previous(d))
    assert {e['kind'] for e in p['edges']} == {'근거 인용', '구성 의존', '경로 포함'}
    assert len(p['nodes']) == 7
    assert [n['id'] for n in p['nodes'] if n.get('changed')] == ['component:산정 기준']
    assert d == before
    assert component_diff(d, api.previous(d))[0]['항목'] == '산정 기준'


def test_transfer_store_failure_not_reported_as_success(demo, monkeypatch):
    api, _ = demo
    d = api.load('cb-demo-approved'); head = api.workflow.repo.head(d['bundle_id'])
    def fail(*args): raise OSError('injected storage failure')
    monkeypatch.setattr(api.workflow.store, 'put', fail)
    with pytest.raises(OSError): api.prepare_transfer(binding(d), 'ref', 'note')
    assert api.workflow.repo.head(d['bundle_id']) == head


def test_history_checks_historical_source_permission(demo):
    api, _ = demo
    d = api.load('cb-demo-review')
    events, more = api.events(d['bundle_id'])
    assert {e['action'] for e in events} >= {'DRAFT', 'APPROVED', 'PUBLISHED'}
    assert not more


@pytest.mark.parametrize(('limit', 'amount', 'baseline', 'result'), [(200, 150, 'FALSE', 'TRUE'), (100, 100, 'TRUE', 'TRUE'),
    (None, 150, 'FALSE', 'UNKNOWN'), (200, None, 'UNKNOWN', 'UNKNOWN'), (1001, 150, 'FALSE', 'UNKNOWN')])
def test_synthetic_scenario_unknown(limit, amount, baseline, result):
    assert scenario(limit, amount) == {'baseline': baseline, 'scenario': result}


def app(monkeypatch, *, review=True):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('ONTOLOGY_DASHBOARD_DEMO', '1')
    monkeypatch.delenv('GENOS_RAG_ONTOLOGY_CONFIG', raising=False)
    at = AppTest.from_file(str(Path(__file__).with_name('ontology_app.py')), default_timeout=20).run()
    if review:
        at.radio(key='od_step').set_value('3 · 검토·승인').run()
    return at


def clean(at):
    assert not at.exception
    assert not at.error


def test_native_dashboard_navigation_and_approval(monkeypatch):
    at = app(monkeypatch); clean(at)
    assert at.radio(key='od_filter').value == '검토 대기'
    assert at.session_state['od_bundle'] == 'cb-demo-review'
    assert len(at.sidebar) == 0
    api = at.session_state['od_demo'][0]
    old_head = api.workflow.repo.head('cb-demo-review')
    next(b for b in at.button if b.label == '승인').click().run()
    assert api.load('cb-demo-review')['status'] == 'DRAFT'
    at.checkbox[0].check()
    next(b for b in at.button if b.label == '승인').click().run(); clean(at)
    assert api.load('cb-demo-review')['status'] == 'APPROVED'
    assert api.workflow.repo.head('cb-demo-review') == old_head
    assert at.radio(key='od_filter').value == '승인 완료'
    assert at.session_state['od_bundle'] == 'cb-demo-review'
    assert any('골드 반영은 담당자가' in s.value for s in at.success)
    assert any('반영 완료 여부를 확인할 수 없습니다' in s.value for s in at.caption)
    events, _ = api.events('cb-demo-review')
    approved = next(e for e in events if e['action'] == 'APPROVED' and e['revision'] == 2)
    assert approved['reason'] == '내용과 근거 원문을 확인하고 승인합니다.'


def test_native_rejection_requires_reason_and_keeps_previous_publication(monkeypatch):
    at = app(monkeypatch)
    api = at.session_state['od_demo'][0]
    head = api.workflow.repo.head('cb-demo-review')
    next(b for b in at.button if b.label == '반려').click().run(); clean(at)
    assert api.load('cb-demo-review')['status'] == 'DRAFT'
    at.text_area[0].input('산정 기준의 원문을 보완해 주세요.')
    next(b for b in at.button if b.label == '반려').click().run(); clean(at)
    assert api.load('cb-demo-review')['status'] == 'REJECTED'
    assert api.workflow.repo.head('cb-demo-review') == head
    assert at.radio(key='od_filter').value == '반려'
    assert any(m.value == '산정 기준의 원문을 보완해 주세요.' for m in at.markdown)


def test_native_connection_failure_no_demo_fallback(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv('ONTOLOGY_DASHBOARD_DEMO', raising=False)
    monkeypatch.delenv('GENOS_RAG_ONTOLOGY_CONFIG', raising=False)
    at = AppTest.from_file(str(Path(__file__).with_name('ontology_app.py'))).run()
    assert not at.exception
    assert len(at.error) == 1
    assert not at.metric


def test_native_configured_workflow_uses_same_entrypoint(demo, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    api, owner = demo
    source = api.load('cb-demo-approved')['input']['originals'][0]
    path = tmp_path / 'source.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE document(document_id TEXT,source_artifact_sha256 TEXT)')
        conn.execute('CREATE TABLE source_block(document_id TEXT,unit_id TEXT,block_id TEXT,text TEXT)')
        conn.execute('INSERT INTO document VALUES (?,?)', (source['anchor']['document_id'], source['anchor']['version']))
        conn.execute('INSERT INTO source_block VALUES (?,?,?,?)', (source['anchor']['document_id'], source['anchor']['unit_id'], '1', source['text']))
    config = {'version': 'ontology-connection-v1', 'environment': 'local', 'database': {'kind': 'sqlite-local', 'path': str(Path(owner.name)/'demo.sqlite')},
              'source': {'kind': 'sqlite-local', 'path': str(path)}, 'work_store': {'kind': 'local', 'path': str(Path(owner.name)/'work')},
              'operators': {'TEST-OPERATOR': {'document_ids': [source['anchor']['document_id']]}}}
    config_path = tmp_path/'config.json'; config_path.write_text(json.dumps(config))
    monkeypatch.setenv('GENOS_RAG_ONTOLOGY_CONFIG', str(config_path))
    monkeypatch.setenv('GENOS_ONTOLOGY_OPERATOR', 'TEST-OPERATOR')
    monkeypatch.delenv('GENOS_BACKEND', raising=False)
    monkeypatch.delenv('ONTOLOGY_DASHBOARD_DEMO', raising=False)
    at = AppTest.from_file(str(Path(__file__).with_name('ontology_app.py'))).run(); clean(at)
    assert at.radio(key='od_step').value == '1 · 모인 기록'
    at.radio(key='od_step').set_value('3 · 검토·승인').run(); clean(at)
    assert at.radio(key='od_filter').value == '검토 대기'
    assert at.session_state['od_identity'][0] == 'TEST-OPERATOR'
    assert at.session_state['od_identity'][1] is False
    existing = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=20).run()
    state = existing.session_state['studio']; state['page'] = '온톨로지 관리'
    existing.session_state['studio'] = state
    existing.run(); clean(existing)
    assert existing.radio(key='od_step').value == '1 · 모인 기록'
    existing.radio(key='od_step').set_value('3 · 검토·승인').run(); clean(existing)
    assert existing.radio(key='od_filter').value == '검토 대기'


def test_collected_input_generation_and_human_approval(monkeypatch):
    at = app(monkeypatch, review=False); clean(at)
    assert at.radio(key='od_step').value == '1 · 모인 기록'
    api = at.session_state['od_demo'][0]
    bid = at.session_state['od_bundle']
    before = api.load(bid)
    assert before['status'] == 'INPUT'
    calls = []
    example = api.workflow.generate
    def tracked(*args):
        calls.append(args)
        return example(*args)
    api.workflow.generate = tracked
    next(b for b in at.button if b.label == '이 기록으로 초안 만들기').click().run(); clean(at)
    assert at.radio(key='od_step').value == '2 · 초안 만들기'
    assert not calls
    assert any('실제 LLM을 호출하지 않습니다' in s.value for s in at.info)
    next(b for b in at.button if b.label == '예시 초안 만들기').click().run(); clean(at)
    assert len(calls) == 1
    assert api.load(bid)['status'] == 'DRAFT'
    assert api.load(bid)['input'] == before['input']
    assert not api.workflow.repo.head(bid)['publication_id']
    at.run(); clean(at)
    assert len(calls) == 1
    next(b for b in at.button if b.label == '초안 검토하기').click().run(); clean(at)
    assert at.radio(key='od_step').value == '3 · 검토·승인'
    assert at.session_state['od_bundle'] == bid
    at.checkbox[0].check()
    next(b for b in at.button if b.label == '승인').click().run(); clean(at)
    assert api.load(bid)['status'] == 'APPROVED'
    assert not api.workflow.repo.head(bid)['publication_id']
    assert len(calls) == 1


def test_generation_unavailable_has_no_demo_substitution(monkeypatch):
    at = app(monkeypatch, review=False)
    api = at.session_state['od_demo'][0]
    api.demo = False
    api.workflow.generate = None
    at.run(); clean(at)
    next(b for b in at.button if b.label == '이 기록으로 초안 만들기').click().run(); clean(at)
    assert next(b for b in at.button if b.label == 'LLM으로 초안 만들기').disabled
    assert any('모델이 아직 연결되지 않았습니다' in s.value for s in at.info)
    assert api.load(at.session_state['od_bundle'])['status'] == 'INPUT'


def test_generation_failure_is_not_automatically_repeated(monkeypatch):
    at = app(monkeypatch, review=False)
    api = at.session_state['od_demo'][0]; calls = []
    def fail(*args):
        calls.append(1)
        raise TimeoutError('ambiguous model transport')
    api.workflow.generate = fail
    next(b for b in at.button if b.label == '이 기록으로 초안 만들기').click().run()
    next(b for b in at.button if b.label == '예시 초안 만들기').click().run()
    assert not at.exception
    assert at.error
    assert api.load(at.session_state['od_bundle'])['status'] == 'INPUT'
    at.run(); clean(at)
    assert next(b for b in at.button if b.label == '예시 초안 만들기').disabled
    assert len(calls) == 1
    assert any('생성 결과 확인' in w.value for w in at.warning)


def test_already_drafted_or_stale_input_never_invokes_generator(demo):
    api, _ = demo
    d = next(d for d in api.listing() if d['status'] == 'INPUT')
    calls = []
    def forbidden(*args):
        calls.append(1)
        raise AssertionError('must not call the generator')
    _, proposal = __import__('ontology_dashboard_demo').fixture()
    api.save(binding(d), proposal)
    api.workflow.generate = forbidden
    with pytest.raises(ContractError): api.propose(binding(d))
    with pytest.raises(ContractError): api.propose(binding(api.load(d['bundle_id'])))
    assert not calls
