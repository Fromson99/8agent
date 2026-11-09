"""문서 대사 through the real API under the selected profile; synthetic originals, scripted model only.

Run against a code root that has the document workflow (MAIN172 and later), e.g.
run_tests.py --code-root <release code>.
"""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semantic_runtime.app import create_app
from test_legal_agent_double_harness import wire

HERE = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get('WORKFLOW_TEST_CODE_ROOT', HERE))
spec = importlib.util.spec_from_file_location('document_mode_concepts', HERE / '05_TESTS/CONTRACTS/test_internal_concept_comparison.py')
concepts = importlib.util.module_from_spec(spec); spec.loader.exec_module(concepts)
tree = concepts.tree
PRINCIPAL = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['inside', 'outside']}
DOCUMENT_WORKFLOW = 'risk_team_document_compare_workflow'


def body(question, request_id, session='s'):
    return {'question': question, 'session_id': session, 'request_id': request_id, 'as_of': '2026-10-15'}


class DocTransport(concepts.Transport):
    """Group placement and unit comparison stand-ins; children use the existing source double."""

    def __init__(self, *, bad_group=0, verdict='CONFORMS', silent_child=0, rejected_child=0):
        super().__init__()
        self.bad_group, self.verdict, self.silent_child, self.rejected_child = bad_group, verdict, silent_child, rejected_child

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        stage = view.get('source_stage', view['phase'])
        if self.silent_child and stage.startswith('source-law-sources-'):
            self.silent_child -= 1
            # Like a provider that never finishes its answer: the gateway records an unknown outcome.
            raise RuntimeError('synthetic provider without a final answer')
        if self.rejected_child and stage.startswith('source-law-sources-') and self.views and self.views[-1][0].startswith('source-law-sources-'):
            self.rejected_child -= 1
            # A known provider rejection after the child has read: only its reads are exported.
            from semantic_runtime.legal_agent.errors import TransportError
            raise TransportError('synthetic known provider rejection', unknown=False)
        if stage == 'workflow-group_read':
            self.views.append((stage, deepcopy(view)))
            refs = [r['ref'] for r in view['rows']]
            if self.bad_group:
                if self.bad_group != 'always':
                    self.bad_group -= 1
                # Every row placed twice: the server must reject, never repair by itself.
                return wire({'units': [{'label': '승인', 'rows': refs, 'summary': '승인 후 보고'}],
                             'not_target': [{'rows': refs, 'reason': '중복 배치'}], 'hold': []})
            return wire({'units': [{'label': '승인 후 보고', 'rows': refs, 'summary': '승인 후 보고한다'}], 'not_target': [], 'hold': []})
        if stage == 'workflow-unit_compare':
            self.views.append((stage, deepcopy(view)))
            pick = lambda side: [{'citation_id': o['citation_id']} for s in view['sources'] if s['side'] == side
                                 for o in s['citation_options']][:1]
            external = pick('external') if self.verdict != 'DEFERRED' else []
            return wire({'internal_citations': pick('internal'), 'external_citations': external,
                         'internal_text': '승인 후 보고', 'external_text': '승인 후 보고' if external else '',
                         'verdict': self.verdict, 'difference': '', 'reason': '양쪽 모두 승인 후 보고를 정함', 'unresolved': []})
        return super().send_once(body=body, ticket=ticket)


def selected_profile():
    nodes = json.loads((ROOT / '00_SYSTEM/PIPELINE.json').read_text())['profiles']['legal-agent-rag-v6']['nodes']
    config = next(n['parameters']['term_agent'] for n in nodes if 'term_agent' in n.get('parameters', {}))
    return json.loads((ROOT / config['legal_agent']['profile']['path']).read_text())


def application(tmp_path, tree, transport, principal=PRINCIPAL):
    from lawrag.pipeline.search_selection import plan, activate
    generation, index = tree
    activate(plan(generation, latest=True))
    profile = selected_profile(); profile['model_binding'] = transport.binding
    app = create_app(tmp_path, generation, contracts_root=ROOT, workspace_root=HERE, provider=object(),
                     implementation='legal-agent-unified-v6', runtime_root=tmp_path / 'runtime',
                     legal_agent_profile=profile, legal_agent_transport=transport, memory_identity=lambda _: principal)
    if index is not None:
        app.state.pipeline.term_agent.unit_fulltext = index
    return app


