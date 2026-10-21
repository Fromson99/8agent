from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from jsonschema import validate,ValidationError
from workflow.adapters.projection import prepare
from workflow.risk_team_compare_workflow.contracts import BASIS,COMPARE,check_citations
from workflow.risk_team_compare_workflow import compare as cmp
from workflow.contracts import WorkflowError
from test_unit_fulltext_adaptive_read import tree,session
from test_definition_entry_integration import install
from semantic_runtime.legal_agent import definition_entry as de
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.workflow_execution import child_execution,task_instructions


def sample():
    sources=[{'evidence_id':i,'side':side,'text':'첫째\n둘째','spans':[{'text':'첫째\n둘째'}],
              'source_complete':True,'version_verified':True} for i,side in [('I','internal'),('E','external')]]
    citations=[{'evidence':e['evidence_id'],'quote':e['text']} for e in sources]
    pair={'pair_id':'P1','issue_id':'q1','internal':['I'],'external':['E'],
          'applicability':{'status':'UNKNOWN','reason':'판본 미확인','as_of':None,'citations':citations},
          'basis_relation':'CONTENT_ONLY','basis_path':[],'comparison_eligibility':False,'reason':'적용 미확인','content_difference':'','content_citations':[]}
    return sources,pair


def test_exact_quote_selection_and_host_fields():
    sources,pair=sample();data={'sources':sources,'basis':{'pairs':[pair]},'as_of':None,'scope':{'issues':[{'id':'q1','numeric':True}]}}
    view,schema,expand,receipt=prepare('COMPARE',data,COMPARE)
    raw={'rows':[{'item':'범위','verdict':'DEFERRED','difference':'미확인','reason':'적용 미확인',
        'citations':[{'citation_id':s['citation_options'][0]['citation_id']} for s in view['sources']],
        'dimensions':[],'unresolved':['미확인']}],'answer':'보류','unresolved':['미확인']}
    validate(raw,schema);canonical=expand(raw);validate(canonical,COMPARE)
    row=canonical['rows'][0];assert row['pair_id']=='P1' and row['numeric'] is True
    assert all(c['quote']=='첫째\n둘째' for c in row['citations'])
    check_citations(row['citations'],{e['evidence_id']:e for e in sources})
    bad=deepcopy(raw);bad['rows'][0]['citations'][0]['citation_id']='UNKNOWN'
    with pytest.raises(ValidationError):validate(bad,schema)
    with pytest.raises(ValueError):expand(bad)
    assert sources[0]['text']=='첫째\n둘째' and receipt['citation_count']==2


def test_basis_system_identifiers_and_date():
    sources,pair=sample();view,schema,expand,_=prepare('BASIS',{'sources':sources,'as_of':'2026-10-15'},BASIS)
    pair.pop('pair_id');pair['applicability'].pop('as_of');pair['applicability']['citations']=[]
    value={'pairs':[pair],'gaps':[],'summary':'미확인'};validate(value,schema)
    got=expand(value);validate(got,BASIS)
    assert got['pairs'][0]['pair_id']=='P1' and got['pairs'][0]['applicability']['as_of']=='2026-10-15'


def comparison_context(monkeypatch,pairs,decide):
    import workflow.presentation as presentation
    sources,_=sample();saved=[];events=[]
    state={'basis':{'pairs':pairs,'gaps':[]},'scope':{'issues':[{'id':'q1','label':'질문','numeric':False}]}}
    def packets(ctx,state,stage,**kwargs):
        return [({'packet':{'index':0,'count':1,'plan_hash':stage,'dependency_closure_complete':True}},sources)]
    monkeypatch.setattr(presentation,'packets',packets)
    monkeypatch.setattr(presentation,'checkpoint',lambda *a:None)
    ctx=NS(request={'use_llm':True},repo=NS(save=lambda s:saved.append(deepcopy(s)),work=NS(event=lambda *a:events.append(a))),model=NS(decide=decide))
    return ctx,state,saved,events


def test_ineligible_pair_zero_calls_and_replay(monkeypatch):
    _,pair=sample()
    ctx,state,saved,events=comparison_context(monkeypatch,[pair],lambda *a:pytest.fail('ineligible pair called LLM'))
    first=cmp.compare(ctx,state);second=cmp.compare(ctx,state)
    assert first==second and first['rows'][0]['verdict']=='DEFERRED'
    assert saved[-1]['comparison']==first and events[0][0]=='WORKFLOW_COMPARISON_GATE'


@pytest.mark.parametrize('failure',['WORKFLOW_REPAIR_EXHAUSTED','WORKFLOW_MODEL_OUTCOME_UNKNOWN'])
def test_prior_accepted_row_survives_later_failure(monkeypatch,failure):
    _,pair=sample();later=deepcopy(pair);later.update(pair_id='P2',comparison_eligibility=True,basis_relation='DIRECT');later['applicability']['status']='MATCH'
    def fail(*a):raise WorkflowError(failure,'test')
    ctx,state,saved,_=comparison_context(monkeypatch,[pair,later],fail)
    if failure=='WORKFLOW_REPAIR_EXHAUSTED':
        result=cmp.compare(ctx,state);assert len(result['rows'])==2
    else:
        with pytest.raises(WorkflowError):cmp.compare(ctx,state)
    assert saved[-1]['comparison']['rows'][0]['pair_id']=='P1'


@pytest.mark.parametrize('fault',['hash','binding'])
def test_persisted_comparison_tamper_fails_closed(monkeypatch,fault):
    _,pair=sample();ctx,state,_,_=comparison_context(monkeypatch,[pair],lambda *a:pytest.fail())
    cmp.compare(ctx,state)
    if fault=='hash':next(iter(state['comparison_progress']['completed'].values()))['result']['rows'][0]['reason']='tamper'
    else:state['basis']['pairs'][0]['reason']='changed'
    with pytest.raises(WorkflowError):cmp.compare(ctx,state)


def test_system_definition_read_is_real_once_and_not_adopted(session):
    native,_=session;inv,_=install(native)
    de.acquire_initial(inv)
    assert inv.p['selected'] and not inv.active_records()
    old=deepcopy(inv.p['read_plans']);de.acquire_initial(inv)
    assert inv.p['read_plans']==old and inv.p['system_definition_seed']['status']=='COMPLETE'


def test_system_definition_rejects_corrupted_original(session):
    native,_=session;inv,_=install(native)
    native.sources.tools.definitions['0']['source_text_sha256']='tamper'
    with pytest.raises(ContractError):de.acquire_initial(inv)
    assert not inv.p['selected']


@pytest.mark.parametrize('side',['internal','external'])
def test_child_role_available_only_inside_trusted_execution(side):
    assert task_instructions()==''
    with child_execution(None,None,'c',[],task={'source_category':side,'search_hints':[]}):
        assert ('내규' if side=='internal' else '외규')+' 조사' in task_instructions()
    assert task_instructions()==''
