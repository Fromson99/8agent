from copy import deepcopy
from pathlib import Path
import importlib.util,json,sqlite3
import pytest
from fastapi.testclient import TestClient
from test_legal_agent_double_harness import wire
from semantic_runtime.legal_agent.errors import ContractError
spec=importlib.util.spec_from_file_location('source_prior',Path(__file__).parents[1]/'adr_0838/test_workflow.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
tree=prior.tree
BODY={**prior.BODY,'question':'대사: 모의내규와 모의승인규정의 승인 기준을 비교해 주세요.'}
class Sources(prior.TaskTransport):
 def send_once(self,*,body,ticket):
  view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
  from semantic_runtime.legal_agent.workflow_execution import has_reentry
  if self.task_mode=='failed_followup' and has_reentry():
   from semantic_runtime.legal_agent.errors import TransportError
   raise TransportError('synthetic failed followup',unknown=True)
  if stage.startswith('source-law-sources-'):
   self.views.append((stage,deepcopy(view)))
   # Test double makes only the technical choice; no model quality claim.
   actions=view.get('actions',[])
   target=None if view.get('preferred_originals') or view.get('sources') else next((a['id'] for a in actions if a['action']=='READ_ARTICLES'),None)
   return wire({'target_id':target,'query':None,'reason':'확보한 원문 반환' if target is None else '원문 확인'})
  return super().send_once(body=body,ticket=ticket)
def app_for(tmp,tree,mode='normal'):
 app,_=prior.task_app(tmp,tree);t=Sources(mode);app.state.pipeline.term_agent.transport=t
 return app,t

def test_api_sources_terminal_no_child_assess_and_duplicate(tmp_path,tree):
 app,t=app_for(tmp_path,tree)
 with TestClient(app) as c:
  r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
  value=r.json();assert value['report']['rows'],value
  for s in ('internal','external'):
   x=value['rag_results'][s];assert x['bundle']['export_mode']=='SOURCE_HANDOFF',x
   assert x['evidence_ids'] and x['answer'] is None and x['bundle']['claims']==[]
   assert x['investigation_return']['acquisition']['documents'][{'internal':'inside','external':'outside'}[s]]['read_complete']
  assert not any(stage.startswith(('memory-assess','memory-compose')) for stage,_ in t.views)
  count=len(t.views);again=c.post('/v1/rag/ask',json=BODY);assert again.status_code==200,again.text
  assert value['answer']==again.json()['answer'] and len(t.views)==count
  saved=c.get('/v1/workflows/runs/'+value['run_id'],params={'session_id':'s'});assert saved.status_code==200,saved.text
  assert saved.json()['answer']==value['answer']
  assert sum(line.startswith('|---') for line in value['answer']['text'].splitlines())==1
 for p in (app.state.workflow_runtime.root/value['run_id']).glob('children/*/case-memory/cases-v3.sqlite'):
  with sqlite3.connect(p) as db:
   assert db.execute('SELECT DISTINCT status FROM goal').fetchall()==[('SOURCES_RETURNED',)]
   assert db.execute('SELECT count(*) FROM route').fetchone()[0]==0
   assert db.execute('SELECT count(*) FROM knowledge').fetchone()[0]==0

@pytest.mark.parametrize('mode',['followup','failed_followup'])
def test_followup_keeps_sources(tmp_path,tree,mode):
 app,t=app_for(tmp_path,tree,mode)
 with TestClient(app) as c:
  r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
  v=r.json();assert v['rag_results']['internal']['evidence_ids'],v
  if mode=='followup':assert all(x['status']=='COMPLETE' for x in v['research_attempts'].values()),v
  else:assert v['latest_rag_attempts']['internal']['status']=='failed',v
  assert all(i['internal']['citations'] for i in v['comparison_items']['items']),v

def test_after_terminal_commit_resumes_without_model(tmp_path,tree,monkeypatch):
 from semantic_runtime import workflow_rag
 app,t=app_for(tmp_path,tree);original=workflow_rag.execute;calls=[]
 def stop(*a,**kw):
  out=original(*a,**kw);calls.append(len(t.views))
  if len(calls)==1:raise KeyboardInterrupt('after source commit')
  return out
 monkeypatch.setattr(workflow_rag,'execute',stop)
 with pytest.raises(KeyboardInterrupt):app.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},prior._base.PRINCIPAL)
 journal=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
 with sqlite3.connect(journal) as db:
  revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0];deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
 with TestClient(app) as c:
  out=c.post('/v1/workflows/resume',json={'run_id':journal.parent.name,'session_id':'s','expected_revision':revision})
  assert out.status_code==200,out.text
  assert calls[0]==calls[1]
 with sqlite3.connect(journal) as db:assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline

def test_source_mode_is_trusted_context_only():
 from semantic_runtime.legal_agent.source_handoff import enabled
 from semantic_runtime.legal_agent.workflow_execution import child_execution
 assert not enabled()
 with child_execution(None,None,'x',[],task={'return_mode':'sources'}):assert enabled()
 assert not enabled()

