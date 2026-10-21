from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent.workflow_execution import entry_proposal,validate_task
from semantic_runtime.legal_agent.request_entry import schema
from semantic_runtime.legal_agent.errors import ContractError
from workflow.risk_team_compare_workflow.retrieval import discover


def task(n=1,side='internal'):
    return {'source_category':side,'search_hints':['승인 기준'],
       'issues':[{'id':'parent-'+str(i),'question':('내규' if side=='internal' else '외규')+' 기준 '+str(i),'numeric':False} for i in range(n)],
       'facts':[{'name':'회사','value':'A','user_quote':'회사 A'}]}

@pytest.mark.parametrize('n',[1,2,8,12])
@pytest.mark.parametrize('side',['internal','external'])
def test_one_parent_plan_preserves_every_issue_and_fact(n,side):
    t=task(n,side);copy=deepcopy(t);out=entry_proposal(t,'회사 A의 승인 기준과 예외를 비교',True)
    validate(out,schema(True));assert len(out['intent']['issues'])==n and t==copy
    assert [i['question'] for i in out['intent']['issues']]==[i['question'] for i in t['issues']]
    assert out['command']['facts']==t['facts'] and out['command']['source_category']==side
    assert out['search']['mode']=='FULLTEXT'
    assert all(i['request_quote']=='회사 A의 승인 기준과 예외를 비교' for i in out['intent']['issues'])

@pytest.mark.parametrize('fault',['fact_quote','duplicate','oversize','unknown_field'])
def test_invalid_parent_binding_never_enters_native_case(fault):
    t=task()
    if fault=='fact_quote':t['facts'][0]['user_quote']='없는 사실'
    if fault=='duplicate':t['issues']*=2
    if fault=='oversize':t=task(13)
    if fault=='unknown_field':t['authority_override']=True
    with pytest.raises(ContractError):entry_proposal(t,'회사 A',True)


def test_parent_side_tasks_and_facts_reach_child_unchanged():
    sent=[]
    def call(action,call_id):sent.append(action);return {'status':'partial','evidence_ids':[],'unresolved':[]}
    scope={'issues':[{'id':'I1','label':'기준','numeric':False,'internal_task':'내규 기준','external_task':'외규 기준'}],
      'facts':task()['facts'],'internal_queries':['내규 승인'],'external_queries':['외규 승인']}
    state={'scope':scope,'history':[],'gaps':[]}
    ctx=NS(request={'question':'회사 A 규정 비교','as_of':None},rag=NS(call=call),repo=NS(save=lambda s:None))
    discover(ctx,state,'external');value=sent[0]['args']
    assert value['question']==ctx.request['question'] and value['task']['issues'][0]['question']=='외규 기준'
    assert value['task']['facts']==scope['facts']

@pytest.mark.parametrize('n',[1,2,12])
@pytest.mark.parametrize('dependency',[False,True])
def test_system_binds_all_issue_links_and_quotes(n,dependency):
    from semantic_runtime.legal_agent import investigation_scope as scope,completion_contracts as cc
    from semantic_runtime.legal_agent.decision_projection import prepare
    from semantic_runtime.legal_agent.law_navigation import _object
    view={'completion_contract':cc.V8,'issues':[{'id':'Q'+str(i),'request_quote':'원래 요구 '+str(i)} for i in range(n)],
      'sources':[{'id':'S1','text':'명시 참조 원문'}],
      'investigation_scope':{'request':' '.join('원래 요구 '+str(i) for i in range(n))}}
    e=scope.schema(view,{'T1','T2'})
    base=_object({'next_action':{'type':'string'},'targets':{'type':'array','items':{'enum':['T1','T2']}},
        'issue_refs':{'type':'array','items':{'enum':[i['id'] for i in view['issues']]}},'exploration':e})
    branches=[]
    for kind,target in [('READ_ARTICLES','T1'),('OPEN_LAW','T2')]:
        b=deepcopy(base);b['properties']['next_action']={'const':kind};b['properties']['exploration']=scope.schema(view,{target});branches.append(b)
    full={**base,'anyOf':branches};wire,expand,_=prepare(full,view)
    raw={'next_action':'OPEN_LAW','targets':['T2'],'exploration':[{'target':'T2','issue_id':i['id'],
        'missing_need':'추가 원문','relation':'DEPENDENCY' if dependency else 'DIRECT',
        **({'source_ref':'S1'} if dependency else {})} for i in view['issues']]}
    validate(raw,wire);out=expand(raw);scope.validate(out,view)
    assert out['issue_refs']==[i['id'] for i in view['issues']]
    assert [r['request_quote'] for r in out['exploration']]==[i['request_quote'] for i in view['issues']]
    if dependency:
        bad=deepcopy(raw);bad['exploration'][0]['source_ref']='not-delivered'
        with pytest.raises(Exception):validate(bad,wire)
