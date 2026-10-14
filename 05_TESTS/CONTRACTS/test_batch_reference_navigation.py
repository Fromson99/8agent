"""Synthetic original witnesses and shared legal_agent consumers; no model service."""
import json
import sqlite3
from types import SimpleNamespace
import pytest
from test_unit_fulltext_adaptive_read import unit_fts, ur, us, SourceRecall
from test_document_release import source
from test_bounded_source_main import settings
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.legal_agent.source_selection import select_sources
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
rel = pytest.importorskip('semantic_runtime.legal_agent.unit_relations')


@pytest.fixture
def connected(tmp_path, term_glossary, request):
    raw = source(tmp_path/'raw.sqlite', [
        ('d', '모의승인규정', ['제1조 승인', '① 긴급 승인 기준은 다음 각 호와 같다.',
            '1. 긴급 승인은 허용한다.', '2. 일반 승인은 제한한다.']),
        ('detail', '모의승인세칙', ['제2조 예외',
            getattr(request, 'param', '① 「모의승인규정」 제1조제1항에 따른 긴급 승인 예외는 다음 각 호와 같다.'),
            '1. 책임자 확인 후 승인한다.', '2. 정해진 보고를 한다.']),
        ('foreign', '비공개규정', ['제3조 비밀', '① 「모의승인규정」 제1조제1항에 따른 비밀 절차'])])
    with sqlite3.connect(raw) as db:
        for did in ('d', 'detail', 'foreign'):
            db.execute('DELETE FROM source_unit WHERE document_id=?', (did,))
            total = 2 if did == 'foreign' else 4
            nodes = [('0', None, 'kr_article', '제1조' if did == 'd' else '제2조' if did == 'detail' else '제3조', 0, total),
                     ('1', '0', 'circled', '①', 1, total)]
            if total == 4:
                nodes += [('2', '1', 'dot_number:1', '1.', 2, 3), ('3', '1', 'dot_number:1', '2.', 3, 4)]
            for uid, parent, family, surface, lo, hi in nodes:
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', (did, uid, parent,
                    json.dumps({'family': family, 'surface': surface, 'title': '', 'span': [lo, hi]}, ensure_ascii=False)))
    build_generation(raw, term_glossary, tmp_path/'built', serving=True)
    gen = tmp_path/'built/generation'
    unit_fts.build(gen, gen/'navigation', tmp_path/'index', workers=1)
    idx = unit_fts.UnitFulltextIndex(tmp_path/'index', json.loads((gen/'navigation/manifest.json').read_text()))
    app = app_for(tmp_path, gen, ScriptedTransport(), {**settings(), 'page_size': 1, 'max_read_chars': 80})
    p = app.state.pipeline
    p.term_agent.unit_fulltext = idx
    request = {'question': '긴급 승인 예외', 'document_ids': ['d', 'detail'], 'use_llm': False}
    try:
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d', 'detail']), runtime=tmp_path/'runtime') as session:
            yield session.sources, idx
    finally:
        p.store.close()


def initial(s):
    src = next(v for v in s.tools.sources.values() if v['document_id'] == 'd')
    h = rel.hit_for(s, src['id'], '2')
    recall = SourceRecall(s)
    recall.discover = lambda: ([src['id']], {'discovery_mode': 'structure', 'routes': {}, 'unit_hits': [h]})
    record = recall.prepare()
    return record, src['id']


def decision(data, action='SKIP'):
    return {'decisions': [{'id': g['id'], 'action': action, 'scopes': [], 'reason': '이번 질문의 조사 범위에 따른 선택', 'applicability':('UNDETERMINED' if action=='DEFER' else 'APPLIES' if action=='FOLLOW' else 'DOES_NOT_APPLY'),'applicability_reason':'이번 질문은 승인 기준이며 단순 인용 문서 전체는 추가 근거로 필요하지 않음'} for g in data['groups']], 'needs_more': False}


def test_reverse_links_are_grouped_with_verified_witnesses_and_closed_scopes(connected):
    s, _ = connected
    rec, sid = initial(s)
    groups, statuses, limits, unresolved = rel.catalog(s, [sid], {'U1': rec['unit_reads'][0]}, set())
    group = next(g for g in groups if g['target']['document_id'] == 'detail')
    assert group['direction'] == 'INCOMING'
    assert group['connections'][0]['witness'].startswith('① 「모의승인규정」')
    assert 'subtree:1' in group['offers'] and 'subtree:0' in group['offers']
    assert not any(g['target']['document_id'] == 'foreign' for g in groups)
    assert statuses[0]['status'] == 'VERIFIED_LINKS' and not limits


