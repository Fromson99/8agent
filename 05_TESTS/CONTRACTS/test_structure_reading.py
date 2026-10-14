from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_unit_fulltext_adaptive_read import tree,session,hit
from test_law_grouped_navigation import enable,decide
from semantic_runtime.legal_agent import law_candidates as lc,law_navigation as ln,unit_reading as ur
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.errors import ContractError


def setup(native,question='모의승인규정'):
 s=native.sources;enable(s,structure_first=True,investigation_control=True,completion_contract=True,batch_selected_pages=True)
 s.context.request['question']=question
 rec=SourceRecall(s).prepare()
 inv=ln.Investigation(s,question,rec,None,120,None,None)
 return inv,rec


def value(data,action,target=None,queries=()):
 v=decide(data,action,target);v.update(expected_state_version=data['state_version'],law_decisions=[],branch_decisions=[],queries=list(queries))
 return v


def test_discovery_and_first_menu_never_call_body_fts(session,monkeypatch):
 native,idx=session
 def forbidden(*a,**k):pytest.fail('global body search before structural selection')
 for name in ['law_groups_page','article_groups_page','hit_page']:monkeypatch.setattr(idx,name,forbidden)
 inv,rec=setup(native)
 data,actions=inv.view()
 assert rec['discovery_mode']=='structure' and data['laws']
 assert data['laws'][0]['document_structure']['children']
 assert any(a['action']=='SEARCH_BODY' for a in actions.values())
 assert not any(a['action']=='NEXT_LAWS' for a in actions.values())


def test_missing_structure_stays_empty_without_fulltext(session,monkeypatch):
 native,idx=session
 monkeypatch.setattr(idx,'law_groups_page',lambda *a,**k:pytest.fail('silent global fallback'))
 inv,rec=setup(native,'존재하지않는이름흠')
 assert rec['unit_hits']==[]
 data,actions=inv.view()
 assert not data['laws'] and not data['sources']
 assert {a['action'] for a in actions.values()} >= {'SEARCH_STRUCTURE','RESEARCH'}
 assert 'SEARCH_BODY' not in {a['action'] for a in actions.values()}


def test_subtree_filters_body_search_before_rank_and_binds_cursor(session):
 native,idx=session;s=native.sources;enable(s,structure_first=True)
 keys=lc.fulltext_scope_keys(s,'d','2');sid=hit(native)['source_id'];db=s.matcher.unit_fulltext_db
 page=idx.hit_page(db,['승인'],sid,lc.allowed(s),unit_keys=keys,limit=1)
 assert page['total']==2 and page['next_cursor']
 second=idx.hit_page(db,['승인'],sid,lc.allowed(s),unit_keys=keys,cursor=page['next_cursor'])
 assert {h['unit_id'] for h in page['items']+second['items']}=={'2','3'}
 with pytest.raises(ValueError,match='cursor'):
  idx.hit_page(db,['승인'],sid,lc.allowed(s),unit_keys=lc.fulltext_scope_keys(s,'d','1'),cursor=page['next_cursor'])
 with pytest.raises(ContractError):lc.fulltext_scope_keys(s,'other')
 assert idx.hit_page(db,['승인'],sid,lc.allowed(s),unit_keys=set())['items']==[]


def test_explicit_body_action_preserves_chosen_scope(session):
 native,idx=session;inv,_=setup(native)
 inv.p['structure_location']={'document_id':'d','unit_id':'2','offset':0}
 data,actions=inv.view();target=data['laws'][0]['body_search_action']
 decision=value(data,'SEARCH_BODY',target,['승인']);inv.validate(decision,data,actions);inv.execute(decision,data,actions)
 assert inv.p['fulltext_scopes']=={'d':'2'}
 assert all(g['hit']['unit_id'] in ('2','3') for g in inv.p['groups'].values())
 after,actions=inv.view()
 assert all(a['identity'].get('unit_id')=='2' for a in actions.values() if a['action']=='READ_ARTICLES' and 'unit_id' in a['identity'] and a['identity'].get('source_id')==hit(native)['source_id'] and a['label'].endswith('전체 원문 읽기') and a['identity']['unit_id'] not in ('3',))
 assert inv.p['selected']=={} # previews are not adopted original scopes


def test_scope_cannot_be_used_without_explicit_selection(session):
 native,_=session;inv,_=setup(native)
 with pytest.raises(ContractError,match='explicit'):inv.fulltext_args('d')


def test_duplicate_acquisition_has_one_read_and_preserves_requested_scope(session,monkeypatch):
 native,_=session;s=native.sources;h=hit(native);calls=[];orig=ur.read
 def counted(*a,**k):calls.append(a[2]['id']);return orig(*a,**k)
 monkeypatch.setattr(ur,'read',counted)
 reads=ur.acquire_batch(s,[h,deepcopy(h)],ur.read_state(s))
 assert len(reads)==len(calls)==1
 reads=ur.acquire_batch(s,[{**h,'requested_unit_id':'1'},{**h,'requested_unit_id':'2'}],ur.read_state(s))
 assert len(reads)==2


def test_interrupted_read_plan_resumes_completed_substeps(session,monkeypatch):
 native,_=session;inv,rec=setup(native);sid=hit(native)['source_id']
 actions={f'T{i}':{'id':f'T{i}','action':'READ_ARTICLES','identity':{'source_id':sid,'document_id':'d','unit_id':uid},'label':'test'} for i,uid in enumerate(('2','5'))}
 data,_=inv.view();decision=value(data,'READ_ARTICLES');decision['targets']=list(actions)
 orig=ur.read;calls=[]
 def fail_second(s,h,o,**kw):
  if o['extent']=='subtree':
   calls.append(o['id'])
   if o['unit_id']=='5':raise RuntimeError('simulated interruption')
  return orig(s,h,o,**kw)
 monkeypatch.setattr(ur,'read',fail_second)
 with pytest.raises(RuntimeError):inv.execute_tool(decision,{'sources':[]},actions)
 plan=next(iter(inv.p['read_plans'].values()));assert plan['status']=='INTERRUPTED' and len(plan['completed'])==1
 checkpoint=deepcopy(inv.p);monkeypatch.setattr(ur,'read',orig)
 resumed=ln.Investigation(native.sources,inv.question,rec,None,120,checkpoint,None)
 resumed.execute_tool(decision,{'sources':[]},actions)
 plan=next(iter(resumed.p['read_plans'].values()))
 assert plan['status']=='ACQUIRED' and len(plan['completed'])==2
 assert all(g['status']!='ACTIVE' for g in resumed.p['groups'].values())
 assert resumed.p['basis_history']=={}


def test_selected_pages_batched_without_adoption_or_early_delivery(session):
 native,_=session;inv,rec=setup(native);sid=hit(native)['source_id']
 native.sources.profile['max_context_chars']=100000
 actions={'T':{'id':'T','action':'READ_ARTICLES','identity':{'source_id':sid,'document_id':'d','unit_id':'0'},'label':'all'}}
 data,_=inv.view();inv.execute_tool(value(data,'READ_ARTICLES','T'),{'sources':[]},actions)
 data,actions=inv.view()
 assert len(data['sources'])>1 and data['read_batch']['automatic_adoption'] is False
 assert inv.p['basis_history']=={} and all(g['status']!='ACTIVE' for g in inv.p['groups'].values())
 assert data['sources'][-1]['selected_scope_complete']
 inv.execute_tool(value(data,'PENDING'),data,actions)
 assert len(inv.p['basis_history'])==len(data['sources'])
 assert all(g['status']!='ACTIVE' for g in inv.p['groups'].values())
