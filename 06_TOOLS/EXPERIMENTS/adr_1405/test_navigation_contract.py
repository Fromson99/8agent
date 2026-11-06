"""Dispatch, lossless menu reachability, repair and checkpoint contract tests."""
from copy import deepcopy
import json
from types import SimpleNamespace as S
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import source_goal_control as goals, investigation_supervisor as su
from semantic_runtime.legal_agent import decision_projection as dp, read_candidate_pages as pages
from semantic_runtime.legal_agent import compact_model_input as compact
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
from test_supervisor_action_review import menu


def test_new_goal_does_not_replace_reviewed_action_and_next_preselect_executes_it(menu):
    inv=menu.inv
    result=su.gate(inv,menu.data,menu.actions,menu.payload,menu.proposal,menu.old,
        {'anyOf':[]},lambda v:goals.native_decision(inv,menu.data,menu.actions,v),'single',consistency_reviewed=True)
    assert result==menu.old and result['targets']==['A']
    state=su.state_for(inv,menu.data)
    assert state['source_goals'][0]['status']=='REQUIRED'
    assert state['source_goals'][0]['routes']==[]
    assert state['source_goal_deferred_choices']['P1']['next_route']['targets']==['B']
    su.before_execute(inv,menu.data,result)
    su.after_execute(inv,menu.data,result,True)
    inv.p=json.loads(json.dumps(inv.p))
    assert goals.preselect(inv,menu.data,menu.actions)==result
    data={**menu.data,'presentation_id':'P2'}
    from semantic_runtime.legal_agent.law_navigation import decision_schema
    inv.validate=lambda decision,view,actions:validate(decision,decision_schema(view,actions,set()))
    following=goals.preselect(inv,data,menu.actions)
    assert following['targets']==['B']
    assert su.state_for(inv,data)['source_goals'][0]['routes']==['READ']
    su.before_execute(inv,data,following)


def test_same_goal_and_action_keep_real_goal_receipt(menu):
    value={**menu.proposal,**menu.read('B')}
    decision=goals.native_decision(menu.inv,menu.data,menu.actions,value)
    result=su.gate(menu.inv,menu.data,menu.actions,menu.payload,value,decision,{'anyOf':[]},lambda x:x,'exact',consistency_reviewed=True)
    st=su.state_for(menu.inv,menu.data)
    assert result['targets']==['B'] and st['source_goal_actions']['P1']['kind']=='READ'
    assert not st.get('source_goal_deferred_choices')


def test_deferred_plan_is_pure_and_preserves_original_proposal(menu):
    st=su.state_for(menu.inv,menu.data);before=deepcopy(st);proposal=deepcopy(menu.proposal)
    plan=goals.plan(menu.inv,menu.data,menu.actions,proposal,menu.old,
        lambda x:goals.native_decision(menu.inv,menu.data,menu.actions,x),st,discover_scope=False,preserve_choice=True)
    assert st==before and proposal==menu.proposal
    assert plan['decision']==menu.old and plan['deferred_route']['targets']==['B']


def test_new_goal_cannot_be_hidden_by_terminal_choice(menu):
    plan=goals.plan(menu.inv,menu.data,menu.actions,menu.proposal,{'next_action':'FINISH'},
        lambda x:goals.native_decision(menu.inv,menu.data,menu.actions,x),su.state_for(menu.inv,menu.data),discover_scope=False,preserve_choice=True)
    assert plan['decision']['next_action']=='READ_ARTICLES' and not plan.get('preserved_choice')


def test_unknown_still_blocks_choice_even_when_goal_can_be_deferred(menu):
    st=su.state_for(menu.inv,menu.data);st['pending']={'key':'unknown'};su.save(menu.inv,st)
    from semantic_runtime.legal_agent.errors import TransportError
    with pytest.raises(TransportError):su.gate(menu.inv,menu.data,menu.actions,menu.payload,menu.proposal,menu.old,{'anyOf':[]},lambda x:x,'u',consistency_reviewed=True)
    assert st['execution']=={}


