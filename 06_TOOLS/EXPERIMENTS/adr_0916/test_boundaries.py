from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import evidence_inventory as inv
from semantic_runtime.legal_agent.errors import ContractError

@pytest.mark.parametrize('text',['가😀나','e\u0301\n조건','甲\r\n乙','x'*37])
@pytest.mark.parametrize('capacity',['short','exact','extra'])
def test_acquired_parent_and_child_are_never_split_at_unicode_boundary(monkeypatch,text,capacity):
    def ev(i,t):return {'source_id':'new-source','document_id':'new-doc','evidence_id':i,'spans':[{'text':t}]}
    child=ev('child','제출한다');parent=ev('parent',text)
    rec={'complete':True,'source_id':'new-source','document_id':'new-doc','evidence':[child]}
    state={'groups':{'read':{'status':'READ'}},'selected':{'read':rec},'contexts':{'p':{**rec,'evidence':[parent]}}};before=deepcopy(state)
    checked=[];session=S(scope={'new-doc'},source=S(verify=lambda e:checked.append(e['evidence_id'])))
    monkeypatch.setattr(inv,'_pack',lambda s,p,r,spans:[{'source_id':k,'spans':v} for k,v in spans.items()])
    capacity=len(text)+len('제출한다')+{'short':-1,'exact':0,'extra':17}[capacity]
    originals,evidence,omitted=inv.acquired_originals_for(session,state,capacity)
    assert checked==['child','parent'] and state==before
    if capacity<len(text)+len('제출한다'):assert not originals and not evidence and set(omitted)=={'child','parent'}
    else:assert {x['evidence_id'] for x in evidence}=={'child','parent'} and not omitted and originals[0]['delivered_context_only']

@pytest.mark.parametrize('failure',['parent_incomplete','parent_document','parent_source_evidence','parent_hash'])
def test_governing_context_failure_does_not_publish_child(monkeypatch,failure):
    child={'source_id':'s','document_id':'d','evidence_id':'c','spans':[{'text':'보고'}]};parent={**child,'evidence_id':'p'}
    rec={'complete':True,'source_id':'s','document_id':'d','evidence':[child]};context={**rec,'evidence':[parent]}
    state={'groups':{'g':{'status':'READ'}},'selected':{'g':rec},'contexts':{'p':context}}
    if failure=='parent_incomplete':context['complete']=False
    if failure=='parent_document':context['document_id']='allowed-other'
    if failure=='parent_source_evidence':parent['source_id']='different-source'
    def verify(e):
        if failure=='parent_hash' and e['evidence_id']=='p':raise ContractError('source hash mismatch')
    monkeypatch.setattr(inv,'_pack',lambda *a:pytest.fail('unverified bundle reached publisher'))
    session=S(scope={'d','allowed-other'},source=S(verify=verify))
    with pytest.raises(ContractError):inv.acquired_originals_for(session,state,100)
