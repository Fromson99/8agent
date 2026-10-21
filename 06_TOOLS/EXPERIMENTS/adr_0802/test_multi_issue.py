from copy import deepcopy
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import completion_contracts as cc, investigation_scope as scope, output_contract as oc
from test_focused_input_modality import tree, session, focused, purpose
from test_investigation_completion_adr0678 import decision, apply


def sample(version=cc.V8,n=2):
    v={'completion_contract':version,'issues':[{'id':f'Q{i}','request_quote':f'요구{i}'} for i in range(1,n+1)],'sources':[], 'investigation_scope':{'request':' '.join(f'요구{i}' for i in range(1,n+1))}}
    p={'targets':['T1'],'issue_refs':[x['id'] for x in v['issues']], 'exploration':[{'target':'T1','issue_id':x['id'],'request_quote':x['request_quote'],'missing_need':x['request_quote']+' 원문','relation':'DIRECT','source_quote':''} for x in v['issues']]}
    return v,p

@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
@pytest.mark.parametrize('n',[1,2,3,8])
def test_distinct_issues_share_target_without_mutation(version,n):
    v,p=sample(version,n);before=deepcopy(p)
    validate(p['exploration'],scope.schema(v,{'T1'}));scope.validate(p,v)
    assert p==before and len(p['targets'])==1 and len(p['exploration'])==n

@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
def test_eight_targets_each_preserve_all_eight_issue_links(version):
    v,p=sample(version,8);rows=p['exploration'];p['targets']=[f'T{i}' for i in range(8)]
    p['exploration']=[{**r,'target':t} for t in p['targets'] for r in rows]
    validate(p['exploration'],scope.schema(v,set(p['targets'])));scope.validate(p,v)
    assert len(p['exploration'])==64

@pytest.mark.parametrize('mode,code',[
 ('duplicate','EXPLORATION_DUPLICATE_TARGET_ISSUE'),('missing','EXPLORATION_TARGET_COVERAGE'),
 ('extra','EXPLORATION_TARGET_COVERAGE'),('unknown','EXPLORATION_UNKNOWN_ISSUE'),
 ('unselected','EXPLORATION_UNSELECTED_ISSUE'),('quote','EXPLORATION_REQUEST_QUOTE_INVALID'),
 ('dependency','DEPENDENCY_WITHOUT_DELIVERED_SOURCE'),('need','EXPLORATION_MISSING_NEED')])
@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
def test_bad_independent_relation_is_still_rejected(version,mode,code):
    v,p=sample(version)
    if mode=='duplicate':p['exploration'].append(deepcopy(p['exploration'][0]))
    elif mode=='missing':p['targets'].append('T2')
    elif mode=='extra':p['exploration'][1]['target']='T2'
    elif mode=='unknown':p['exploration'][1]['issue_id']='Q999'
    elif mode=='unselected':p['issue_refs']=['Q1']
    elif mode=='quote':p['exploration'][1]['request_quote']='없는 인용'
    elif mode=='dependency':p['exploration'][1]['relation']='DEPENDENCY'
    elif mode=='need':p['exploration'][1]['missing_need']=' '
    before=deepcopy(p)
    with pytest.raises(oc.OutputContractError) as caught:scope.validate(p,v)
    assert code in {x['code'] for x in caught.value.issues} and p==before

@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
def test_native_navigation_one_read_keeps_both_issue_provenances(session,version):
    native,_=session;i=focused(native);i.s.profile['candidate_navigation']['completion_policy_version']=version
    i.p['issues'].append({**i.p['issues'][0],'id':'Q2'})
    d,a=i.view();t=d['articles'][0]['read_parent_action'];p=decision(d,'READ_PARENT',t)
    p['issue_refs']=['Q1','Q2'];p['exploration']=[{**purpose(d,t),'issue_id':q,'missing_need':q+' 원문 확인'} for q in p['issue_refs']]
    before=deepcopy(p);calls=[];execute=i.execute_tool
    def counted(value,data,actions):
        calls.extend(value['targets']);return execute(value,data,actions)
    i.execute_tool=counted
    proposed=[]
    def invoke(*args):
        if proposed:raise RuntimeError("stop after accepted read")
        proposed.append(True);return deepcopy(p)
    i.invoke=invoke
    with pytest.raises(RuntimeError,match="stop after accepted read"):i.run()
    assert calls==[t] and p==before
    assert i.p['decisions'][-1]['decision']['exploration']==p['exploration']
    assert next(iter(i.p['law_reasons'].values()))['issue_refs']==['Q1','Q2']
    assert i.p['selected']
