"""State/range boundaries using the real reader, immutable menus and checkpoints."""
from copy import deepcopy
import json
import pytest
from test_unit_fulltext_adaptive_read import tree, session, hit
from test_law_grouped_navigation import prepared, decide, enable
from semantic_runtime.legal_agent import law_navigation as ln, unit_reading as ur
from semantic_runtime.legal_agent import evidence_inventory as ei, investigation_chain as trail
from semantic_runtime.legal_agent import investigation_contracts as ic
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from jsonschema import validate, ValidationError


def investigation(native, uid='3'):
    s = native.sources; record = prepared(s)
    enable(s, investigation_control=True)
    record['unit_reads'] = ur.acquire_batch(s,[hit(native, uid)],record['read_state'])
    record['unit_hits'] = [hit(native, uid)]
    return ln.Investigation(s, '제1조 제1항 전체 승인 구조', record, None, 120, None, None)


def value(data, action='PENDING', target=None, branch=None):
    out = decide(data, action, target, branch)
    out['expected_state_version'] = data['state_version']
    return out


def apply(inv, out, data, actions):
    inv.validate(out, data, actions); inv.execute(out, data, actions)


def read_parent(inv):
    data, actions = inv.view(); card = data['articles'][0]
    apply(inv,value(data,'READ_PARENT',card['read_parent_action'],card),data,actions)
    return card['id']


def adopt(inv, gid, *, finish=True):
    data, actions = inv.view()
    out = value(data,'FINISH' if finish else 'PENDING')
    out['branch_decisions'] = [{'branch_id':gid,'status':'ADOPT','reason':'원문이 현재 요구를 뒷받침',
        'issue_refs':['Q1'],'basis_refs':[p['id'] for p in data['sources'] if p['branch_id']==gid]}]
    out['evidence_sufficient'] = False
    apply(inv,out,data,actions)
    return out


def test_scope_union_does_not_confuse_parent_or_last_page_with_whole():
    want=[{'block_id':'1','start_cp':0,'end_cp':10},{'block_id':'2','start_cp':0,'end_cp':8}]
    assert not ei.covers(want,[{'block_id':'1','start_cp':5,'end_cp':10},{'block_id':'2','start_cp':0,'end_cp':8}])
    assert ei.covers(want,[{'block_id':'1','start_cp':5,'end_cp':10},{'block_id':'1','start_cp':0,'end_cp':6},{'block_id':'2','start_cp':0,'end_cp':8}])
    assert ei.covers(None,[]) is None


def test_whole_item_is_not_whole_paragraph_and_finish_is_not_sufficiency(session):
    native,_=session;inv=investigation(native);gid=read_parent(inv)
    out=adopt(inv,gid);result=inv.result(out)
    assert result['status']=='complete' and result['evidence_sufficient'] is False
    receipt=result['evidence_inventory'][0]['receipt']
    assert receipt['scope']['id']=='subtree:2' and receipt['acquired_complete']
    assert not result['selected_originals'][0]['article_complete']
    assert '일반 승인 예외' not in result['selected_originals'][0]['text']
    assert '일반 승인 예외' not in json.dumps(result['saved_inventory'],ensure_ascii=False)


def test_saved_deferred_requires_current_body_before_readoption(session):
    native,_=session;inv=investigation(native);gid=read_parent(inv)
    data,actions=inv.view();out=value(data)
    out['branch_decisions']=[{'branch_id':gid,'status':'DEFER','reason':'별도 요구 확인 후 재판단',
                             'issue_refs':['Q1'],'basis_refs':[]}]
    apply(inv,out,data,actions)
    data,actions=inv.view();assert not data['sources']
    stale=value(data);stale['branch_decisions']=[{'branch_id':gid,'status':'ADOPT','reason':'메타데이터만으로 채택',
        'issue_refs':['Q1'],'basis_refs':[b['id'] for b in data['basis'] if b.get('branch_id')==gid]}]
    with pytest.raises(ProposalError,match='delivered original'):inv.validate(stale,data,actions)
    count=inv.p['read_state']['count'];target=next(a['id'] for a in actions.values() if a['action']=='VIEW_SAVED_SOURCE')
    apply(inv,value(data,'VIEW_SAVED_SOURCE',target),data,actions)
    assert inv.view()[0]['sources'] and inv.p['read_state']['count']==count
    done=adopt(inv,gid);assert inv.result(done)['final_ids']


def test_entry_and_sequence_survive_sorted_serialization(session):
    native,_=session;inv=investigation(native);entry,_=inv.view();read_parent(inv);inv.view()
    saved=json.loads(json.dumps(inv.p,sort_keys=True))
    assert trail.context(saved)['entry_frame_id']==entry['chain_frame_id']
    assert [p['number'] for p in trail.points(saved)]==sorted(p['number'] for p in trail.points(saved))
    assert trail.context(saved)['entry_search']['queries']==entry['search_queries']


def test_history_normalization_preserves_every_reason_and_judgment(session):
    native,_=session;inv=investigation(native);data,actions=inv.view()
    for n in range(3):
        out=value(data);out['reason']='보존할 행동 이유 '+str(n)
        apply(inv,out,data,actions);data,actions=inv.view()
    projection=trail.context(inv.p)
    assert len(projection['steps'])==3 and len(projection['judgments'])==1
    assert [s['reason'] for s in projection['steps']]==['보존할 행동 이유 '+str(n) for n in range(3)]
    assert all(s['judgment_refs'] for s in projection['steps'])


def test_stale_decision_has_no_tool_effect(session):
    native,_=session;inv=investigation(native);data,actions=inv.view();card=data['articles'][0]
    out=value(data,'READ_PARENT',card['read_parent_action'],card);out['expected_state_version']=-1
    count=inv.p['read_state']['count']
    with pytest.raises(ValidationError):inv.validate(out,data,actions)
    assert inv.p['read_state']['count']==count and not inv.p['selected']