@pytest.fixture
def tree3(tmp_path, term_glossary):
    """One internal rule naming 모의승인규정 and two external rules, so a narrowed search differs from the side."""
    import hashlib, sqlite3
    from lawrag.pipeline.term_generation import build_generation
    from lawrag.pipeline.fulltext_stage import derive
    folder = tmp_path / 'tree3'; folder.mkdir()
    documents = [('inside', '모의내규', 'internal', '제1조(승인) 모의승인규정에 따라 승인 후 보고한다.'),
                 ('outside', '모의승인규정', 'external', '제1조(승인) 승인 후 보고한다.'),
                 ('other', '모의기록규정', 'external', '제1조(보관) 기록은 1년 이상 보관한다.')]
    with sqlite3.connect(folder / 'source.sqlite') as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
          CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did, name, category, text in documents:
            artifact = hashlib.sha256(text.encode()).hexdigest()
            db.execute('INSERT INTO document VALUES (?,?,?,?)', (did, name, artifact, json.dumps(
                {'document_category': category, 'document_metadata': {'team': 'risk_team'}}, ensure_ascii=False)))
            db.execute('INSERT INTO source_unit VALUES (?,?,?,?)', (did, '0', None, json.dumps(
                {'family': 'kr_article', 'surface': '제1조', 'title': text[4:6], 'span': [0, 1]}, ensure_ascii=False)))
            db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', (did, '0', '0', text, artifact, '{}'))
    build_generation(folder / 'source.sqlite', term_glossary, folder / 'built', serving=True, fulltext_workers=1)
    derive(folder / 'built/generation', folder / 'indexed', workers=1)
    return folder / 'indexed', None


def stages(transport):
    return [stage for stage, _ in transport.views]


def test_mode_choice_routes_document_compare_separately():
    from semantic_runtime.chat_adapter import views
    from workflow.contracts import route, request, WorkflowError
    view = views()
    data = {'applied_fields': {'mode': '문서 대사'}, 'session_id': 'chat-1', 'team_id': 'risk_team'}
    assert view._selected_question('리스크관리규정 대사해 줘', data) == '문서 대사: 리스크관리규정 대사해 줘'
    assert view._selected_question('리스크관리규정 대사해 줘', {**data, 'applied_fields': {'mode': 'document_compare'}}) == '문서 대사: 리스크관리규정 대사해 줘'
    assert view._selected_question('유지 기준 비교', {**data, 'applied_fields': {'mode': '대사'}}) == '대사: 유지 기준 비교'
    with pytest.raises(view.QueryModeError):
        view._selected_question('대사: 유지 기준 비교', data)
    with pytest.raises(view.QueryModeError):
        view._selected_question('리스크관리규정', {'applied_fields': {'mode': '문서 대사'}})
    assert route({'question': '문서 대사: 모의내규'}) == DOCUMENT_WORKFLOW
    assert route({'question': '문서대사: 모의내규'}) == DOCUMENT_WORKFLOW
    assert route({'question': '대사: 모의내규'}) == 'risk_team_compare_workflow'
    with pytest.raises(WorkflowError):
        route({'question': '문서 대사: 모의내규', 'workflow_id': 'risk_team_compare_workflow'})
    value = request({'question': '문서 대사: 모의내규 전체', 'session_id': 's', 'request_id': 'r'},
                    {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['inside']})
    assert value['workflow_id'] == DOCUMENT_WORKFLOW and value['question'] == '모의내규 전체'


def test_whole_document_runs_every_row_without_limits(tmp_path, tree):
    transport = DocTransport()
    app = application(tmp_path, tree, transport)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규 전체 대사해 줘', 'r1'))
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['workflow_id'] == DOCUMENT_WORKFLOW and value['status'] == 'completed', value
        summary = value['document_compare']
        assert summary['document']['document_id'] == 'inside'
        assert summary['groups_total'] >= 1 and summary['groups_finished'] == summary['groups_total'] and summary['units'] >= 1
        assert summary['verdicts']['CONFORMS'] == summary['units'], (summary, stages(transport), value['answer']['text'])
        # No request call/time limit for this workflow; the comparison workflow keeps its own.
        assert value['usage']['model_limit'] == 10 ** 9 and value['usage']['tool_limit'] == 10 ** 9
        seen = stages(transport)
        assert 'workflow-group_read' in seen and 'workflow-unit_compare' in seen
        assert any(s.startswith('source-law-sources-') for s in seen)
        assert not any(s in ('workflow-intake', 'workflow-concepts', 'workflow-items') for s in seen)
        # The external child read the rule named in the internal row (모의승인규정) first.
        child = [v for s, v in transport.views if s.startswith('source-law-sources-')]
        assert any(v.get('preferred_originals') or v.get('sources') for v in child)
        compare = [v for s, v in transport.views if s == 'workflow-unit_compare'][0]
        assert {s['side'] for s in compare['sources']} == {'internal', 'external'}
        text = value['answer']['text']
        assert '문서 대사 결과' in text and '모의내규' in text and '모의승인규정' in text and '승인 후 보고한다' in text, text
        count = len(transport.views)
        again = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규 전체 대사해 줘', 'r1'))
        assert again.status_code == 200 and again.json()['answer'] == value['answer'] and len(transport.views) == count
    from semantic_runtime.legal_agent import journal_storage
    folder = app.state.workflow_runtime.root / value['run_id']
    with journal_storage.connect(str(folder / 'journal.sqlite')) as db:
        progress = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='DOCUMENT_COMPARE_PROGRESS'")]
        deadline = db.execute('SELECT deadline_at FROM run').fetchone()[0]
        tasks = [json.loads(r[0])['args']['task'] for r in db.execute("SELECT input_json FROM workflow_call WHERE kind='rag'")]
    # The unit names 모의승인규정: the search is narrowed to that rule, nothing is loaded whole,
    # and the unit has its own child session.
    assert tasks and all(t['search_document_ids'] == ['outside'] and t['preferred_document_ids'] == [] and t['session_key'] for t in tasks)
    assert progress and progress[-1]['done'] == progress[-1]['total'] == summary['groups_total'], progress
    # The parent has no time limit; each child keeps its own native deadline label.
    children = list(folder.glob('children/*/legal-agent/runs/*/*/journal.sqlite'))
    assert children and deadline[:4] >= '2035'
    for path in children:
        with journal_storage.connect(str(path)) as db:
            assert db.execute('SELECT deadline_at FROM run').fetchone()[0][:4] < '2030'
        assert path.parts[-3][:4] < '2030'


