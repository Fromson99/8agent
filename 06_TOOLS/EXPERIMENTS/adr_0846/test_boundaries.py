"""Controlled tool-result boundaries; no legal relevance or model quality metric."""
from pathlib import Path
import importlib.util,json,sqlite3
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from test_legal_agent_double_harness import wire
spec=importlib.util.spec_from_file_location('boundary_dev',Path(__file__).parents[1]/'adr_0844/test_sources.py');dev=importlib.util.module_from_spec(spec);spec.loader.exec_module(dev)
tree=dev.tree
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0846-source-return-boundary';CASES=json.loads((A/'artifacts/design/cases.json').read_text())
@pytest.mark.parametrize('case',CASES,ids=[c['id'] for c in CASES])
def test_empty_partial_bounded_and_interrupted_sources(tmp_path,tree,case,monkeypatch):
 from semantic_runtime.legal_agent.workflow_execution import task_context
 from semantic_runtime.legal_agent.source_recall import SourceRecall
 from semantic_runtime.legal_agent import law_candidates as lc,definition_entry,law_navigation,source_handoff
 from semantic_runtime import comparison_research_bridge as bridge
 from semantic_runtime.contracts import digest
 from semantic_runtime.legal_agent.errors import BudgetExhausted
 def empty():
  task=task_context();return bool(task and not case[task['source_category']])
 discover=SourceRecall.discover;preferred=bridge.preferred_documents;acquire=definition_entry.acquire_initial;choose=law_navigation.Investigation.request_decision
 def recall(self):
  if not empty():return discover(self)
  idx,_=lc.index(self.s)
  catalogue={'contract':lc.CONTRACT,'terms':[],'queries':[],'route_queries':[],
   'query_origin':'synthetic-empty-tool-result','law_page':{'items':[],'total':0,'next_cursor':None},
   'query_fingerprint':digest({'fixture':case['id'],'side':task_context()['source_category']}),
   'index_sha256':idx.manifest['index_sha256'],'search_policy':'best-own-block-match-v1'}
  return [],{'discovery_mode':'fulltext','law_navigation':catalogue,'unit_hits':[],
   'unit_index_sha256':idx.manifest['index_sha256'],'selected_for_read':[],'discovered':[],
   'routes':{},'queries':[],'parent_selections_preserved':True}
 monkeypatch.setattr(SourceRecall,'discover',recall)
 monkeypatch.setattr(bridge,'preferred_documents',lambda p,q,s:preferred(p,q,s) if case[s] else [])
 monkeypatch.setattr(definition_entry,'acquire_initial',lambda inv:None if empty() else acquire(inv))
 def bounded(inv,*args):
  if case['bounded']:raise BudgetExhausted('synthetic shared budget boundary; originals remain')
  return choose(inv,*args)
 monkeypatch.setattr(law_navigation.Investigation,'request_decision',bounded)
 class Finish(dev.Sources):
  def send_once(self,*,body,ticket):
   view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
   if stage.startswith('source-law-sources-'):
    self.views.append((stage,deepcopy(view)));return wire({'target_id':None,'query':None,'reason':'현재 확보 범위를 부모에 반환'})
   return super().send_once(body=body,ticket=ticket)
 app,_=dev.app_for(tmp_path,tree);t=Finish();app.state.pipeline.term_agent.transport=t
 if case['interrupted']:
  publish=source_handoff.publish;calls=[]
  def stop(*a,**kw):
   result=publish(*a,**kw);calls.append(len(t.views))
   if len(calls)==1:raise KeyboardInterrupt('after durable source terminal')
   return result
  monkeypatch.setattr(source_handoff,'publish',stop)
  with pytest.raises(KeyboardInterrupt):app.state.workflow_runtime.execute({**dev.BODY,'workflow_id':'risk_team_compare_workflow'},dev.prior._base.PRINCIPAL)
  p=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
  with sqlite3.connect(p) as db:
   revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0];deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0];budget=db.execute('SELECT model_reserved,tool_used FROM budget').fetchone()
  with TestClient(app) as client:
   response=client.post('/v1/workflows/resume',json={'run_id':p.parent.name,'session_id':'s','expected_revision':revision})
  assert calls[0]==calls[1]
  with sqlite3.connect(p) as db:
   assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline
   later=db.execute('SELECT model_reserved,tool_used FROM budget').fetchone();assert all(b>=a for a,b in zip(budget,later))
 else:
  with TestClient(app) as client:response=client.post('/v1/rag/ask',json=dev.BODY)
 assert response.status_code==200,response.text
 value=response.json();root=app.state.workflow_runtime.root/value['run_id']
 for side in ('internal','external'):
  child=value['rag_results'][side];assert child['bundle']['export_mode']=='SOURCE_HANDOFF' and child['answer'] is None
  assert bool(child['evidence_ids'])==case[side],child
  if not case[side] or case['bounded']:assert child['status']=='partial'
  assert child['investigation_return']['absence_proven'] is False
  for p in root.glob('children/'+side+'/legal-agent/runs/*/*/journal.sqlite'):
   with sqlite3.connect(p) as db:assert db.execute('SELECT status,phase FROM run').fetchone()==('COMPLETED','END')
 assert not any(s.startswith(('memory-assess','memory-compose')) for s,_ in t.views)
 assert value['comparison_items']['items']
 count=len(t.views)
 with TestClient(app) as client:
  saved=client.get('/v1/workflows/runs/'+value['run_id'],params={'session_id':'s'});assert saved.status_code==200 and saved.json()['answer']==value['answer']
  duplicate=client.post('/v1/rag/ask',json=dev.BODY);assert duplicate.status_code==200 and duplicate.json()['answer']==value['answer']
 assert len(t.views)==count
