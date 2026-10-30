"""Test consumer of compact wire. Stage supplied out-of-band for fixture routing."""
from copy import deepcopy
from semantic_runtime.legal_agent.navigation_input import expand_cards
last_stage='';observations=[]
def instrument(monkeypatch):
 from semantic_runtime.legal_agent import compact_model_input as m
 old=m.project
 def wrapped(view,schema):
  global last_stage
  last_stage=view.get('source_stage','')
  out=old(view,schema);observations.append(deepcopy(out));return out
 monkeypatch.setattr(m,'project',wrapped)
def decode(value):
 view=expand_cards(value)
 if 'source_stage' not in view:view['source_stage']=last_stage;view['phase']='investigate'
 if isinstance(view.get('tool_options'),dict):view['tool_options']=[dict(row,choice=kind) for kind,rows in view['tool_options'].items() for row in rows]
 view.setdefault('sources',[])
 if 'references' in view:view['references'].setdefault('dependency_cards',[])
 ctx=view.get('read_judgments',{})
 for k in ('judgments','needs','conflicts','required'):ctx.setdefault(k,[])
 return view
