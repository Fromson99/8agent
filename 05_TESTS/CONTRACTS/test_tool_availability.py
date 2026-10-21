"""Menu/execution parity on synthetic sources; no model or production calls."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import tool_availability as ta,law_navigation as ln,unit_reading as ur,unit_relations as rel,completion_contracts as cc,memory_methods as mm,request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError,BudgetExhausted
from test_container_article_read import tree,session,action,execute,hit,setup,value,grouped
from test_batch_reference_navigation import connected,initial,decision
from test_memory_runtime_v2 import memory,start,command

@pytest.mark.parametrize('kind,history',[('SEARCH_BODY','body_search_history'),('SEARCH_STRUCTURE','structure_search_history'),('RESEARCH','query_history')])
@pytest.mark.parametrize('restored',[False,True])
def test_exhausted_search_removed_from_fresh_and_historical_menu(session,kind,history,restored):
    native,_=session;inv,_=setup(native);data,actions=inv.view()
    prior={k:v for k,v in actions.items() if v['action']==kind};assert prior
    if restored:inv.p['revisit']={'frame_id':data['chain_frame_id'],'reason':'기록 확인'}
    if kind=='RESEARCH':inv.policy['search_rounds']=inv.search_rounds_used()
    else:inv.p[history]=[{}]*inv.policy['search_rounds']
    after,offered=inv.view()
    assert not any(a['action']==kind for a in offered.values())
    assert not any(a['action']==kind for a in after['actions'])
    before=deepcopy(inv.p)
    with pytest.raises(ContractError):inv.execute_tool(value(data,kind,next(iter(prior))),{'sources':[]},prior)
    assert inv.p==before

@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
def test_gap_injected_tools_obey_current_budget(session,version):
    native,_=session;inv,_=setup(native);inv.completion=version
    inv.p['body_search_history']=[{}]*inv.policy['search_rounds']
    inv.p['structure_search_history']=[{}]*inv.policy['search_rounds']
    gap={'gap_id':'G1','missing_target':'모의승인규정','target_binding':{'document_candidates':['d'],'status':'DOCUMENT_BOUND'}}
    inv.p['assessment_gaps']=[gap];inv.open_gap_round()
    actions={};rr.add_target_actions(inv,actions)
    assert any(a['action']=='SEARCH_BODY' for a in actions.values())
    data={'actions':[{'id':k,'action':a['action']} for k,a in actions.items()]}
    ta.filter_navigation(inv,data,actions)
    assert {a['action'] for a in actions.values()}=={'OPEN_STRUCTURE'}

@pytest.mark.parametrize('policy,reason',[('initial_chars','READ_CHARACTER_LIMIT'),('read_actions','READ_ACTION_LIMIT')])
def test_exhausted_read_menu_has_no_unread_tools_but_navigation_survives(session,monkeypatch,policy,reason):
    native,_=session;inv,_=setup(native);monkeypatch.setitem(ur.POLICY,policy,0)
    data,actions=inv.view()
    assert not any(a['action'] in ('READ_ARTICLES','READ_PARENT','READ_SCOPE') for a in actions.values())
    assert any(a['action']=='BROWSE_STRUCTURE' for a in actions.values())
    assert not data['sources'] and not inv.p['selected']

def test_page_limit_counts_short_blocks_not_just_characters(session):
    native,_=session;inv,_=setup(native);s=inv.s;sid=hit(native)['source_id']
    h,o=ta.article_plan(s,{'source_id':sid,'document_id':'d'})[0]
    s.profile.update(page_size=1,max_read_chars=100000)
    original=s.repo.budget;s.repo.budget=lambda:{**original(),'tool_limit':1,'tool_used':0}
    assert ta.read_reason(s,h,o,inv.p['read_state'])=='TOOL_ACTION_LIMIT'

def test_acquired_original_remains_viewable_after_budget_exhaustion(session,monkeypatch):
    native,_=session;inv,_=setup(native);execute(inv,action(inv.s,hit(native)['source_id']))
    prior=deepcopy(inv.p['read_state']);monkeypatch.setitem(ur.POLICY,'initial_chars',prior['chars'])
    monkeypatch.setitem(ur.POLICY,'read_actions',prior['count'])
    plan,_=ta.article_plan(inv.s,{'source_id':hit(native)['source_id'],'document_id':'d'})
    assert ta.read_reason(inv.s,*plan,prior) is None
    inv.p['window']='structure';data,actions=inv.view()
    assert inv.p['read_state']==prior
    assert any(a['action']=='VIEW_SAVED_SOURCE' for a in actions.values())

def test_cross_source_container_not_offered_but_child_remains_readable(grouped):
    s,_=grouped;inv,_=setup(SimpleNamespace(sources=s),'모의장규정')
    sid=next(sid for sid,src in s.tools.sources.items() if src['document_id']=='chap' and str(src['unit_id'])=='0')
    plan,reason=ta.article_plan(s,{'source_id':sid,'document_id':'chap'})
    assert plan is None and reason=='SUBTREE_CROSSES_SOURCE_BOUNDARY'
    data,actions=inv.view()
    assert not any(a['action']=='READ_ARTICLES' and a['identity']['source_id']==sid for a in actions.values())
    assert any(a['action']=='BROWSE_STRUCTURE' for a in actions.values())

@pytest.mark.parametrize('kind,ident',[('NEXT_STRUCTURE',{'document_id':'d','offset':999}),('NEXT_ARTICLES',{'document_id':'d','cursor':'old'}),('NEXT_HITS',{'source_id':'missing','cursor':'old'}),('FOLLOW_CONNECTION',{'signature':'old'})])
def test_stale_menu_handles_fail_before_any_state_mutation(session,kind,ident):
    native,_=session;inv,_=setup(native);data,_=inv.view()
    actions={'T':{'id':'T','action':kind,'identity':ident}};before=deepcopy(inv.p)
    with pytest.raises(ContractError):inv.execute_tool(value(data,kind,'T'),{'sources':[]},actions)
    assert inv.p==before

def test_no_ready_goal_or_knowledge_means_no_completion_or_reuse():
    assert set(mm.offered({'goals':[],'knowledge':[]}))=={'CASE_START','NEED_TARGET'}
    context={'goals':[{'id':'pending','status':'RUNNING','events':[]}],'knowledge':[]}
    offered=mm.offered(context)
    assert {'ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','EXPERIENCE_REUSE','WIKI_RELINK','STATE_RESTORE'}.isdisjoint(offered)
    assert offered['FACT_UPDATE']['targets']==['pending']
    context['goals'].append({'id':'ready','status':'READY','events':[{'after':{'facts':[]}}]})
    offered=mm.offered(context)
    assert offered['EXPERIENCE_CONFIRM']['targets']==['ready'] and offered['STATE_RESTORE']['targets']==['ready']
    with pytest.raises(ValueError):mm.require_offered({'method_id':'EXPERIENCE_CONFIRM','target':'pending'},context)

def test_memory_schema_couples_method_to_ready_route_and_target(memory):
    m,executor,wire,send,principal=memory;gid=start(send)['goal_id'];context=m.context('s',principal,'표로 보여줘')
    assert mm.offered(context)['ANSWER_PRESENT']['targets']==[gid]
    context['goals'].append({'id':'pending','status':'RUNNING','state':deepcopy(context['goals'][0]['state']),'events':[]})
    seen=[]
    def invoke(system,data,schema,phase):
        if phase=='memory-command-check':return {'valid':True,'reason':'모의 검사'}
        seen.append(schema);return command('ANSWER_PRESENT',target=gid)
    m.invoke=invoke;m.resolve(context)
    schema=seen[0];good=command('ANSWER_PRESENT',target=gid);good.pop('action',None)
    validate(good,schema)
    with pytest.raises(ValidationError):validate({**good,'target':'pending'},schema)
    assert 'EXPERIENCE_REUSE' not in schema['properties']['method_id']['enum']

def test_reference_budget_exhaustion_keeps_defer_but_removes_follow(connected,monkeypatch):
    s,_=connected;rec,sid=initial(s);state=rec['read_state'];selected={'U1':rec['unit_reads'][0]}
    ur.ensure_context(s,selected,state)
    monkeypatch.setitem(ur.POLICY,'initial_chars',state['chars'])
    called=[]
    def invoke(system,data,schema,phase,timeout):
        called.append(data);assert all(not g['read_options'] for g in data['groups'])
        assert all(b['properties']['action'].get('const')!='FOLLOW' for b in schema['properties']['decisions']['items']['anyOf'])
        return decision(data,'DEFER')
    before=s.repo.budget()['tool_used']
    result=rel.navigate('승인',s,selected,invoke,read_state=state,seconds_left=lambda:120,max_context_chars=80000)
    assert called and result['pending'] and s.repo.budget()['tool_used']==before

def test_navigation_catalogue_has_no_unreviewed_executor_kinds():
    assert ta.NAVIGATION==ln.INVESTIGATIVE_ACTIONS

@pytest.mark.parametrize('page_size,chars',[(1,80),(3,18),(20,10000)])
def test_article_cost_matches_actual_intro_then_subtree_reads(session,page_size,chars):
    native,_=session;inv,_=setup(native);s=inv.s;s.profile.update(page_size=page_size,max_read_chars=chars)
    sid=hit(native)['source_id'];plan,_=ta.article_plan(s,{'source_id':sid,'document_id':'d'})
    expected=ta.sequence_cost(s,ta.article_sequence(s,plan),s.repo.evidence())
    before=deepcopy(inv.p['read_state']);execute(inv,action(s,sid))
    assert (inv.p['read_state']['chars']-before['chars'],inv.p['read_state']['count']-before['count'])==expected

def test_read_batch_budget_checked_before_acknowledgement_or_partial_reads(session,monkeypatch):
    native,_=session;inv,_=setup(native);s=inv.s;sid=hit(native)['source_id']
    actions={key:{**action(s,sid,unit)['T'],'id':key} for key,unit in [('A','1'),('B','5')]}
    costs=[ta.sequence_cost(s,ta.article_sequence(s,ta.article_plan(s,a['identity'])[0]),s.repo.evidence()) for a in actions.values()]
    monkeypatch.setitem(ur.POLICY,'initial_chars',inv.p['read_state']['chars']+max(c[0] for c in costs))
    data={'actions':[{'id':k} for k in actions]};ta.filter_navigation(inv,data,actions)
    assert len(actions)==2 and data['read_batch_limit']==1
    before=deepcopy(inv.p);decision={'next_action':'READ_ARTICLES','targets':['A','B']}
    with pytest.raises(BudgetExhausted):inv.execute_tool(decision,{'sources':[]},actions)
    assert inv.p==before and not s.repo.evidence()

def test_shortcut_terminal_clarification_does_not_reenter_command_admission(monkeypatch):
    from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
    from semantic_runtime.legal_agent.case_repository import CaseRepository
    case=ShortcutCases.__new__(ShortcutCases)
    case.context=lambda *a:{'utterance':'모의 요청','allowed_documents':[],'goals':[]}
    case.direct_request=lambda context:None
    case.executor=SimpleNamespace(request_entry=None)
    case.flags={'core_evidence_route':True};case.procedure=SimpleNamespace(event=lambda *a:None,lookup=lambda *a:(None,None))
    monkeypatch.setattr(CaseRepository,'resolve',lambda *a:{'action':'CLARIFY','reason':'제시되지 않은 저장 경험 명령으로 복구 한도 소진'})
    case.admit=lambda *a:pytest.fail('terminal clarification is not an executable command')
    result=case._execute({'session_id':'s','question':'모의 요청'}, {})
    assert result=={'status':'CLARIFY','answer':None,'reason':'제시되지 않은 저장 경험 명령으로 복구 한도 소진'}
    assert not hasattr(case,'resolved_command')

def test_shortcut_api_unavailable_command_finishes_as_clarification_and_deduplicates(tmp_path,tree):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from test_unified_legal_agent import ScriptedTransport
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    gen,idx=tree;t=ScriptedTransport();t.command=command('EXPERIENCE_CONFIRM',target='unavailable')
    app=create_app(tmp_path/'app',gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t,
        memory_identity=lambda req:{'user_id':'u','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture']=True
    app.state.pipeline.term_agent.unit_fulltext=idx
    try:
        with TestClient(app) as client:
            body={'question':'현재 내용 저장해줘','session_id':'s','request_id':'invalid-command'}
            reply=client.post('/v1/rag/ask',json=body)
            assert reply.status_code==200,reply.text
            assert reply.json()['status']=='CLARIFY' and not reply.json()['answer']['claims']
            calls=list(t.phases);assert sum(p.startswith('memory-resolve') for p in calls)==2
            again=client.post('/v1/rag/ask',json=body)
            assert again.status_code==200 and again.json()['status']=='CLARIFY'
            assert t.phases==calls
    finally:app.state.pipeline.store.close()
