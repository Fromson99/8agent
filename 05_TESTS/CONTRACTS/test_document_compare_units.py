"""문서 대사 = the ordinary 대사 run once per reading group (user 2026-11-13).

"문서대사는 일반대사를 그냥 그 구조단위로 실행한 거 아닌가 / 싹다 교체해주고 일반대사의 한도를 좀 조정해서 필수만 좀
들고오고 보수적으로 최대한 1시간 정도에 끝내게". Real API under the selected profile; synthetic originals; the ordinary
question stages and the 대사 stages are scripted (test_compare_general_flow.Both).
Run against a code root with this design: run_tests.py --code-root <staged code>.
"""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dcu_general', HERE / '05_TESTS/CONTRACTS/test_compare_general_flow.py')
general = importlib.util.module_from_spec(spec); spec.loader.exec_module(general)
points = general.points
tree = points.tree
BODY = {**points.BODY, 'question': '문서 대사: 모의내규'}
DOCUMENT = 'risk_team_document_compare_workflow'


class Pick(general.Both):
    """The 대사 script plus the group pick: each internal article takes its nearest candidate and one search word.

    bad: 'once' | 'always' -> the pick names another article's candidate (checked, corrected once, then the fallback)."""

    def __init__(self, pair='PAIRED', bad=None):
        super().__init__(pair)
        self.bad, self.picks = bad, []

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        from test_legal_agent_double_harness import wire
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        stage = view.get('source_stage') or view['phase']
        if stage != 'workflow-pick':
            return super().send_once(body=body, ticket=ticket)
        self.phases.append(stage)
        self.picks.append(view)
        ids = [a['id'] for a in view['internal_articles']]
        rows = []
        for n, aid in enumerate(ids):
            own = [c['id'] for c in view['candidates'].get(aid, [])][:1]
            if self.bad and n == 0:
                other = [c['id'] for k, v in view['candidates'].items() if k != aid for c in v][:1] or ['X']
                own = other
            rows.append({'internal_id': aid, 'basis': 'INFERRED', 'candidates': own,
                         'documents': [d['id'] for d in view['documents']][:1], 'search_words': ['승인'], 'reason': '승인 기준'})
        if self.bad == 'once':
            self.bad = None
        return wire({'articles': rows})


def module(app, workflow, name):
    definition = app.state.workflow_runtime.registry.resolve(workflow, None, 'risk_team')
    return sys.modules[definition.entrypoint.__module__.rsplit('.', 1)[0] + '.' + name]


def child_state(app, run_id):
    runtime = app.state.workflow_runtime
    row = sys.modules[type(runtime).__module__]._saved_state(runtime.root / run_id / 'journal.sqlite')
    return json.loads(row['checkpoint_json']), json.loads(row['request_json'])