def test_document_is_asked_by_number_when_not_named(tmp_path, tree):
    transport = DocTransport()
    app = application(tmp_path, tree, transport)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=body('문서 대사: 규정 전체를 대사해 줘', 'q1')).json()
        assert first['status'] == 'completed' and first['document_compare']['selection']['status'] == 'NEEDS_DOCUMENT', first
        assert '<ol><li>모의내규</li></ol>' in first['answer']['text'] and transport.views == []
        out_of_range = client.post('/v1/rag/ask', json=body('문서 대사: 7번', 'q2')).json()
        assert out_of_range['document_compare']['selection']['status'] == 'NEEDS_DOCUMENT' and transport.views == []
        chosen = client.post('/v1/rag/ask', json=body('문서 대사: 1', 'q3')).json()
        assert chosen['status'] == 'completed' and chosen['document_compare']['document']['document_id'] == 'inside', chosen
        assert chosen['document_compare']['units'] >= 1
        # Another session cannot use this session's numbered list.
        other = client.post('/v1/rag/ask', json=body('문서 대사: 1', 'q4', session='other')).json()
        assert other['document_compare']['selection']['status'] == 'NEEDS_DOCUMENT'


def test_unplaceable_group_is_held_then_continued_without_redoing_finished_work(tmp_path, tree):
    transport = DocTransport(bad_group='always')
    app = application(tmp_path, tree, transport)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규', 'c1')).json()
        assert first['status'] == 'partial' and first['resume_available'], first
        assert first['document_compare']['groups_held'] == first['document_compare']['groups_total']
        assert stages(transport).count('workflow-group_read') == 2      # first proposal + one correction
        assert '보류' in first['answer']['text'] and '계속' in first['answer']['text']
        transport.bad_group = 0
        second = client.post('/v1/rag/ask', json=body('문서 대사: 계속', 'c2')).json()
        assert second['status'] == 'completed', second
        assert second['document_compare']['continuation_of'] == first['run_id']
        assert second['document_compare']['units'] >= 1 and second['document_compare']['groups_held'] == 0
        count = len(transport.views)
        third = client.post('/v1/rag/ask', json=body('문서 대사: 계속', 'c3')).json()
        assert third['document_compare']['selection']['status'] == 'ALREADY_COMPLETE' and len(transport.views) == count


def test_continue_without_a_previous_run_asks_for_a_document(tmp_path, tree):
    transport = DocTransport()
    app = application(tmp_path, tree, transport)
    with TestClient(app) as client:
        value = client.post('/v1/rag/ask', json=body('문서 대사: 계속', 'n1')).json()
        assert value['document_compare']['selection']['status'] == 'NEEDS_DOCUMENT' and transport.views == []
        assert '이어 갈 문서 대사가 없습니다' in value['answer']['text']


