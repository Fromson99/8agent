from copy import deepcopy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'adr_0694'))
from test_structure_reading import setup,tree,session,hit,value
from test_completion_v4 import claim
from semantic_runtime.legal_agent import law_navigation as ln, completion_contracts as cc


def contradictions(value):
 out=[]
 if isinstance(value,dict):
  if 'minItems' in value and 'maxItems' in value and value['minItems']>value['maxItems']:out.append(value)
  for v in value.values():out.extend(contradictions(v))
 elif isinstance(value,list):
  for v in value:out.extend(contradictions(v))
 return out


def test_empty_structural_menu_has_no_impossible_decision(session):
 native,_=session;inv,_=setup(native);view,actions=inv.view()
 assert not view['branches']
 schema=ln.decision_schema(view,actions,set())
 assert not contradictions(schema)
 assert 'DECIDE' not in schema['properties']['next_action']['enum']
 assert {'SEARCH_STRUCTURE','SEARCH_BODY'}<=set(schema['properties']['next_action']['enum'])
 sid=hit(native)['source_id'];a={'T':{'id':'T','action':'READ_ARTICLES','identity':{'source_id':sid,'document_id':'d','unit_id':'2'},'label':'article'}}
 inv.execute_tool(value(view,'READ_ARTICLES','T'),{'sources':[]},a)
 view,actions=inv.view();assert view['branches']
 schema=ln.decision_schema(view,actions,set(inv.p['groups']))
 assert 'DECIDE' in schema['properties']['next_action']['enum'] and not contradictions(schema)


def test_explicit_nested_refs_are_bound_without_semantic_or_input_mutation():
 c=claim();c['evidence_refs']=['S1'];v={'claims':[c]};before=deepcopy(v)
 opts=[{'id':s,'source_id':s,'text':'모의 원문'} for s in ['S1','S2']]
 fixed,changes=cc.bind_rule_evidence(v,opts)
 assert v==before and changes
 assert fixed['claims'][0]['evidence_refs']==['S1','S2']
 assert fixed['claims'][0]['rule']==before['claims'][0]['rule']
 assert not cc.rule_errors(fixed['claims'][0])
 again,changes=cc.bind_rule_evidence(fixed,opts);assert again==fixed and not changes


def test_unoffered_nested_refs_remain_rejected():
 c=claim();c['evidence_refs']=['S1'];c['rule']['exceptions'][0]['evidence_refs']=['UNREAD']
 v={'claims':[c]};fixed,changes=cc.bind_rule_evidence(v,[{'id':'S1'}])
 assert fixed==v and not changes and cc.rule_errors(fixed['claims'][0])
