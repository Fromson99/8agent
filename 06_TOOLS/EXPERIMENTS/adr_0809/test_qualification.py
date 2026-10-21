"""Prospective finite software boundary cases, not semantic accuracy holdout."""
from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent.workflow_execution import entry_proposal
from workflow.adapters.projection import prepare
from workflow.risk_team_compare_workflow.contracts import BASIS
from workflow.risk_team_compare_workflow import compare as cmp
from workflow.contracts import WorkflowError
from test_system_mechanics import sample,comparison_context


@pytest.mark.parametrize('n',[5,11])
@pytest.mark.parametrize('side',['internal','external'])
def test_T01_multiple_parent_issues_and_literal_facts(n,side):
    original='회사 Z가 검토합니다.\n기준일 2026-09-17, 조건과 예외를 비교해 주세요.'
    task={'source_category':side,'search_hints':['조건과 예외'],
      'issues':[{'id':'issue-'+str(17+i*7),'question':'항목 '+str(i)+'의 조건과 예외','numeric':i%2==1} for i in range(n)],
      'facts':[{'name':'회사','value':'Z','user_quote':'회사 Z'},
               {'name':'기준일','value':'2026-09-17','user_quote':'기준일 2026-09-17'}]}
    before=deepcopy(task);out=entry_proposal(task,original,True)
    assert len(out['intent']['issues'])==n and task==before
    assert out['command']['facts']==task['facts'] and out['command']['source_category']==side
    assert [i['question'] for i in out['intent']['issues']]==[i['question'] for i in task['issues']]
    assert all(i['request_quote']==original for i in out['intent']['issues'])


@pytest.mark.parametrize('size',[11,12001,24003])
def test_T02_exact_unicode_partition_and_distinct_source_identity(size):
    original=('① 조건🙂\r\n② 예외\t'*3000)[:size]
    sources=[{'evidence_id':'E'+str(k),'side':side,'text':original,'spans':[{'text':original}]} for k,side in enumerate(['internal','external'],41)]
    before=deepcopy(sources);view,wire,_,_=prepare('BASIS',{'sources':sources,'scope':{'issues':[{'id':'Q17'}]}},BASIS)
    ids=[]
    for s in view['sources']:
        assert ''.join(v['text'] for v in s['citation_options'])==original
        assert all(len(v['text'])<=12000 and v['text'] in original for v in s['citation_options'])
        ids.extend(v['citation_id'] for v in s['citation_options'])
    assert len(ids)==len(set(ids)) and sources==before


def test_T03_independent_three_issue_rows_and_reconstructed_restart(monkeypatch):
    _,base=sample();pairs=[]
    for k in range(3):
        p=deepcopy(base);p.update(pair_id='P'+str(k+7),issue_id='Q'+str(17+k*7))
        if k<2:p.update(comparison_eligibility=True,basis_relation='DIRECT');p['applicability']['status']='MATCH'
        pairs.append(p)
    calls=[]
    def decide(*args):
        calls.append(args[0])
        if len(calls)==2:raise WorkflowError('WORKFLOW_REPAIR_EXHAUSTED','검사에서 의도한 두 번째 쟁점 실패')
        value=cmp.deferred(pairs[0],state['scope']['issues'],'모의 양측 확인')
        value['rows'][0].update(verdict='CONFORMS',difference='모의 동일 조항',unresolved=[])
        return value
    ctx,state,saved,_=comparison_context(monkeypatch,pairs,decide)
    state['scope']['issues']=[{'id':p['issue_id'],'label':'독립 쟁점 '+p['issue_id'],'numeric':False} for p in pairs]
    first=cmp.compare(ctx,state)
    assert [r['pair_id'] for r in first['rows']]==['P7','P8','P9']
    assert [r['verdict'] for r in first['rows']]==['CONFORMS','DEFERRED','DEFERRED'] and len(calls)==2
    restored=json.loads(json.dumps(saved[-1]));ctx.model.decide=lambda *a:pytest.fail('complete row recalled model')
    assert cmp.compare(ctx,restored)==first and len(calls)==2
