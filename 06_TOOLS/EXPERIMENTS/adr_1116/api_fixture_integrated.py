"""Test consumer of compact wire. Stage supplied out-of-band for fixture routing."""
from copy import deepcopy
from semantic_runtime.legal_agent.navigation_input import expand_cards
last_stage='';observations=[];last_mapping={}
def instrument(monkeypatch):
 from semantic_runtime.legal_agent import compact_model_input as m
 old=m.project
 def wrapped(view,schema=None):
  global last_stage,last_mapping
  last_stage=view.get('source_stage','');last_mapping=deepcopy(view.get('reference_registry',{}).get('mapping',{}))
  out=old(view,schema);observations.append(deepcopy(out));return out
 monkeypatch.setattr(m,'project',wrapped)
def decode(value):
 view=expand_cards(value)
 if 'source_stage' not in view:view['source_stage']=last_stage;view['phase']='investigate'
 if isinstance(view.get('tool_options'),dict):view['tool_options']=[dict(row,choice=kind) for kind,rows in view['tool_options'].items() for row in rows]
 view.setdefault('sources',[])
 if 'references' in view:view['references'].setdefault('dependency_cards',[])
 ctx=view.get('read_judgments',{})
 for k in ('judgments','needs','conflicts','required','current_originals'):ctx.setdefault(k,[])
 return view

# Translate only fixed fixture identities into the actual displayed vocabulary.
# Model-selected source/target handles and all legal strings are untouched.
def to_wire(value,key=None):
 if isinstance(value,dict):return {k:to_wire(v,k) for k,v in value.items()}
 if isinstance(value,list):return [to_wire(v,key) for v in value]
 if isinstance(value,str) and value in ('Q1','K1') and key in ('issue_id','issue_refs','claim_id','claim_refs'):
  return last_mapping.get(value,value)
 return value