def test_follow_reads_only_chosen_paragraph_and_review_receives_it(connected):
    s, _ = connected
    rec, sid = initial(s)
    phases = []
    def invoke(system, data, schema, phase, timeout):
        phases.append(phase)
        if phase == 'source-unit-triage':
            return {'issues': ['예외'], 'choices': [{'id': data['units'][0]['id'], 'scope': 'exact:2', 'status':'ADOPT','reason': '실제 원칙을 먼저 읽음'}], 'needs_search': False}
        if phase.startswith('source-reference-batch'):
            value = decision(data)
            if data['round'] == 1:
                chosen = next(g for g in data['groups'] if g['target']['document_id'] == 'detail')
                next(d for d in value['decisions'] if d['id'] == chosen['id']).update(action='FOLLOW',applicability='APPLIES', scopes=['subtree:1'])
            return value
        assert any('책임자 확인' in v['text'] and '정해진 보고' in v['text'] for v in data['sources'])
        assert any('제2조 예외' in v['text'] for v in data['sources'])  # governing heading retained
        return {'issues': [], 'choices': [], 'needs_search': False}
    out = select_sources('긴급 승인 예외', rec, invoke, remaining_seconds=120, session=s)
    assert out['status'] == 'complete' and len(out['final_ids']) == 2
    assert len(phases) == 4 and phases[1:3] == ['source-reference-batch-1', 'source-reference-batch-2']
    assert any(scope['offer']['id'] == 'subtree:1' for scope in out['read_scopes'])
    detail = next(v for v in out['selected_originals'] if v['document_id'] == 'detail')
    assert '책임자 확인' in detail['text'] and detail['article_complete'] is False
    assert {e['source_id'] for e in out['selected_evidence']} == set(out['final_ids'])


def test_skip_keeps_related_sources_unread_and_reason_is_recorded(connected):
    s, _ = connected
    rec, sid = initial(s)
    def invoke(system, data, schema, phase, timeout):
        if phase.startswith('source-reference-batch'):
            return decision(data)
        return {'issues': [], 'choices': ([{'id': data['units'][0]['id'], 'scope': 'exact:2', 'status':'ADOPT','reason': '원칙 확인'}] if phase.endswith('triage') else []), 'needs_search': False}
    out = select_sources('원칙', rec, invoke, remaining_seconds=120, session=s)
    assert out['final_ids'] == [sid] and out['reference_navigation']['actions'] == []
    assert out['reference_navigation']['batches'][0]['decision']['decisions'][0]['reason']


def test_defer_remains_pending(connected):
    s, _ = connected
    s.profile.setdefault('candidate_navigation',{})['allow_unresolved_completion']=False
    rec, sid = initial(s)
    def invoke(system, data, schema, phase, timeout):
        if phase.startswith('source-reference-batch'):
            return decision(data, 'DEFER')
        return {'issues': [], 'choices': ([{'id': data['units'][0]['id'], 'scope': 'exact:2', 'status':'ADOPT','reason': '원칙 확인'}] if phase.endswith('triage') else []), 'needs_search': False}
    out = select_sources('예외', rec, invoke, remaining_seconds=120, session=s)
    assert out['status'] == 'pending' and not out['needs_fulltext']
    assert out['next_action'] == 'CONTINUE_REFERENCES'


def test_no_verified_links_does_not_create_a_model_turn(connected):
    s, _ = connected
    rec, sid = initial(s)
    s.scope = ['d']
    groups, statuses, limits, unresolved = rel.catalog(s, [sid], {}, set())
    assert groups == [] and statuses[0]['status'] == 'NO_VERIFIED_LINKS_IN_CURRENT_SCOPE_AND_INDEX'
    calls = []
    def invoke(*args): calls.append(args);raise AssertionError('no reference model call expected')
    result = rel.navigate('승인', s, {'U1': rec['unit_reads'][0]}, invoke,
        read_state={'count': 0, 'chars': 0}, seconds_left=lambda:120, max_context_chars=80000)
    assert calls == [] and result['batches'][0]['model_called'] is False


