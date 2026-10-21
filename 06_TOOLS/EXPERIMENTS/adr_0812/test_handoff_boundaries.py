from copy import deepcopy
from types import SimpleNamespace as NS
import json,sqlite3
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.workflow_evidence import parent_issues,parent_refs,compact_result
from semantic_runtime.legal_agent.errors import ContractError
from workflow.risk_team_compare_workflow.retrieval import restore_context


def child(task):
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE event(seq,kind,payload_json,payload_hash)')
    value={'task':task,'task_hash':digest(task),'issue_map':{'Q'+str(n):i['id'] for n,i in enumerate(task['issues'],1)}}
    db.execute('INSERT INTO event VALUES(1,?,?,?)',('WORKFLOW_PARENT_TASK_BOUND',json.dumps(value),digest(value)))
    return NS(db=db),value


def test_issue_join_and_unknown_ref_are_not_guessed():
    c,_=child({'issues':[{'id':'reserve-target'},{'id':'threshold-target'}]})
    m=parent_issues(c);v=parent_refs({'issue_refs':['Q2','Q1','new-dependency']},m)
    assert v['parent_issue_refs']==['threshold-target','reserve-target']
    assert v['unmapped_child_issue_refs']==['new-dependency']
    assert v['issue_refs']==['Q2','Q1','new-dependency']


@pytest.mark.parametrize('fault',['hash','mapping','duplicate'])
def test_issue_binding_tamper_and_ambiguity_rejected(fault):
    c,v=child({'issues':[{'id':'a'},{'id':'b'}]})
    if fault=='hash':c.db.execute("UPDATE event SET payload_hash='0'")
    elif fault=='mapping':
        v['issue_map']['Q1']='b';c.db.execute('UPDATE event SET payload_json=?,payload_hash=?',(json.dumps(v),digest(v)))
    else:c.db.execute('INSERT INTO event SELECT 2,kind,payload_json,payload_hash FROM event')
    with pytest.raises(ContractError):parent_issues(c)


def test_parent_view_keeps_all_claims_gaps_and_provenance_without_generated_answer():
    result={'side':'internal','status':'partial','answer':{'text':'UNVERIFIED GENERATED DUPLICATE'},'run_id':'r',
        'bundle':{'bundle_hash':'h','issue_map':{'Q1':'a'},'claims':[{'claim_id':str(n),'issue_refs':['Q1'],
        'parent_issue_refs':['a'],'rule':{'condition':'same','exception':'preserve-'+str(n)},'evidence_ids':[str(n)]} for n in range(37)],
        'gaps':[{'id':'g','reason':'missing provision'}],'limitations':['unknown edition'],'stop_reason':'budget'}}
    before=deepcopy(result);v=compact_result(result)
    assert result==before and 'answer' not in v
    assert len(v['claims'])==37 and v['gaps']==result['bundle']['gaps'] and v['limitations']==['unknown edition']
    assert v['claims'][-1]['rule']['exception']=='preserve-36' and v['issue_map']=={'Q1':'a'}


def test_saved_original_context_is_restored_once_and_survives_restart():
    intents={};calls=[];saved=[]
    def intent(k,kind,args):return intents.setdefault(k,{'status':'STARTED'})
    def finish(k,v):intents[k]={'status':'COMPLETE','result':v}
    def context(ids,key):calls.append(ids);return ids+['whole-exception-block']
    ctx=NS(repo=NS(intent=intent,finish=finish,save=lambda x:saved.append(deepcopy(x))),rag=NS(port=NS(saved_context=context)))
    state={'rag_results':{'internal':{'evidence_ids':['adopted-rule'],'bundle':{'bundle_hash':'h'}}}}
    restore_context(ctx,state);restored=deepcopy(saved[-1]);restore_context(ctx,restored)
    assert len(calls)==1 and restored['context_evidence']==['adopted-rule','whole-exception-block']
    assert restored['context_by_side']['internal']==restored['context_evidence']


def test_failed_context_read_is_not_completed_or_converted_to_absence():
    intents={};state={'rag_results':{'external':{'evidence_ids':['e'],'bundle':{'bundle_hash':'h'}}}}
    def fail(*a):raise TimeoutError('read interrupted')
    ctx=NS(repo=NS(intent=lambda k,*a:intents.setdefault(k,{'status':'STARTED'}),finish=lambda *a:pytest.fail('false completion'),save=lambda *a:None),rag=NS(port=NS(saved_context=fail)))
    with pytest.raises(TimeoutError):restore_context(ctx,state)
    assert not state.get('context_evidence') and all(v['status']=='STARTED' for v in intents.values())


def test_unstructured_claim_keeps_its_only_semantic_statement():
    v=compact_result({'bundle':{'claims':[{'claim_id':'c','rule':None,'text':'Only committed statement','evidence_ids':['e']}]}})
    assert v['claims'][0]['text']=='Only committed statement'


def test_compare_packet_includes_current_same_source_context_only(monkeypatch):
    import workflow.presentation as p
    items=[{'evidence_id':ident,'source_id':root,'text':'원문'} for ident,root in
           [('selected','same'),('exception','same'),('unrelated','other')]]
    seen=[]
    def evidence(ctx,state,ids=None):
        out=[dict(e) for e in items if ids is None or e['evidence_id'] in ids]
        seen.append({e['evidence_id'] for e in out});return out
    monkeypatch.setattr(p,'evidence',evidence)
    monkeypatch.setattr(p,'view',lambda ctx,state,values,**k:{'sources':values})
    ctx=NS(rag=NS(evidence=lambda:items),model=NS(services=NS(profile={'max_context_chars':50000})))
    state={'rag_results':{'internal':{'evidence_ids':['selected'],'bundle':{'bundle_hash':'h'}}},'context_evidence':['exception','unrelated']}
    packets=p.packets(ctx,state,'COMPARE:p',ids={'selected'})
    assert {e['evidence_id'] for e in packets[0][1]}=={'selected','exception'}
    assert packets[0][0]['packet']['dependency_closure_complete']


def test_oversize_atomic_span_is_capacity_failure_without_altering_source():
    from semantic_runtime.workflow_bridge import SourcePort
    from semantic_runtime.legal_agent.errors import BudgetExhausted
    source={'spans':[{'text':'가'*15001}]};before=deepcopy(source)
    with pytest.raises(BudgetExhausted) as error:SourcePort.split_evidence(NS(),source,14000)
    assert 'complete original block' in str(error.value)
    assert source==before