def menu_data():
    opts=[];branches=[]
    for action in ['LOCATE','SEARCH_BODY','OPEN_STRUCTURE']:
        targets=[]
        for doc in ['d1','d2','d3']:
            target=action+'_'+doc;targets.append(target)
            opts.append({'choice':action,'target':target,'label':doc+' '+action,'scope':{'document_id':doc}})
        branches.append({'type':'object','properties':{'choice':{'const':action},'target':{'enum':targets}},'required':['choice','target'],'additionalProperties':False})
    opts.append({'choice':'RESEARCH','target':'all','label':'허용 범위 검색','scope':{}})
    branches.append({'type':'object','properties':{'choice':{'const':'RESEARCH'},'target':{'enum':['all']}},'required':['choice','target'],'additionalProperties':False})
    branches.append({'type':'object','properties':{'choice':{'const':'READ'},'selections':{'type':'array','items':{'type':'object','properties':{'target':{'enum':['r1','r2']}},'required':['target']}}},'required':['choice','selections']})
    data={'tool_options':opts,'sources':[{'id':'E1','document_id':'d1','text':'검증된 원문'}],
          'document_structures':[{'document_id':d,'name':'규정'+d} for d in ['d1','d2','d3']],
          'read_candidates':[{'target':'r1','document_id':'d1'},{'target':'r2','document_id':'d2'}]}
    return data,{'type':'object','anyOf':branches}


def test_scoped_tools_are_smaller_without_dropping_any_executable_route():
    data,schema=menu_data();before=deepcopy(data)
    view,wire=pages.tool_menu_view(data,schema)
    assert view['tool_menu']['shown']==4 and view['tool_menu']['total']==10
    assert view['sources']==data['sources'] and view['read_candidates']==data['read_candidates']
    all_pairs={(r['choice'],r['target']) for r in view['tool_options']}
    for doc in ['d2','d3']:
        validate({'choice':pages.DOCUMENT_TOOLS,'document_ref':doc},wire)
        v,s=pages.tool_menu_view(data,schema,doc)
        for row in v['tool_options']:
            validate({'choice':row['choice'],'target':row['target']},s)
            all_pairs.add((row['choice'],row['target']))
    assert all_pairs=={(r['choice'],r['target']) for r in data['tool_options']}
    assert data==before


@pytest.mark.parametrize('target',['LOCATE_d2','LOCATE_d3','foreign'])
def test_hidden_or_unknown_tool_cannot_be_executed(target):
    data,schema=menu_data();_,wire=pages.tool_menu_view(data,schema)
    with pytest.raises(ValidationError):validate({'choice':'LOCATE','target':target},wire)


@pytest.mark.parametrize('document',['foreign','d1'])
def test_document_switch_only_offered_documents(document):
    data,schema=menu_data();_,wire=pages.tool_menu_view(data,schema)
    with pytest.raises(ValidationError):validate({'choice':pages.DOCUMENT_TOOLS,'document_ref':document},wire)


def test_required_goal_document_remains_visible():
    data,schema=menu_data();data['source_goal_context']={'goals':[{'document_id':'d3','status':'REQUIRED'}]}
    v,w=pages.tool_menu_view(data,schema)
    validate({'choice':'LOCATE','target':'LOCATE_d3'},w)
    assert v['tool_menu']['shown']==7


def test_switch_changes_only_display_and_survives_restart():
    data,schema=menu_data();state={'binding':'M','page':0,'sequence':0};events=[]
    inv=S(p={'read_candidate_pager':state},policy={'read_candidate_page_size':20},save=lambda:None,s=S(repo=S(event=lambda *v:events.append(v))))
    focus=pages.tool_menu_state(inv,'M');after=pages.move_tool_menu(inv,data,'d2',expected_state=state,focus=focus)
    assert after=={'binding':'M','page':0,'sequence':1}
    assert events[-1][1]['originals_acquired'] is False
    inv.p=json.loads(json.dumps(inv.p));restored=pages.tool_menu_state(inv,'M')
    assert restored['document']=='d2'
    with pytest.raises(ContractError):pages.move_tool_menu(inv,data,'d3',expected_state=state,focus=focus)
    inv.p['tool_menu_focus']['document']='foreign'
    with pytest.raises(ContractError):pages.tool_menu_state(inv,'M')


def test_switch_cycle_hands_off_without_read_or_budget_reset():
    data,schema=menu_data();st={'binding':'M','page':0,'sequence':0};inv=S(p={'read_candidate_pager':st},policy={},save=lambda:None,s=S(repo=S(event=lambda *v:None)))
    for doc in ['d2','d3','d2','d3']:
        st=pages.move_tool_menu(inv,data,doc,expected_state=st,focus=pages.tool_menu_state(inv,'M'))
    with pytest.raises(ProgressHandoff,match='TOOL_MENU_NO_PROGRESS'):
        pages.move_tool_menu(inv,data,'d2',expected_state=st,focus=pages.tool_menu_state(inv,'M'))
    assert inv.p['read_candidate_pager']['sequence']==4
    assert pages.tool_menu_state(inv,'M')['halt']


