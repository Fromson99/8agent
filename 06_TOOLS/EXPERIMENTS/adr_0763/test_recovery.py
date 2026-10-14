import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"05_TESTS/CONTRACTS"))
from copy import deepcopy
import json
import pytest
from conftest import term_glossary
from test_unit_fulltext_adaptive_read import tree,session
from test_structure_reading import setup,value
from test_structure_first_search import matcher
from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,compact_cards
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.errors import ProposalError,ContractError

def test_document_bound_with_unresolved_heading():
 m=matcher();q='자본시장법에서 위탁 투표 신고 내용을 찾아 주세요.'
 scope=ln.request_scope_view(q,m,['law','decree'])
 assert scope['status']=='BOUND' and scope['document_id']=='law' and scope['unit_id'] is None
 span=scope['quote_span'];assert q[span['start']:span['end']]==span['text']

@pytest.mark.parametrize('q',['자본시장법 제6조와 제7조 비교','자본시장법 제6조만 빼고 설명','자본시장법 제6조는 제외하고 다른 조항','자본시장법 제99조 안에서만 설명','자본시장법은 제외하고 시행령을 설명'])
def test_ambiguous_or_excluded_does_not_add_wide_scope(q):
 assert ln.request_scope_view(q,matcher(),['law','decree'])['status']=='UNKNOWN'

def test_explicit_subtree_requires_unique_authorized_original():
 q='자본시장법 제6조제1항 안에서만 설명해 주세요.';m=matcher()
 scope=ln.request_scope_view(q,m,['law','decree'])
 assert scope['hard_bound'] and scope['unit_id']=='제6조제1항'
 assert ln.request_scope_view(q,m,['decree'])['status']=='UNKNOWN'
 m.stored_coordinates={**m.stored_coordinates,('law','dup'):m.stored_coordinates[('law','제6조제1항')]}
 m.units[('law','dup')]={'coordinate_scope':'body'}
 assert ln.request_scope_view(q,m,['law'])['status']=='UNKNOWN'

def test_wrong_read_focus_keeps_document_search_and_exact_identity(session):
 native,_=session;inv,_=setup(native)
 inv.p['structure_location']={'document_id':'d','unit_id':'2','offset':0}
 data,actions=inv.view();law=data['laws'][0]
 current=law['body_search_action'];request=law['request_body_search_action']
 assert current!=request and actions[current]['identity']['unit_id']=='2'
 assert actions[request]['identity']=={'document_id':'d','unit_id':None}
 decision=value(data,'SEARCH_BODY',request,['승인']);inv.validate(decision,data,actions);inv.execute(decision,data,actions)
 assert inv.p['fulltext_scopes']['d'] is None
 after,actions=inv.view();assert after['search_status']['attempts'][-1]['mode']=='FULLTEXT'
 assert after['search_status']['attempts'][-1]['result']['total'] is not None
 request=after['laws'][0]['request_body_search_action']
 with pytest.raises(ProposalError,match='unchanged body'):
  inv.validate(value(after,'SEARCH_BODY',request,['승인']),after,actions)
 # Different expression through same handle is not a repeated action.
 inv.validate(value(after,'SEARCH_BODY',request,['긴급']),after,actions)


def test_same_scope_targets_deduplicate_and_wire_survives(session):
 native,_=session;inv,_=setup(native);data,actions=inv.view();law=data['laws'][0]
 assert law['body_search_action']==law['request_body_search_action']
 assert len(law['body_search_scopes'])==1
 model=inv.model_view(data);assert 'previous_search_queries' not in model
 refs=NavigationReferences(model)
 wire=compact_cards(compact_wire_view(refs.view(model),"select"))
 assert 'search_status' in wire
 assert refs.restore(refs.view(model))==model
 assert json.loads(json.dumps(wire,ensure_ascii=False))['search_status']['attempts'][0]['mode']=='STRUCTURE'


def test_heading_failure_not_hidden_by_nonempty_document_catalogue(session):
 native,_=session;inv,_=setup(native)
 inv.p['structure_page']['resolutions']=[{'status':'MISS','reason':'MISSING_OR_AMBIGUOUS_HEADING','failure':{'code':'UNRESOLVED_HEADING'}}]
 inv.p['structure_page']['lookup_status']='NEEDS_SELECTION';inv.p['structure_page']['failure']=None
 data,_=inv.view();status=data['search_status']
 assert status['document_match']=='MATCH'
 assert status['heading_resolution'][0]['failure']['code']=='UNRESOLVED_HEADING'
 assert [a['mode'] for a in status['attempts']]==['STRUCTURE']


def test_hard_bound_has_no_research_or_parent_read_escape(session):
 native,_=session;inv,_=setup(native)
 # Scope resolver is independently checked above; use verified fixture subtree.
 inv.request_scope.update(status='BOUND',document_id='d',unit_id='2',hard_bound=True)
 inv.p['structure_location']={'document_id':'d','unit_id':'3','offset':0}
 data,actions=inv.view()
 assert not any(a['action'] in ('RESEARCH','FOLLOW_CONNECTION') for a in actions.values())
 assert {a['identity']['unit_id'] for a in actions.values() if a['action']=='SEARCH_BODY'}=={'2','3'}
 assert not inv.scope_allows({'action':'READ_ARTICLES','identity':{'document_id':'d','unit_id':'1'}})
 assert not inv.scope_allows({'action':'SEARCH_BODY','identity':{'document_id':'other','unit_id':'2'}})
 assert inv.scope_allows({'action':'READ_ARTICLES','identity':{'document_id':'d','unit_id':'3'}})


def test_resume_preserves_scope_and_search_receipts(session):
 native,_=session;inv,rec=setup(native);before,_=inv.view();checkpoint=deepcopy(inv.p)
 restored=ln.Investigation(native.sources,inv.question,rec,None,120,checkpoint,None)
 after,_=restored.view();assert after['search_status']==before['search_status']
 old=deepcopy(checkpoint);old['binding']='old-contract'
 with pytest.raises(ContractError,match='binding changed'):
  ln.Investigation(native.sources,inv.question,rec,None,120,old,None)


def test_repair_does_not_demand_arbitrary_adoption(session):
 native,_=session;inv,_=setup(native);data,actions=inv.view()
 _,feedback=ln.repair_contract(data,actions,set(inv.p['groups']),value(data,'FINISH'),ProposalError('no adopted originals for completion'))
 c=next(c for c in feedback['conflicts'] if c['code']=='NO_ADOPTED_ORIGINALS')
 assert len(c['corrections'])==3 and '무관한 원문' in c['corrections'][0]