def test_forged_reference_witness_is_rejected(connected, monkeypatch):
    s, _ = connected
    rec, sid = initial(s)
    db = s.tools.db
    class Changed:
        def execute(self, sql, args):
            rows = db.execute(sql, args).fetchall()
            ref = json.loads(rows[0][0]);ref['source_text_sha256'] = 'forged'
            return SimpleNamespace(fetchall=lambda:[(json.dumps(ref),)])
    monkeypatch.setattr(s.tools, 'db', Changed())
    with pytest.raises(ContractError, match='witness mismatch'):
        rel.catalog(s, [sid], {}, set())


@pytest.mark.parametrize('change', ['unoffered', 'skip_read', 'missing_decision', 'duplicate'])
def test_reference_choices_cannot_escape_closed_group_contract(connected, change):
    s, _ = connected
    rec, sid = initial(s)
    groups, _, _, _ = rel.catalog(s, [sid], {}, set())
    offered = {'R1': groups[0]}
    v = {'decisions': [{'id':'R1','action':'FOLLOW','scopes':['subtree:1'],'reason':'확인','applicability':'APPLIES','applicability_reason':'원문 관계 적용'}], 'needs_more':False}
    if change == 'unoffered':v['decisions'][0]['scopes'] = ['subtree:999']
    if change == 'skip_read':v['decisions'][0]['action'] = 'SKIP'
    if change == 'missing_decision':v['decisions'] = []
    if change == 'duplicate':v['decisions'] *= 2
    with pytest.raises((ContractError,ProposalError)):rel.validate(v, offered)


def test_empty_menu_schema_has_no_empty_enum():
    value = rel.schema({})
    assert value['properties']['decisions']['maxItems'] == 0
    assert '"enum": []' not in json.dumps(value) and value['properties']['decisions']['minItems']==0


def test_grouping_collapses_duplicate_edges_without_per_edge_model_calls(connected, monkeypatch):
    s, _ = connected
    rec, sid = initial(s)
    db = s.tools.db
    class Duplicate:
        def execute(self, sql, args):
            rows = db.execute(sql,args).fetchall()
            return SimpleNamespace(fetchall=lambda:rows*20)
    monkeypatch.setattr(s.tools, 'db', Duplicate())
    groups, _, _, _ = rel.catalog(s, [sid], {}, set())
    assert len(groups) == 1 and len(groups[0]['connections']) == 20
    card = rel.menu(groups[0], 'R1')
    assert len(card['connections']) == 8 and card['omitted_connections'] == 12


