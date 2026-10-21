from copy import deepcopy
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import decision_projection as dp
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.contracts import digest

def fixture(*,route='REFERENCE',historical=False,status='READ',accepted=True):
 span={'block_id':'1','start_cp':0,'end_cp':2,'text':'원문'}
 page={'id':'E1','branch_id':'B1','source_id':'S1','document_id':'D1','text':'원문','spans':[span],'page':1,'total_pages':1,'scope_id':digest({'old':True})}
 record={'source_id':'S1','document_id':'D1','document_name':'문서','heading':'조문','offer':{'new':True} if historical else {'old':True}}
 state={'requested_originals':['B1'] if route=='READ_ARTICLES' else [],'selected':{'B1':record},'basis_history':{'E1':{**page,'accepted':accepted}},'groups':{'B1':{'status':status,'page_plan':[] if historical else [[]]}}}
 session=SimpleNamespace(scope={'D1'},store=SimpleNamespace(source=lambda *a:{'text':'원문'}),profile={'max_read_chars':4,'max_context_chars':100})
 inv=SimpleNamespace(p=state,s=session,render_page=lambda *a:deepcopy(page));return inv,{'sources':[],'basis':[]}

@pytest.mark.parametrize('route',['READ_ARTICLES','REFERENCE','READ_PARENT','READ_SCOPE','VIEW_SAVED_SOURCE'])
def test_every_actual_delivered_route_remains_context(route):
 inv,data=fixture(route=route);before=deepcopy(inv.p)
 assert dp.retain_requested(inv,data)==['E1'] and data['sources'][0]['text']=='원문'
 assert dp.bounded_original_refs(inv.p,[],50)[0]==['E1']
 assert inv.p==before and not data['retained_original_context']['automatic_adoption']
 assert dp.retain_requested(inv,data)==[]

@pytest.mark.parametrize('route',['REFERENCE','READ_SCOPE'])
def test_changed_page_plan_retains_exact_historical_scope(route):
 inv,data=fixture(route=route,historical=True);old=deepcopy(inv.p['basis_history']['E1'])
 assert dp.retain_requested(inv,data)==['E1'];p=data['sources'][0]
 assert p['id']==old['id'] and p['scope_id']==old['scope_id'] and p['spans']==old['spans']
 assert p['retained_historical_scope'] and p['selected_scope_complete'] is None
 assert p['scope_id']!=digest(inv.p['selected']['B1']['offer'])

@pytest.mark.parametrize('status',['DEFERRED','EXCLUDED'])
def test_explicit_disposition_preserved(status):
 inv,data=fixture(status=status)
 assert dp.retain_requested(inv,data)==[] and dp.bounded_original_refs(inv.p,[],50)[0]==[]

def test_preview_and_unconfirmed_not_original():
 inv,data=fixture(accepted=False);assert dp.retain_requested(inv,data)==[]
 inv,data=fixture();inv.p['selected']={};assert dp.requested_refs(inv.p)==[]

@pytest.mark.parametrize('failure',['acl','source','span'])
def test_historical_page_still_validates_provenance(failure):
 inv,data=fixture(historical=True)
 if failure=='acl':inv.s.scope=set()
 elif failure=='source':inv.p['selected']['B1']['source_id']='different'
 else:inv.p['basis_history']['E1']['spans'][0]['text']='변조'
 with pytest.raises(ContractError):dp.retain_requested(inv,data)

def test_whole_page_budget_and_mandatory_priority():
 inv,data=fixture();refs,receipt=dp.bounded_original_refs(inv.p,[],1)
 assert refs==[] and receipt['omitted_by_context_budget']==['E1'] and not receipt['source_absence_proven']
 refs,receipt=dp.bounded_original_refs(inv.p,['E1','E1'],1)
 assert refs==[] and receipt['mandatory_basis_refs']==['E1'] and not receipt['omitted_by_context_budget']

def test_resume_preserves_original_order_without_reacquisition():
 inv,data=fixture(route='REFERENCE',historical=True);restored=deepcopy(inv.p)
 assert dp.original_groups(restored)==['B1']
 assert dp.bounded_original_refs(restored,[],50)==dp.bounded_original_refs(inv.p,[],50)
