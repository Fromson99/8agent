from contextlib import contextmanager
from copy import deepcopy
import json,sqlite3
import pytest
from semantic_runtime.legal_agent import compact_model_input as minimal
from semantic_runtime.legal_agent.relations_repository import RelationsRepository
from semantic_runtime.legal_agent.tools_repository import ToolsRepository
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,expand_cards
from semantic_runtime.legal_agent.gateway import compact_wire_view,WIRE_PROJECTION
from semantic_runtime.legal_agent.repository import encoded
from semantic_runtime.legal_agent.errors import ContractError

@pytest.mark.parametrize('tamper',['none','text','target','documents','request_binding','view_binding','version','no_projection','order'])
def test_repository_rebuilds_exact_model_copy_before_attempt(tamper,monkeypatch):
 source=' 원문\n조건과 예외 '
 schema={'properties':{'target':{'enum':['T'+'a'*28]},'basis':{'enum':['E'+'a'*28]}}}
 view=minimal.bind({'view_id':'V1','phase':'investigate','source_stage':'source-law-navigation-1-read-choice-page-1-0',
  'input_projection':'compact-selection-source-v3','sources':[{'id':'E'+'a'*28,'document_id':'d2','document_name':'나규정','text':source}],
  'read_candidates':[{'target':'T'+'a'*28,'document_id':'d1','document_name':'가규정','preview':'미리보기'}]},schema)
 stored=json.loads(encoded(view));refs=NavigationReferences(view)
 wire=minimal.project(compact_wire_view(refs.view(view),'investigate'),refs.schema(schema))
 repo=RelationsRepository.__new__(RelationsRepository);repo.VERSION=6;repo.db=sqlite3.connect(':memory:')
 repo.db.execute('CREATE TABLE model_view(view_id PRIMARY KEY,body_json)');repo.db.execute('INSERT INTO model_view VALUES(?,?)',('V1',encoded(stored)))
 repo.db.commit();events=[];repo.event=lambda k,v:events.append((k,v));reserved=[]
 monkeypatch.setattr(ToolsRepository,'reserve_attempt',lambda *a,**kw:reserved.append(True) or 'A1')
 kw={'numbered_references':refs,'wire_projection':WIRE_PROJECTION,'minimal_input_projection':minimal.VERSION}
 if tamper=='text':wire['sources'][0]['text']+='변조'
 elif tamper=='target':wire['read_candidates'][0]['target']='T999'
 elif tamper=='documents':wire['documents'][0]['name']='다른 규정'
 elif tamper=='request_binding':wire['minimal_input_binding']={'version':minimal.VERSION,'selection_refs':[]}
 elif tamper=='view_binding':view['minimal_input_binding']['selection_refs']=[]
 elif tamper=='version':kw['minimal_input_projection']='unsupported'
 elif tamper=='no_projection':kw.pop('minimal_input_projection')
 elif tamper=='order':view=json.loads(json.dumps(view,sort_keys=True));assert wire==minimal.project(compact_wire_view(refs.view(view),'investigate'),refs.schema(schema))
 request={'messages':[{'role':'system','content':'system'},{'role':'user','content':encoded({'view':wire})}]}
 if tamper in ('none','order'):
  assert repo.reserve_attempt(view,request,'L',1,'investigate',**kw)=='A1'
  assert reserved==[True] and any(k=='MINIMAL_INPUT_PROJECTION' for k,v in events)
 else:
  with pytest.raises(ContractError):repo.reserve_attempt(view,request,'L',1,'investigate',**kw)
  assert not reserved
 repo.db.close()
