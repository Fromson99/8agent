"""Teach synthetic transports the new wire vocabulary; product validators intact."""
from copy import deepcopy
import pytest

@pytest.fixture(autouse=True)
def ordinary_wire_fixture(monkeypatch):
 from pathlib import Path
 root=Path(__file__).resolve().parents[3]
 monkeypatch.syspath_prepend(str(root/'06_TOOLS/EXPERIMENTS/adr_1188'))
 import api_fixture_integrated as fixture
 from semantic_runtime.legal_agent import assessment_input as ai
 decode=fixture.decode;last={}
 def read(value):
  result=decode(ai.restore(value) if ai.META in value else value)
  last.clear();last.update(deepcopy(result));return result
 monkeypatch.setattr(fixture,'decode',read)
 import test_legal_agent_double_harness as harness
 original=harness.wire
 def response(value):
  if 'read_judgment_review' in value or 'requirement_review' in value:
   value=deepcopy(value);ctx=last.get('read_judgments',{})
   targets={t['id']:t for t in ctx.get('need_continuity',{}).get('targets',[])}
   ids={n['id'] for n in ctx.get('needs',[]) if n.get('origin') in ('SOURCE_GOAL','STRUCTURE_SELECTION') and n.get('target_refs')
        and all(targets.get(t,{}).get('available_complete') and targets[t]['available_evidence_refs'] for t in n['target_refs'])}
   if 'read_judgment_review' in value:
    value['read_judgment_review']['needs']=[n for n in value['read_judgment_review']['needs'] if n['id'] not in ids]
   if 'review_links' not in value:
    from fixtures import share
    value=share(value)
   else:
    def refs(v):
     if isinstance(v,dict):return ({v['link_ref']} if 'link_ref' in v else set())|set().union(*(refs(x) for x in v.values()))
     if isinstance(v,list):return set().union(*(refs(x) for x in v))
     return set()
    used=refs({k:v for k,v in value.items() if k!='review_links'})
    value['review_links']=[r for r in value['review_links'] if r['id'] in used]
  return original(value)
 monkeypatch.setattr(harness,'wire',response)