@pytest.mark.parametrize('kind,extra,expected',[
 ('SEARCH_STRUCTURE',{'structure_filter':{'coordinate':'제2조'}},'LOCATE'),
 ('SEARCH_STRUCTURE',{'queries':['제2조']},'CATALOG_SEARCH'),
 ('READ_ARTICLES',{},'READ'),('FOLLOW_CONNECTION',{},'FOLLOW_CONNECTION')])
def test_public_diagnostics_match_model_vocabulary_without_editing_raw(kind,extra,expected):
    route={'next_action':kind,'targets':['T1'],**extra}
    raw={'repair_contract':{'validation':{'issues':[{'expected_constraint':route}]}},'sources':[{'text':'SEARCH_STRUCTURE 원문 그대로'}]}
    original=deepcopy(raw);wire=dp.public_repair_payload(raw)
    actual=wire['repair_contract']['validation']['issues'][0]['expected_constraint']
    assert actual['choice']==expected and 'next_action' not in actual
    assert raw==original and wire['sources']==raw['sources']


def test_guidance_explains_visible_actions_and_unavailable_finish():
    data,schema=menu_data();data['connection_review']={'required_before_finish':True}
    v,w=pages.tool_menu_view(data,schema);text=dp.tool_guidance(v,w)
    for branch in w['anyOf']:assert branch['properties']['choice']['const']+':' in text
    assert 'FINISH는 연결 범위 미확인' in text
    assert '목차 조회는 원문 읽기가 아니다' in text


def test_document_tool_wire_roundtrip_preserves_canonical_document():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    data,schema=menu_data();view,wire=pages.tool_menu_view(data,schema)
    refs=NavigationReferences(view)
    refs.document_forward={'d1':'D1','d2':'D2','d3':'D3'};refs.document_reverse={v:k for k,v in refs.document_forward.items()}
    mapped=refs.schema(wire)
    assert refs.decode({'choice':pages.DOCUMENT_TOOLS,'document_ref':'D2'},mapped)=={'choice':pages.DOCUMENT_TOOLS,'document_ref':'d2'}


def test_menu_projection_keeps_unread_source_and_document_routes():
    data,schema=menu_data();v,w=pages.tool_menu_view(data,schema)
    v['source_stage']='source-law-navigation-read-choice';out=compact.project(v,w)
    assert out['tool_menu']['total']==10 and 'SHOW_DOCUMENT_TOOLS' in out['tool_menu']['meaning']
    assert len(out['tool_documents']['table_rows'])==3


@pytest.mark.parametrize('repair_first',[False,True])
def test_actual_journal_document_switch_repair_and_restart(tmp_path,repair_first):
    from test_output_contract_recovery import Journal
    data,schema=menu_data();data['presentation_id']='presentation-1'
    path=tmp_path/'menu.sqlite';repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3)
    inv=S(p={'binding':{'case':'case-1'}},policy={},save=lambda:None,left=lambda:500,
          s=S(repo=repo,profile={'selection_time_reserve_seconds':20}))
    calls=[];executed=[]
    def invoke(payload,attempt,wire,suffix):
        calls.append((deepcopy(payload),attempt,suffix))
        assert payload['sources']==data['sources']
        if len(calls)==1 and repair_first:return {'choice':'LOCATE','target':'LOCATE_d2'}
        if payload['tool_menu']['focused_document'] is None:
            if repair_first:assert attempt==1 and payload['repair_contract']['same_evidence_scope']
            return {'choice':pages.DOCUMENT_TOOLS,'document_ref':'d2'}
        return {'choice':'LOCATE','target':'LOCATE_d2'}
    first=pages.choose(inv,data,schema,invoke,executed.append,key='same')
    assert first=={'choice':'LOCATE','target':'LOCATE_d2'}
    assert all(x['choice']!=pages.DOCUMENT_TOOLS for x in executed)
    assert inv.p['read_candidate_pager']['sequence']==1
    repo.db.commit();repo.db.close()
    inv.p=json.loads(json.dumps(inv.p));repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=len(calls),finalization_reserve=3)
    inv.s.repo=repo
    assert pages.choose(inv,data,schema,lambda *a:pytest.fail('accepted page must not resend'),executed.append,key='same')==first
    assert len(calls)==2+int(repair_first)
    repo.db.close()