def test_related_originals_reach_shared_assessment_after_confirmation(connected, tmp_path):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from test_memory_runtime_v2 import command
    from test_legal_agent_double_harness import ROOT, wire
    from test_unified_legal_agent import ok
    import importlib.util
    s, idx = connected
    # The fixture layout is pinned here; no inference from a selected release.
    gen = tmp_path/'built/generation'
    class Transport(ScriptedTransport):
        def send_once(self, *, body, ticket):
            v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
            if phase in ('source-unit-triage','source-unit-review'):
                self.phases.append(phase)
                if phase==self.fail:raise RuntimeError('injected source selection failure')
                choices=[]
                if phase=='source-unit-triage':
                    row=next(r for r in v['units'] if v['laws'][r['law']]=='모의승인규정' and any(o[0]=='exact:2' for o in r['read_options']))
                    choices=[{'id':row['id'],'scope':'exact:2','status':'ADOPT','reason':'긴급 승인 원칙 확인'}]
                else:assert any('책임자 확인' in x['text'] for x in v['sources'])
                if 'status' not in body['response_format']['json_schema']['schema']['properties']['choices']['items']['properties']:
                    for choice in choices:choice.pop('status',None)
                return wire({'issues':['긴급 승인 예외'],'choices':choices,'needs_search':False})
            if phase.startswith('source-reference-batch'):
                self.phases.append(phase)
                value=decision(v)
                if v['round']==1:
                    for group in v['groups']:
                        if group['target']['document_id']=='detail':
                            next(d for d in value['decisions'] if d['id']==group['id']).update(action='FOLLOW',applicability='APPLIES',scopes=['subtree:1'])
                return wire(value)
            if phase in ('memory-assess','memory-compose'):
                assert any('책임자 확인' in x['text'] and x['document_id']=='detail' for x in v['sources'])
            return super().send_once(body=body,ticket=ticket)
    source_code=__import__('pathlib').Path(rel.__file__).resolve().parents[3]
    if source_code==ROOT.resolve():code=ROOT
    else:
        spec=importlib.util.spec_from_file_location('relation_package',ROOT/'06_TOOLS/EXPERIMENTS/adr_0622/package.py')
        package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
        code=package.materialize(source_code,tmp_path/'consumer-code')
    t=Transport();t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='긴급 승인 예외',queries=['긴급 승인'],facts=[])
    app=create_app(tmp_path/'app',gen,contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t,
        memory_identity=lambda r:{'user_id':'u','team_id':'risk_team','document_ids':['d','detail']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    try:
        with TestClient(app) as client:
            body={'question':'긴급 승인 예외','session_id':'s','request_id':'r1'}
            first=ok(client.post('/v1/rag/ask',json=body));gid=first['question_id']
            t.command=command('EXPERIENCE_CONFIRM',target=gid)
            stored=ok(client.post('/v1/rag/ask',json={**body,'request_id':'r2','question':'기억해줘'}));kid=stored['experience_id']
            # Wiki administration now uses separate AD contracts. Verify the
            # changed source path through confirmation and exact reuse here.
            t.command=command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,task='긴급 승인 예외',queries=['긴급 승인'],facts=[])
            reused=ok(client.post('/v1/rag/ask',json={**body,'session_id':'new','request_id':'r3'}))
            assert reused['status'] in ('READY','REUSED') and 'COMPOSE' in reused['executed']
            if reused['status']=='READY':assert 'READ' in reused['executed'] and 'SELECT' in reused['executed']
            else:assert reused['executed']==['COMPOSE']
            # A fresh HTTP retry opens a fresh source session. Accepted selection
            # and reference originals must restore from the durable checkpoint.
            t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='별도 조건의 긴급 승인 예외',queries=['긴급 승인'],facts=[])
            interrupted={**body,'question':'별도 조건의 긴급 승인 예외','session_id':'resume','request_id':'resume-select'}
            t.fail='source-unit-review'
            assert client.post('/v1/rag/ask',json=interrupted).status_code==502
            triages=t.phases.count('source-unit-triage')
            relations=sum(p.startswith('source-reference-batch') for p in t.phases)
            t.fail=None;resumed=ok(client.post('/v1/rag/ask',json=interrupted))
            assert resumed['status']=='READY'
            assert t.phases.count('source-unit-triage')==triages
            assert sum(p.startswith('source-reference-batch') for p in t.phases)==relations
    finally:app.state.pipeline.store.close()


def test_bounded_path_adopts_new_reference_source_with_exact_evidence(connected, tmp_path):
    from test_bounded_source_main import Transport as BaseTransport
    from test_legal_agent_double_harness import wire
    from semantic_runtime.legal_agent.source_bundle import validate_current
    _, idx=connected
    class Transport(BaseTransport):
        def send_once(self, *, body, ticket):
            v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
            if phase in ('source-unit-triage','source-unit-review'):
                return wire({'issues':['예외'],'choices':([{'id':v['units'][0]['id'],'scope':'subtree:0','status':'ADOPT','reason':'명시 조항 원문을 확인'}] if phase.endswith('triage') else []),'needs_search':False})
            if phase.startswith('source-reference-batch'):
                value=decision(v)
                if v['round']==1:
                    for group in v['groups']:
                        if group['target']['document_id']=='detail':
                            next(d for d in value['decisions'] if d['id']==group['id']).update(action='FOLLOW',applicability='APPLIES',scopes=['subtree:1'])
                return wire(value)
            return super().send_once(body=body,ticket=ticket)
    app=app_for(tmp_path/'bounded',tmp_path/'built/generation',Transport(),settings())
    p=app.state.pipeline;p.term_agent.unit_fulltext=idx
    request={'question':'모의승인규정 제1조의 긴급 승인 예외는?', 'document_ids':['d','detail'], 'use_llm':True}
    try:
        with p.term_agent.open_session(request,query=p.plan(request['question'],['d','detail']),runtime=tmp_path/'bounded-runtime') as session:
            retrieved=session.investigate()
            assert not session.limitations,session.limitations
            result=session.source_selection_record
            assert len(result['first_ids'])==1 and len(result['recovered_ids'])==1
            session.select({'retrieval':retrieved})
            assert any('책임자 확인' in x['text'] for x in session.packed['contexts'])
            bundle=session.build_bundle()
            validate_current(session.work,{'assembly':{'term_agent':{'source_bundle':bundle}}},session.sources.store)
            assert {x['document_id'] for x in bundle['sources']}=={'d','detail'}
    finally:p.store.close()
