"""Prospective minimal-input contracts using no network or corpus loader."""
import json,sqlite3
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import compact_model_input as minimal,read_candidate_pages as pages
from semantic_runtime.legal_agent import request_repair as rr
from semantic_runtime.legal_agent.errors import BudgetExhausted,ContractError
from semantic_runtime.legal_agent.navigation_input import expand_cards
from test_output_contract_recovery import Journal


def fixture(n=41):
 data={'presentation_id':'P1','request':'원문 조건 확인','source_stage':'source-law-navigation-1-read-choice',
       'sources':[{'id':'E1','text':'  원문\n조건·예외는 그대로  ','source_id':'server-only','document_id':'d','document_name':'모의규정','spans':[{'server':'offsets'}]}],
       'read_candidates':[{'target':'T'+str(i),'document_id':'d','document_name':'모의규정','coordinate':f'제{i+1}조','preview':f'원문 미리보기 {i}'} for i in range(n)],
       'tool_options':[{'choice':'LOCATE','target':'L1','label':'모의규정에서 위치 찾기','scope':{'document_id':'d'}}],
       'read_judgments':{'judgments':[{'id':'J1','finding':'검토 의견','reason':'원문 조건','missing':['미확인 사항']}],'needs':[{'id':'N1','status':'OPEN'}]}}
 schema={'type':'object','anyOf':[{'type':'object','properties':{'choice':{'const':'READ'},'selections':{'type':'array','minItems':1,'items':{'type':'object','properties':{'target':{'enum':[r['target'] for r in data['read_candidates']]}},'required':['target'],'additionalProperties':False}}},'required':['choice','selections'],'additionalProperties':False},{'type':'object','properties':{'choice':{'const':'FINISH'}},'required':['choice'],'additionalProperties':False}]}
 return data,schema

@pytest.mark.parametrize('n',[0,1,19,20,21,39,40,41,100])
def test_pages_partition_and_bind_schema(n):
 data,schema=fixture(n);original=deepcopy((data,schema));seen=[]
 for i in range(max(1,(n+19)//20)):
  view,wire=pages.page_view(data,schema,i,20)
  visible=[r['target'] for r in view['read_candidates']];seen+=visible
  allowed=wire['anyOf'][0]['properties']['selections']['items']['properties']['target']['enum']
  assert allowed==visible and len(visible)<=20
  for target in visible:validate({'choice':'READ','selections':[{'target':target}]},wire)
  for target in set(r['target'] for r in data['read_candidates'])-set(visible):
   with pytest.raises(ValidationError):validate({'choice':'READ','selections':[{'target':target}]},wire)
  for choice in (pages.NEXT,pages.PREVIOUS):
   if choice in view['read_candidate_page']['actions']:validate({'choice':choice},wire)
   else:
    with pytest.raises(ValidationError):validate({'choice':choice},wire)
 assert seen==[r['target'] for r in data['read_candidates']] and original==(data,schema)
 with pytest.raises(ContractError):pages.page_view(data,schema,-1,20)


def test_projection_no_sql_and_preserves_decision_material(monkeypatch):
 data,schema=fixture();view,wire=pages.page_view(data,schema,0,20);before=deepcopy(view)
 def forbidden(*args,**kwargs):raise AssertionError('renderer must not open database')
 monkeypatch.setattr(sqlite3,'connect',forbidden)
 got=expand_cards(minimal.project(view,wire))
 assert got['sources'][0]['text']==data['sources'][0]['text']
 assert got['read_judgments']==data['read_judgments']
 assert got['sources'][0]['document']=='D1' and got['documents']==[{'id':'D1','name':'모의규정'}]
 assert 'source_id' not in got['sources'][0] and 'spans' not in got['sources'][0]
 assert got['tool_options']['LOCATE'][0]['target']=='L1' and len(got['read_candidates'])==20
 assert view==before

@pytest.mark.parametrize('mode',['normal','back','repair','crash_before_save','crash_after_save','budget','time','stale'])
def test_durable_pages_existing_owner_no_menu_rebuild(tmp_path,monkeypatch,mode):
 data,schema=fixture();repo=Journal(tmp_path/'journal.sqlite');sql=[];repo.db.set_trace_callback(sql.append)
 reserved={'model_limit':40,'model_reserved':0,'finalization_reserve':2};repo.budget=lambda:reserved
 state={'binding':'binding'};persisted={};calls=[];expands=[];saves=[]
 inv=S(p=state,s=S(repo=repo,profile={}),policy={'minimal_input':True,'read_candidate_page_size':20},left=lambda:100)
 monkeypatch.setattr(rr,'gap_review_capacity',lambda inv:None)
 crashed=False
 def save():
  nonlocal crashed,persisted
  page=inv.p['read_candidate_pager']['page'];saves.append(page)
  if mode=='crash_before_save' and page==1 and not crashed:crashed=True;raise RuntimeError('synthetic checkpoint crash')
  persisted=deepcopy(inv.p)
  if mode=='crash_after_save' and page==1 and not crashed:crashed=True;raise RuntimeError('synthetic checkpoint crash')
 inv.save=save
 def invoke(view,attempt,wire,suffix):
  calls.append((view['read_candidate_page']['page'],attempt));reserved['model_reserved']+=1
  if mode=='stale':return {'choice':'READ','selections':[{'target':'wrong-principal-target'}]}
  if mode=='repair' and len(calls)==1:return {'choice':'READ','selections':[{'target':'T40'}]}
  if mode=='back':
   seq=[pages.NEXT,pages.PREVIOUS,pages.NEXT,'FINISH'];choice=seq[len(calls)-1]
  else:choice=pages.NEXT if view['read_candidate_page']['page']==1 else 'FINISH'
  return {'choice':choice}
 def expand(value):expands.append(value);validate(value,schema)
 def run():return pages.choose(inv,data,schema,invoke,expand,key='menu-key')
 if mode in ('budget','time'):
  if mode=='budget':reserved['model_reserved']=38
  else:inv.left=lambda:1
  with pytest.raises(BudgetExhausted):run()
  assert not calls
 elif mode=='stale':
  from semantic_runtime.legal_agent.output_contract import OutputContractError
  with pytest.raises(ValidationError):run()
  assert len(calls)==2 and not expands
 else:
  if mode.startswith('crash'):
   with pytest.raises(RuntimeError):run()
   inv.p=deepcopy(persisted)
  value=run();assert value=={'choice':'FINISH'}
  before=len(calls);assert run()==value and len(calls)==before
  assert len(calls)==(4 if mode=='back' else 3 if mode=='repair' else 2)
  assert all(v['choice']=='FINISH' for v in expands)
  assert inv.p['read_candidate_pager']['page']==1
 assert not any('source_' in q or 'fulltext' in q or 'reference_' in q for q in sql)