@pytest.mark.parametrize('mutation',['artifact','selection','task'])
def test_saved_source_return_tamper_rejected(tmp_path,tree,mutation):
 app,t=app_for(tmp_path,tree)
 with TestClient(app,raise_server_exceptions=False) as c:
  r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
  value=r.json();count=len(t.views);path=next((app.state.workflow_runtime.root/value['run_id']).glob('children/internal/legal-agent/runs/*/*/journal.sqlite'))
  with sqlite3.connect(path) as db:
   if mutation=='artifact':db.execute("UPDATE source_handoff_export SET payload_json='{}'")
   else:
    table='event' if mutation=='task' else 'entity_version'
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",(table,)).fetchall():db.execute('DROP TRIGGER "'+name+'"')
    if mutation=='task':db.execute("UPDATE event SET payload_json='{}' WHERE kind='WORKFLOW_PARENT_TASK_BOUND'")
    else:
     ref=json.loads(db.execute('SELECT payload_json FROM source_handoff_export').fetchone()[0])['selection_ref']
     assert db.execute("UPDATE entity_version SET payload_json='{}' WHERE kind=? AND entity_id=? AND version=?",(ref['kind'],ref['entity_id'],ref['version'])).rowcount==1
  again=c.post('/v1/rag/ask',json=BODY);assert again.status_code in (409,500),again.text
  assert len(t.views)==count

def test_stop_between_select_commit_and_terminal_is_recoverable(tmp_path,tree,monkeypatch):
 from semantic_runtime.legal_agent import source_handoff
 app,t=app_for(tmp_path,tree);old=source_handoff.commit;hits=[]
 def stop(*a,**kw):
  hits.append(len(t.views))
  if len(hits)==1:raise KeyboardInterrupt('SELECT durable, terminal not yet committed')
  return old(*a,**kw)
 monkeypatch.setattr(source_handoff,'commit',stop)
 with pytest.raises(KeyboardInterrupt):app.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},prior._base.PRINCIPAL)
 journal=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
 with sqlite3.connect(journal) as db:revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
 with TestClient(app) as c:
  response=c.post('/v1/workflows/resume',json={'run_id':journal.parent.name,'session_id':'s','expected_revision':revision})
  assert response.status_code==200,response.text
  assert hits[1]==hits[0]
  assert response.json()['rag_results']['internal']['evidence_ids']

def test_no_named_doc_still_uses_native_search(tmp_path,tree):
 app,t=app_for(tmp_path,tree)
 with TestClient(app) as c:
  out=c.post('/v1/rag/ask',json=prior.BODY);assert out.status_code==200,out.text
  for result in out.json()['rag_results'].values():
   assert result['bundle']['export_mode']=='SOURCE_HANDOFF' and result['evidence_ids'],result
  assert not any(s.startswith('memory-assess') for s,_ in t.views)

@pytest.fixture
def linked_tree(tmp_path,term_glossary):
 base=prior._base;raw=base.source(tmp_path/'linked.sqlite',[
  ('inside','모의내규',['제1조(승인) 「연결내규」 제1조와 「미확보내규」 제9조를 따른다.','자료를 제출한다.']),
  ('linked','연결내규',['제1조(보고) 승인 후 보고한다.']),
  ('outside','모의승인규정',['제1조(승인) 승인 후 보고한다.'])])
 with sqlite3.connect(raw) as db:
  for did in ('inside','linked','outside'):
   db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({'document_category':'external' if did=='outside' else 'internal','document_metadata':{'team':'risk_team'}}),did))
 base.build_generation(raw,term_glossary,tmp_path/'linked-built',serving=True)
 gen=tmp_path/'linked-built/generation';index=tmp_path/'linked-index';base.build(gen,gen/'navigation',index,workers=1)
 return gen,base.UnitFulltextIndex(index,json.loads((gen/'navigation/manifest.json').read_text()))

def test_existing_reference_first_and_missing_is_not_absence(tmp_path,linked_tree):
 app,_=prior._base.application(tmp_path,linked_tree,principal={'user_id':'u','team_id':'risk_team','document_ids':['inside','linked','outside']})
 app.state.pipeline.term_agent.transport=Sources()
 with TestClient(app) as c:
  r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
  child=r.json()['rag_results']['internal'];refs=list(child['investigation_return']['acquisition']['references'].values())
  linked=[r for r in refs if r['document_name_hint']=='연결내규'];assert linked,refs
  assert linked[0]['resolution_path']=='EXISTING_REFERENCE' and linked[0]['status']=='COMPLETE'
  missing=[r for r in refs if r['document_name_hint']=='미확보내규'];assert missing,refs
  assert missing[0]['status']=='UNRESOLVED' and missing[0]['absence_proven'] is False

def test_large_named_doc_outlines_without_claiming_full_read(tmp_path,tree):
 from semantic_runtime.legal_agent import source_investigation
 # Exercise the actual acquisition state and SourceSession using a narrowly bounded input budget.
 app,t=app_for(tmp_path,tree);profile=app.state.pipeline.term_agent.profile
 original=source_investigation.acquire_preferred
 def small(inv):
  saved=inv.s.profile['max_context_chars'];inv.s.profile['max_context_chars']=8001
  try:return original(inv)
  finally:inv.s.profile['max_context_chars']=saved
 from unittest.mock import patch
 with patch.object(source_investigation,'acquire_preferred',small),TestClient(app) as c:
  r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
  for child in r.json()['rag_results'].values():
   for doc in child['investigation_return']['acquisition']['documents'].values():
    assert doc['status']=='OUTLINE_ONLY' and doc['read_complete'] is False and doc['structure']