def test_assessment_does_not_search_for_missing_facts():
    assessment={'claims':[],'limitations':[],'disposition':'NEEDS_INVESTIGATION',
        'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT','reason':'취임 날짜 미제공'}],
        'gaps':[{'issue_id':'Q1','kind':'MISSING_FACT','reason':'취임일 필요','material_id':None,'suggested_action':'RESEARCH'}]}
    with pytest.raises(ContractError,match='facts'):ic.validate_assessment(assessment,[{'id':'Q1'}],[])
    assessment['gaps'][0]['suggested_action']='REQUEST_FACT'
    ic.validate_assessment(assessment,[{'id':'Q1'}],[])


def test_assessment_each_issue_once_and_no_false_full_answer():
    value={'claims':[{'source_id':'s','text':'규칙','quote':'규칙'}],'limitations':[],
        'disposition':'ANSWER','issue_assessments':[{'issue_id':'Q1','status':'PARTIAL','reason':'일부만 읽음'}],'gaps':[]}
    with pytest.raises(ContractError,match='all issues'):ic.validate_assessment(value,[{'id':'Q1'}],[])
    value['disposition']='LIMITED_ANSWER';ic.validate_assessment(value,[{'id':'Q1'}],[])


def test_unread_scope_adoption_and_defer_read_collision_rejected(session):
    native,_=session;inv=investigation(native);data,actions=inv.view();card=data['articles'][0]
    out=value(data,'READ_PARENT',card['read_parent_action'],card)
    out['branch_decisions']=[{'branch_id':card['id'],'status':'DEFER','reason':'미선택', 'issue_refs':['Q1'],'basis_refs':[]}]
    with pytest.raises(ProposalError,match='defer/exclude'):inv.validate(out,data,actions)
    assert not inv.p['selected']


class ControlTransport(__import__('test_law_grouped_navigation').LawTransport):
    def __init__(self):
        super().__init__();self.assess_count=0;self.gap_count=1;self.final_assess_views=[]
    def send_once(self, *, body, ticket):
        from test_legal_agent_double_harness import wire
        from test_law_grouped_navigation import reader
        view=json.loads(body['messages'][1]['content'])['view'];phase=view.get('source_stage',view['phase'])
        if phase=='memory-intent':
            self.phases.append(phase)
            return wire({'purpose':'모의 승인 대상 확인','concepts':['승인'],'issues':[
                {'id':'Q1','question':'승인 대상과 예외','subject':'모의 대상','kind':'STRUCTURE'}]})
        if phase.startswith('source-law-navigation-'):
            self.phases.append(phase)
            out=reader(None,view,None,phase,120);out['expected_state_version']=view['state_version']
            return wire(out)
        if phase.startswith('memory-assess'):
            self.phases.append(phase);self.assess_count+=1;self.final_assess_views.append(deepcopy(view))
            source=view['sources'][0];gap=self.assess_count<=self.gap_count
            return wire({'claims':[{'text':'제공된 모의 규정으로 승인 대상 확인','source_id':source['source_id'],'quote':source['text'][:15]}],
                'limitations':[], 'disposition':'NEEDS_INVESTIGATION' if gap else 'ANSWER',
                'issue_assessments':[{'issue_id':'Q1','status':'PARTIAL' if gap else 'COVERED','reason':'예외 보완' if gap else '모의 원문 확인'}],
                'gaps':[{'issue_id':'Q1','kind':'MISSING_SCOPE','reason':'예외 원문 재확인','material_id':None,'suggested_action':'RETURN_TO'}] if gap else []})
        if phase.startswith('memory-compose'):
            self.phases.append(phase);a=view['assessment']
            return wire({'text':a['claims'][0]['text'],'claims':a['claims'],'limitations':a['limitations']})
        return super().send_once(body=body,ticket=ticket)


@pytest.fixture
def control_api(tmp_path,tree):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from test_legal_agent_double_harness import ROOT
    from test_bounded_source_main import settings
    gen,idx=tree;t=ControlTransport();principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'max_model_attempts':80,'max_read_chars':1000,
            'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'assessment_reentry_limit':2}},
        legal_agent_transport=t,memory_identity=lambda _:principal)
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as client:yield client,t,tmp_path


def test_native_assess_select_reentry_uses_same_case_and_preserves_chain(control_api):
    client,t,path=control_api
    r=client.post('/v1/rag/ask',json={'question':'긴급 승인 예외','session_id':'control','request_id':'one'})
    assert r.status_code==200,r.text
    out=r.json();meta=out['assembly']['term_agent']
    assert t.assess_count==2 and meta['answer_coverage']=='COVERED'
    assert meta['control_contract']=='investigation-control-v2'
    assert len(t.final_assess_views[-1]['investigation_chain']['steps'])>len(t.final_assess_views[0]['investigation_chain']['steps'])
    assert t.final_assess_views[-1]['reentry_budget']['ASSESS_GAP_REENTRY']==1
    assert all(c['source_ids'] for c in out['answer']['claims'])


def test_native_assessment_budget_bounds_loop_and_reports_specific_gap(control_api):
    client,t,path=control_api;t.gap_count=99
    r=client.post('/v1/rag/ask',json={'question':'긴급 승인 예외','session_id':'control','request_id':'bounded'})
    assert r.status_code==200,r.text
    out=r.json();meta=out['assembly']['term_agent']
    assert t.assess_count==3 and meta['answer_coverage']=='PARTIAL'
    assert len(meta['gaps'])==1
    assert t.final_assess_views[-1]['reentry_budget']['ASSESS_GAP_REENTRY']==2
    assert '예외 원문 재확인' in out['assembly']['unresolved']