@pytest.mark.parametrize('defect', ['none', 'no_external', 'wrong_side', 'false_quote', 'deferred_ok', 'external_text_alone'])
def test_unit_compare_checks_quotes_and_sides(defect):
    from workflow.risk_team_document_compare_workflow import compare_unit
    sources = [{'evidence_id': 'i', 'side': 'internal', 'spans': [{'text': '승인 후 보고한다.'}]},
               {'evidence_id': 'e', 'side': 'external', 'spans': [{'text': '승인 후 보고한다.'}]}]
    value = {'internal_citations': [{'evidence': 'i', 'quote': '승인 후 보고한다.'}],
             'external_citations': [{'evidence': 'e', 'quote': '승인 후 보고한다.'}],
             'internal_text': '승인 후 보고', 'external_text': '승인 후 보고', 'verdict': 'CONFORMS',
             'difference': '', 'reason': '같음', 'unresolved': []}
    if defect == 'no_external':
        value.update(external_citations=[], external_text='')
    if defect == 'wrong_side':
        value['internal_citations'] = [{'evidence': 'e', 'quote': '승인 후 보고한다.'}]
    if defect == 'false_quote':
        value['external_citations'] = [{'evidence': 'e', 'quote': '5영업일 이내'}]
    if defect == 'deferred_ok':
        value.update(external_citations=[], external_text='', verdict='DEFERRED')
    if defect == 'external_text_alone':
        value.update(external_citations=[], verdict='DEFERRED')
    before = deepcopy(value)
    check = compare_unit.validator(sources)
    if defect in ('none', 'deferred_ok'):
        check(value)
    else:
        with pytest.raises(ValueError):
            check(value)
    assert value == before


def test_external_task_searches_named_rules_only_and_isolates_units():
    from workflow.risk_team_document_compare_workflow.flow import external_task
    unit = {'unit_id': 'g-U1', 'label': '적용대상', 'summary': '규준의 적용 대상'}
    other = {**unit, 'unit_id': 'g-U2'}
    question, task = external_task('모의 규준', unit, '이 규준은 금융투자회사에 적용한다.', '문서 전체 대사', [])
    assert 'search_document_ids' not in task and task['preferred_document_ids'] == []      # ordinary RAG over every external rule
    assert '이 규준은 금융투자회사에 적용한다.' in question and '문서 전체 대사' in question
    _, named = external_task('모의 규준', unit, '금융투자업규정에 따라 관리한다.', '문서 전체 대사', ['b', 'a'])
    assert named['search_document_ids'] == ['a', 'b'] and named['preferred_document_ids'] == []
    assert external_task('모의 규준', other, '본문', '요청', [])[1]['session_key'] != task['session_key']


def test_unknown_external_outcome_stops_with_partial_and_continue_finishes(tmp_path, tree):
    transport = DocTransport(silent_child=1)
    app = application(tmp_path, tree, transport)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규', 'u1')).json()
        assert first['status'] == 'partial' and first['stop_code'] == 'DOCUMENT_STOPPED_UNKNOWN_OUTCOME', first
        assert '결과를 알 수 없는 모델 호출' in first['answer']['text'] and '계속' in first['answer']['text']
        assert not any(s == 'workflow-unit_compare' for s in stages(transport))      # nothing sent after the unknown outcome
        count = len(transport.views)
        again = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규', 'u1')).json()
        assert again['answer'] == first['answer'] and len(transport.views) == count
        second = client.post('/v1/rag/ask', json=body('문서 대사: 계속', 'u2')).json()
        assert second['status'] == 'completed' and second['document_compare']['continuation_of'] == first['run_id'], second
        assert second['document_compare']['units'] >= 1


@pytest.mark.parametrize('rejected', [0, 1])
def test_narrowed_search_is_reverified_against_its_own_scope(tmp_path, tree3, rejected):
    """Successful and failed (reads only) narrowed searches pass the final re-verification."""
    transport = DocTransport(rejected_child=rejected)
    principal = {**PRINCIPAL, 'document_ids': ['inside', 'other', 'outside']}
    app = application(tmp_path, tree3, transport, principal)
    with TestClient(app) as client:
        value = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규', 'n%d' % rejected)).json()
        assert value.get('workflow_id') == DOCUMENT_WORKFLOW and value['status'] == 'completed', value
        count = len(transport.views)
        again = client.post('/v1/rag/ask', json=body('문서 대사: 모의내규', 'n%d' % rejected)).json()
        assert again['answer'] == value['answer'] and len(transport.views) == count
    from semantic_runtime.legal_agent import journal_storage
    folder = app.state.workflow_runtime.root / value['run_id']
    with journal_storage.connect(str(folder / 'journal.sqlite')) as db:
        tasks = [json.loads(r[0])['args']['task'] for r in db.execute("SELECT input_json FROM workflow_call WHERE kind='rag'")]
        results = [json.loads(r[0]) for r in db.execute("SELECT result_json FROM workflow_call WHERE kind='rag'")]
    assert [t['search_document_ids'] for t in tasks] == [['outside']]
    assert results[0]['status'] == ('failed' if rejected else 'completed')