def ask(client, question, request_id):
    response = client.post('/v1/rag/ask', json={**BODY, 'question': question, 'request_id': request_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_each_reading_group_is_one_ordinary_comparison(tmp_path, tree, monkeypatch):
    transport = Pick('PAIRED')
    app = points.application(tmp_path, tree, transport)
    unit = module(app, 'risk_team_compare_workflow', 'unit')
    original, looked = unit.neighbours, []

    def recorded(ctx, sid, external):
        out = original(ctx, sid, external)
        looked.append((sid, out))
        return out
    monkeypatch.setattr(unit, 'neighbours', recorded)
    # The fixture's one internal article is "제1조 정의", whose links are not expanded; here they are, to run the
    # stored reference lookup on the real store.
    monkeypatch.setattr(unit, 'DEFINITIONS', __import__('re').compile('(?!)'))
    with TestClient(app) as client:
        value = ask(client, '문서 대사: 모의내규', 'd1')
        again = ask(client, '문서 대사: 모의내규', 'd1')
    assert value['workflow_id'] == DOCUMENT and value['status'] == 'completed', value.get('stop_code')
    summary = value['document_compare']
    total = summary['groups_total']
    assert total >= 1 and summary['groups_finished'] == total and summary['groups_waiting'] == 0
    phases = transport.phases
    # No document-only stages: each group pairs and compares as the ordinary 대사 does.
    assert 'workflow-group_read' not in phases and 'workflow-unit_compare' not in phases
    assert phases.count('workflow-concepts') == total, phases
    # Neither side is an ordinary question: the internal side is the group's text, the external side is found from it
    # (candidates, one pick per group, reads). A group is not a chat message: no question split either (MAIN226).
    assert phases.count('request-entry') == 0 and phases.count('workflow-pick') == total, phases
    assert not any('split' in p for p in phases), phases
    shown = transport.picks[0]
    assert [a['heading'] for a in shown['internal_articles']] and all(shown['candidates'].values()), shown
    assert any('모의승인규정' in c['document'] for v in shown['candidates'].values() for c in v)
    # Without vectors the candidates come from a title search; a hit is its stored article (excerpt shown, links looked up).
    assert all(c['found_by'] == 'SEARCH' for v in shown['candidates'].values() for c in v)
    assert any(c['excerpt'] for v in shown['candidates'].values() for c in v)
    # Their links were looked up in the stored reference index (the fixture's externals cite nothing external).
    assert looked and all(out == [] for _, out in looked), looked
    # The pairing is told which external article was picked (and read) for which internal article (ADR-1529).
    concept_view = next(v for stage, v in transport.seen if stage == 'workflow-concepts')
    article = shown['internal_articles'][0]
    first = shown['candidates'][article['id']][0]
    assert concept_view['internal_picks'] == [{'internal': article['heading'], 'external': [first['document'] + ' ' + first['heading']]}]
    run = summary['group_runs'][0]
    assert run['status'] == 'done' and run['rows'] >= 1 and run['seconds'] >= 150
    state, request = child_state(app, run['run_id'])
    assert request['workflow_id'] == 'risk_team_compare_workflow' and request['document_unit']['document_id'] == 'inside'
    assert state['document_unit']['status'] == 'read' and state['document_unit']['evidence_ids']
    assert not state.get('rag_attempts')
    pick = state['external_pick']
    assert pick['done'] and pick['read'] >= 1 and pick['vector']['status'] == 'NONE' and pick['picks'][0]['basis'] == 'INFERRED'
    # Only the picked candidates are read; the search words are for an article whose pick took no candidate.
    assert all(r['why'].startswith('PICK ') for r in pick['reads']) and pick['queries'] == []
    assert pick['candidates_by']['SEARCH'] == pick['candidates']
    # The special-rule search of the question 대사 is not run for a group (its candidates are in the pick).
    assert 'special_external' not in state
    assert set(state['context_by_side']['external']) and '모의승인규정' in ' '.join(pick['documents'])
    # The group's table (exact quotations) is in the document answer.
    text = value['answer']['text']
    assert '문서 대사 결과' in text and '1. ' in text and '<blockquote' in text
    assert '내규 조문별 근거 외규' in text and '대응 외규 문서' in text and run['documents']
    assert again['answer'] == value['answer']


def test_a_group_runs_under_the_lighter_unit_policy(tmp_path, tree):
    transport = Pick('INTERNAL_ONLY')
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        value = ask(client, '문서 대사: 모의내규', 'd2')
    run = value['document_compare']['group_runs'][0]
    state, _ = child_state(app, run['run_id'])
    concept = state['scope']['issues'][0]['concept']
    # No follow-up question for an unpaired row ("필수만"); the external side was asked once.
    assert concept['pair_status'] == 'INTERNAL_ONLY' and concept['followup'] == {'side': 'external', 'status': 'NOT_ASKED', 'reason': 'LIMIT'}
    assert transport.phases.count('request-entry') == 0
    runtime = app.state.workflow_runtime
    from semantic_runtime.legal_agent import journal_storage
    db = journal_storage.connect(runtime.root / run['run_id'] / 'journal.sqlite')
    try:
        payload = db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_EXECUTION_POLICY'").fetchone()[0]
    finally:
        db.close()
    policy = json.loads(payload)['policy']
    assert policy['version'] == 'comparison-document-unit-v2' and policy['wall_seconds'] == run['seconds'] <= 600
    assert policy['max_model_attempts'] == 30 and policy['followups_per_side'] == 0


def test_groups_without_enough_time_wait_and_continue_runs_only_them(tmp_path, tree, monkeypatch):
    transport = Pick('PAIRED')
    app = points.application(tmp_path, tree, transport)
    import semantic_runtime.basis_links.reading_groups as groups
    # Two reading groups from the one internal article (its text split by code points).
    monkeypatch.setitem(groups.LIMITS, 'max_chars', 20)
    flow = module(app, DOCUMENT, 'flow')
    original = flow.allot
    calls = []

    def first_only(ctx, policy, left, parallel):
        calls.append(left)
        return original(ctx, policy, left, parallel) if len(calls) == 1 else None
    monkeypatch.setattr(flow, 'allot', first_only)
    with TestClient(app) as client:
        first = ask(client, '문서 대사: 모의내규', 'c1')
        summary = first['document_compare']
        assert summary['groups_total'] >= 2, summary
        assert first['status'] == 'partial' and first['resume_available'] and summary['groups_finished'] == 1
        assert summary['groups_waiting'] == summary['groups_total'] - 1
        assert '시작하지 않았습니다' in first['answer']['text'] and '계속' in first['answer']['text']
        mark = transport.phases.count('workflow-concepts')
        monkeypatch.setattr(flow, 'allot', original)
        second = ask(client, '문서 대사: 계속', 'c2')
        assert second['status'] == 'completed', second['document_compare']
        assert second['document_compare']['continuation_of'] == first['run_id']
        # Only the groups that had not started ran.
        assert transport.phases.count('workflow-concepts') - mark == summary['groups_total'] - 1
        count = len(transport.phases)
        third = ask(client, '문서 대사: 계속', 'c3')
        assert third['document_compare']['selection']['status'] == 'ALREADY_COMPLETE' and len(transport.phases) == count


def test_several_groups_run_at_once_and_all_finish(tmp_path, tree, monkeypatch):
    transport = Pick('PAIRED')
    app = points.application(tmp_path, tree, transport)
    import semantic_runtime.basis_links.reading_groups as groups
    monkeypatch.setitem(groups.LIMITS, 'max_chars', 8)
    with TestClient(app) as client:
        value = ask(client, '문서 대사: 모의내규', 'p1')
    summary = value['document_compare']
    assert summary['groups_total'] >= 3 and summary['groups_finished'] == summary['groups_total'], summary
    assert value['status'] == 'completed' and transport.phases.count('workflow-concepts') == summary['groups_total']
    runs = [r['run_id'] for r in summary['group_runs']]
    assert len(set(runs)) == len(runs)                    # one ordinary 대사 run (own journal) per group
    # All groups are parts of the one internal article: the first picks from the whole article, the others read
    # what it picked (one pick call; their state names it as shared).
    assert transport.phases.count('workflow-pick') == 1, transport.phases
    first, *later = [child_state(app, r['run_id']) for r in summary['group_runs']]
    shared = list(dict.fromkeys(r['source_id'] for r in first[0]['external_pick']['pairs'] if r['source_id']))
    assert shared and 'shared_pick' not in first[1]['document_unit']
    assert all(request['document_unit']['shared_pick'] == shared and state['external_pick']['shared_from'] == len(shared)
               for state, request in later)
    assert all('%d. ' % (n + 1) in value['answer']['text'] for n in range(summary['groups_total']))


def test_a_pick_that_does_not_fit_reads_the_nearest_candidates(tmp_path, tree):
    transport = Pick('PAIRED', bad='always')
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        value = ask(client, '문서 대사: 모의내규', 'k1')
    run = value['document_compare']['group_runs'][0]
    state, _ = child_state(app, run['run_id'])
    pick = state['external_pick']
    # The pick named another article's candidate twice (first answer + one correction): the nearest two are read.
    assert transport.phases.count('workflow-pick') == 2 and pick['pick_failed'] == 'WORKFLOW_REPAIR_EXHAUSTED'
    assert pick['read'] >= 1 and run['status'] == 'done'


def test_document_names_keep_the_rule_an_annex_belongs_to():
    from workflow.risk_team_compare_workflow.unit import document_name
    assert document_name('external > risk_team > law > 금융투자업규정시행세칙 > 별표서식 > [별표 10] 계량항목 산정기준') \
        == '금융투자업규정시행세칙 [별표 10] 계량항목 산정기준'
    assert document_name('external > risk_team > law > 금융투자업규정') == '금융투자업규정'
    assert document_name('모의승인규정') == '모의승인규정' and document_name(None) == ''


def test_time_share_is_bounded_and_none_below_the_minimum():
    from types import SimpleNamespace
    import time
    from workflow.risk_team_document_compare_workflow import flow
    policy = {'unit_seconds': {'min': 150, 'max': 600}, 'report_seconds': 90}
    at = lambda seconds: SimpleNamespace(context=SimpleNamespace(deadline=time.monotonic() + seconds))
    assert flow.allot(at(3600), policy, 1, 3) == 600                  # one group left: capped at the maximum
    assert 328 <= flow.allot(at(3600), policy, 32, 3) <= 330         # 3510 s x 3 / 32 groups = 329
    assert flow.allot(at(1000), policy, 100, 3) == 150               # never below the minimum while it fits
    assert flow.allot(at(200), policy, 1, 3) is None                 # less than the minimum left: waits for "계속"
    assert flow.allot(at(400), policy, 1, 3) <= 310                  # never past this run's end less the report time


def test_parallel_setting_is_checked(monkeypatch):
    from workflow.risk_team_document_compare_workflow import flow
    from workflow.contracts import WorkflowError
    assert flow.workers({'parallel_groups': 3}) == 3
    monkeypatch.setenv('GENOS_DOCUMENT_COMPARE_PARALLEL', '1')
    assert flow.workers({'parallel_groups': 3}) == 1
    monkeypatch.setenv('GENOS_DOCUMENT_COMPARE_PARALLEL', '9')
    with pytest.raises(WorkflowError):
        flow.workers({'parallel_groups': 3})


def _unit(**changes):
    node = {'document_id': 'inside', 'unit_id': '0', 'source_id': None,
            'read_segments': [{'block_id': '0', 'start_cp': 0, 'end_cp': 10}], 'read_label': '제1조'}
    return {'document_id': 'inside', 'document_name': '모의내규', 'group_id': 'a' * 64, 'title': '제1조',
            'path': [], 'node': node, 'seconds': 300, **changes}


@pytest.mark.parametrize('case,ok', [
    ('valid', True), ('outside_scope', False), ('extra_key', False), ('other_node_document', False),
    ('bad_segment', False), ('too_short', False), ('other_input', False), ('blank_question', False), ('no_input', True),
    ('shared', True), ('shared_bad', False), ('shared_many', False)])
def test_group_input_is_checked(case, ok):
    from workflow.risk_team_compare_workflow.unit import normalize
    from workflow.contracts import WorkflowError
    principal = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['inside', 'outside']}
    unit = {'valid': _unit(), 'outside_scope': _unit(document_id='elsewhere'), 'extra_key': {**_unit(), 'more': 1},
            'other_node_document': _unit(node={**_unit()['node'], 'document_id': 'outside'}),
            'bad_segment': _unit(node={**_unit()['node'], 'read_segments': [{'block_id': '0', 'start_cp': 5, 'end_cp': 5}]}),
            'too_short': _unit(seconds=10), 'shared': _unit(shared_pick=['s1', 's2']), 'shared_bad': _unit(shared_pick=[1]),
            'shared_many': _unit(shared_pick=['s%d' % n for n in range(13)])}.get(case, _unit())
    body = {'question': '「모의내규」 제1조에 대응하는 외규는?', 'session_id': 's', 'request_id': 'r', 'input': {'document_unit': unit}}
    if case == 'other_input':
        body['input'] = {'mode': 'x'}
    if case == 'blank_question':
        body['question'] = '대사:  '
    if case == 'no_input':
        body.pop('input')
    if ok:
        value = normalize(body, principal)
        assert value == ({} if case == 'no_input' else {'document_unit': unit})
    else:
        with pytest.raises(WorkflowError):
            normalize(body, principal)


def test_unit_policy_caps_the_seconds_and_leaves_ordinary_runs_alone():
    from workflow.runtime import unit_definition
    from workflow.registry import Definition
    manifest = {'execution_policy': {'version': 'ordinary', 'wall_seconds': 1800},
                'unit_execution_policy': {'version': 'unit', 'wall_seconds': 600}}
    definition = Definition(manifest, lambda ctx: None)
    assert unit_definition(definition, {'question': 'q'}) is definition
    used = unit_definition(definition, {'document_unit': {'seconds': 900}}).manifest['execution_policy']
    assert used == {'version': 'unit', 'wall_seconds': 600}
    assert unit_definition(definition, {'document_unit': {'seconds': 200}}).manifest['execution_policy']['wall_seconds'] == 200
    assert definition.manifest['execution_policy']['version'] == 'ordinary'


class _Retriever:
    """Nearest-first rows: the nearest external articles, or the given ones in the ranking order."""

    def __init__(self, nearest, ranking=()):
        self.nearest, self.ranking, self.calls = nearest, list(ranking), []

    def search(self, question, documents, source_ids=None):
        self.calls.append(source_ids)
        rows = self.nearest if source_ids is None else [x for x in self.ranking if x in source_ids]
        return {'rows': [{'DOC_ID': 'ext', 'SOURCE_ID': x, 'DISTANCE': n / 10} for n, x in enumerate(rows)]}


SOURCES = {
    'v1': ('금융투자업규정', '제3-48조(외국환포지션의 한도)', '외국환포지션의 한도는 자기자본의 50%로 한다.'),
    'v2': ('금융투자업규정', '부칙 제2조(경과조치)', '이 규정 시행 당시 외국환포지션은 종전 규정에 따른다.'),
    'v3': ('금융투자업규정 별지서식', '[별지 제5호] 외국환포지션 보고서', '보고서 양식'),
    'v4': ('금융투자업규정시행세칙', '제2-15조(외국환포지션 산정)', '외국환포지션은 다음과 같이 산정한다.'),
    'l1': ('금융투자업규정', '제3-24조의4(종합금융투자사업자 특례)', '종합금융투자사업자의 외국환 한도는 다음과 같다.'),
    'l2': ('금융투자업규정', '제3-49조(외국환포지션 보고)', '외국환포지션을 매월 보고한다.'),
    'l3': ('금융투자업규정', '부칙 제5조', '경과조치'),
    'l4': ('외국환거래규정', '제2-9조의2(포지션 한도)', '외국환 포지션 한도를 정한다.'),
}


def _fake(nearest, ranking=(), picked=None, search=None):
    """A group with two internal articles (a definitions article and a limit article) on a fake source session."""
    from types import SimpleNamespace as S
    sources = {sid: {'document_id': 'ext', 'unit_id': sid, 'document_name': 'external > law > ' + d, 'heading': h, 'text': t}
               for sid, (d, h, t) in SOURCES.items()}
    internal = [{'evidence_id': 'e1', 'source_id': 'i1', 'text': '이 세칙에서 사용하는 용어의 뜻은 다음과 같다.', 'metadata': {'heading': '제1-2조(정의)'}},
                {'evidence_id': 'e2', 'source_id': 'i2', 'text': '외국환포지션 한도는 자기자본의 40%로 한다.', 'metadata': {'heading': '제11-6조(외국환 포지션 한도)'}}]
    evidence = list(internal)
    calls = []

    def source_call(call, call_id):
        calls.append(call)
        if call['operation'] == 'read_node':
            eid = 'x' + call['args']['node']['source_id']
            evidence.append({'evidence_id': eid, 'source_id': call['args']['node']['source_id'], 'text': 'x' * 100, 'metadata': {}})
            return {'status': 'OK', 'evidence_ids': [eid]}
        return {'status': 'OK', 'items': (search or {}).get(call['args']['query'], [])}

    def decide(phase, data, schema, instructions, validate):
        rows = [{'internal_id': a['id'], 'basis': 'INFERRED', 'reason': 'r',
                 'candidates': [c['id'] for c in data['candidates'][a['id']] if c['heading'] in (picked or {}).get(a['id'], [])],
                 'documents': [d['id'] for d in data['documents']], 'search_words': ['용어의 정의', '외국환 보고', '한도']}
                for a in data['internal_articles']]
        value = {'articles': rows}
        validate(value)
        return value
    session = S(tools=S(sources=sources), handle=lambda kind, value: value,
                node=lambda did, uid, sid=None: {'document_id': did, 'unit_id': uid, 'source_id': sid},
                matcher=S(initial_vector=_Retriever(nearest, ranking) if nearest else None, documents={'ext': 'external > law > 금융투자업규정'}))
    port = S(session=session, all_scope=['in', 'ext'], categories={'in': 'internal', 'ext': 'external'})
    ctx = S(rag=S(port=port, source_call=source_call, evidence=lambda: evidence), model=S(decide=decide),
            repo=S(save=lambda state: None), request={'document_unit': {'document_name': '위험관리기준시행세칙'}})
    state = {'document_unit': {'evidence_ids': ['e1', 'e2']}}
    return ctx, state, calls


def test_links_and_special_articles_are_candidates_not_reads(monkeypatch):
    from workflow.risk_team_compare_workflow import unit
    links = {'v1': [('l1', 'CITES'), ('l2', 'CITED_BY'), ('l3', 'CITES')], 'v4': [('l4', 'CITES')]}
    monkeypatch.setattr(unit, 'neighbours', lambda ctx, sid, external: links.get(sid, []))
    ctx, state, calls = _fake(['v2', 'v1', 'v3', 'v4'], ranking=['l4', 'l2', 'l1'])
    state['external_pick'] = {'reads': [], 'skipped': [], 'picks': [], 'queries': []}
    found = unit.candidates(ctx, state, unit.internal_articles(ctx, state))
    definitions, limit = found['A1'], found['A2']
    # Supplementary provisions and forms are not candidates; nothing is read or searched while collecting them.
    assert all('부칙' not in c['heading'] and '별지' not in c['heading'] for v in found.values() for c in v) and calls == []
    # A definitions article does not take the articles its candidates are linked with.
    assert [c['found_by'] for c in definitions] == ['VECTOR', 'VECTOR']
    # The other article: the nearest, then the linked ones — the special article first, the rest nearest first.
    assert [c['heading'][:9] for c in limit] == ['제3-48조(외국', '제2-15조(외국', '제3-24조의4(', '제2-9조의2(포', '제3-49조(외국']
    assert [c['found_by'].split(':')[0] for c in limit] == ['VECTOR', 'VECTOR', 'LINK', 'LINK', 'LINK']
    assert '금융투자업규정 제3-48조' in limit[2]['found_by'] and limit[2]['excerpt']
    assert state['external_pick']['candidates_by'] == {'VECTOR': 4, 'SEARCH': 0, 'LINK': 3}


def test_only_picked_candidates_are_read_and_words_need_a_title_match(monkeypatch):
    from workflow.risk_team_compare_workflow import unit, retrieval
    monkeypatch.setattr(unit, 'neighbours', lambda ctx, sid, external: [('l1', 'CITES')] if sid == 'v1' else [])
    monkeypatch.setattr(retrieval, 'team_facts', lambda ctx: ['회사는 증권회사이다.'])
    hit = lambda sid: {'node': {'document_id': 'ext', 'unit_id': sid, 'source_id': sid}, 'heading': SOURCES[sid][1],
                       'document_name': SOURCES[sid][0]}
    search = {'외국환 보고': [hit('v3'), hit('l2')], '한도': [hit('v4'), hit('l4')]}
    ctx, state, calls = _fake(['v1', 'v4'], picked={'A2': ['제3-24조의4(종합금융투자사업자 특례)', '제3-48조(외국환포지션의 한도)']},
                              search=search)
    unit.find_external(ctx, state)
    record = state['external_pick']
    reads = [c['args']['node']['source_id'] for c in calls if c['operation'] == 'read_node']
    # The linked special article is read because the pick chose it; nothing else from the candidates.
    assert reads[:2] == ['v1', 'l1'] and record['picks'][1]['found_by'] == ['VECTOR', 'LINK']
    # The definitions article took no candidate: its words are searched (not the generic "용어의 정의"); a hit is read
    # only when its title shares a content word and it is not a form.
    searched = [c['args']['query'] for c in calls if c['operation'] == 'search_sources']
    assert '용어의 정의' not in searched and '외국환 보고' in searched
    assert reads[2:] == ['l2', 'l4'] and record['queries'] == ['외국환 보고', '한도']
    assert record['read'] == 4 and set(state['context_by_side']['external']) == {'xl1', 'xv1', 'xl2', 'xl4'}
    # Each read is kept with the internal article it was taken for; the pairing sees them per article.
    assert [(r['internal'][:6], r['external'], r['evidence_ids']) for r in record['pairs']] == [
        ('제11-6조', '금융투자업규정 제3-48조(외국환포지션의 한도)', ['xv1']),
        ('제11-6조', '금융투자업규정 제3-24조의4(종합금융투자사업자 특례)', ['xl1']),
        ('제1-2조(', '금융투자업규정 제3-49조(외국환포지션 보고)', ['xl2']),
        ('제1-2조(', '외국환거래규정 제2-9조의2(포지션 한도)', ['xl4'])]
    from workflow.risk_team_compare_workflow import concepts
    from types import SimpleNamespace as S
    picks = concepts.internal_picks(S(request={'document_unit': {'group_id': 'g'}}), state)
    assert [p['internal'][:6] for p in picks] == ['제11-6조', '제1-2조('] and len(picks[0]['external']) == 2
    assert concepts.internal_picks(S(request={}), state) == []          # an ordinary question 대사: nothing added


def test_parts_of_one_article_share_the_first_parts_pick():
    from workflow.risk_team_document_compare_workflow.flow import families
    row = lambda label, *path: {'label': label, 'path': list(path)}
    groups = [{'group_id': 'a', 'rows': [row('제1-4조 용어의 정의')]},
              {'group_id': 'b', 'rows': [row('① (머리 문장)', '제1-4조 용어의 정의'), row('1.', '제1-4조 용어의 정의', '①')]},
              {'group_id': 'c', 'rows': [row('16.', '제1-4조 용어의 정의', '①')]},
              {'group_id': 'd', 'rows': [row('제2-1조 건전성비율'), row('제2-2조 특수관계인')]},      # two articles: alone
              {'group_id': 'e', 'rows': [row('제2장 유동성')]}]                                   # no article: alone
    assert families(groups) == {'b': 'a', 'c': 'a'}


def test_the_pairing_of_a_question_comparison_sees_what_each_answer_cited(tmp_path, tree):
    transport = general.Both('PAIRED')
    general.run(tmp_path, tree, transport)
    pairing = next(v for stage, v in transport.seen if stage == 'workflow-concepts')
    uses = pairing['side_uses']
    assert set(uses) == {'internal', 'external'}, uses
    assert all(u['point'] and u['articles'] for side in uses.values() for u in side), uses


def test_side_uses_and_answered_articles_come_from_the_answers_not_the_reads():
    from workflow.risk_team_compare_workflow import concepts, task_board
    e = lambda i, side, doc, head: {'evidence_id': i, 'side': side, 'document_id': doc, 'source_id': i,
                                    'metadata': {'document_name': 'external > law > ' + doc, 'heading': head}}
    by = {x['evidence_id']: x for x in (e('a1', 'external', '규정', '제1조 승인'), e('a2', 'external', '규정', '제9조 보고'),
                                         e('r1', 'external', '규정', '제3조 정의'), e('i1', 'internal', '내규', '제1조 승인'))}
    state = {'rag_results': {
        'external': {'side': 'external', 'bundle': {'claims': [{'text': '승인 후 보고한다.', 'evidence_ids': ['a1', 'a2']}],
                                                   'evidence_ids': ['a1', 'a2']}},
        'internal': {'side': 'internal', 'bundle': {'claims': [{'text': '승인한다.', 'evidence_ids': ['i1']}], 'evidence_ids': ['i1']}}},
        'rag_valid_results': {'external': [{'side': 'external', 'bundle': {'export_mode': 'READ_ORIGINALS', 'evidence_ids': ['r1'],
                                                                         'claims': [{'text': '정의', 'evidence_ids': ['r1']}]}}]}}
    uses = concepts.side_uses(state, by)
    assert uses == {'external': [{'point': '승인 후 보고한다.', 'articles': ['규정 제1조 승인', '규정 제9조 보고']}],
                    'internal': [{'point': '승인한다.', 'articles': ['내규 제1조 승인']}]}
    # An external only read (the read export) is not an answered article; one the answer cited is.
    assert task_board.answered_articles(state, by) == {('규정', '제1조 승인'), ('규정', '제9조 보고'), ('내규', '제1조 승인')}
