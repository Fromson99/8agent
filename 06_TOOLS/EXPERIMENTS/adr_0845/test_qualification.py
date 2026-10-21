"""Prospective finite software states. Model proposals are synthetic, not legal gold."""
import json,sqlite3,importlib.util
from pathlib import Path
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from test_legal_agent_double_harness import wire
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0845-source-terminal-qualification'
spec=importlib.util.spec_from_file_location('development_sources',Path(__file__).parents[1]/'adr_0844/test_sources.py');dev=importlib.util.module_from_spec(spec);spec.loader.exec_module(dev)
tree=dev.tree;linked_tree=dev.linked_tree
CASES=json.loads((A/'artifacts/design/cases.json').read_text())

@pytest.mark.parametrize('case',CASES,ids=[x['id'] for x in CASES])
def test_opinions_are_preserved_and_source_work_ends(tmp_path,tree,case):
 class Opinions(dev.Sources):
  def send_once(self,*,body,ticket):
   raw=super().send_once(body=body,ticket=ticket)
   view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
   if stage not in ('workflow-items','workflow-compare'):return raw
   value=json.loads(raw['body_json']['choices'][0]['message']['content'])
   if stage=='workflow-items':
    for item in value['items']:
     for side in ('internal','external'):
      item[side]['status']=case['item_status'];item[side]['missing']='예외 추가 확인' if case['missing'] else ''
   else:
    for row in value['rows']:
     row['verdict']=case['verdict'];row['item']='모델이 쓴 중복 제목'
     row['unresolved']=['범위 추가 확인'] if case['missing'] else []
   return wire(value)
 app,_=dev.app_for(tmp_path,tree);t=Opinions();app.state.pipeline.term_agent.transport=t
 with TestClient(app) as client:
  response=client.post('/v1/rag/ask',json=dev.BODY);assert response.status_code==200,response.text
  value=response.json();assert value['report']['rows'] and value['report']['rows'][0]['verdict']==case['verdict'],value
  assert '| 승인 기준 |' in value['answer']['text'] and '모델이 쓴 중복 제목' not in value['answer']['text']
  assert all(i[s]['status']==case['item_status'] for i in value['comparison_items']['items'] for s in ('internal','external'))
  calls=len(t.views);again=client.post('/v1/rag/ask',json=dev.BODY);assert again.status_code==200 and again.json()['answer']==value['answer'] and len(t.views)==calls
  assert not any(s.startswith(('memory-assess','memory-compose')) for s,_ in t.views)
  root=app.state.workflow_runtime.root/value['run_id']
  for p in root.glob('children/*/legal-agent/runs/*/*/journal.sqlite'):
   with sqlite3.connect(p) as db:
    assert db.execute('SELECT status,phase FROM run').fetchone()==('COMPLETED','END')
    assert db.execute('SELECT count(*) FROM source_handoff_export').fetchone()[0]==1
  for p in root.glob('children/*/case-memory/cases-v3.sqlite'):
   with sqlite3.connect(p) as db:
    assert db.execute('SELECT count(*) FROM route').fetchone()[0]==0
    assert db.execute('SELECT count(*) FROM knowledge').fetchone()[0]==0

def test_zero_read_source_handoff_is_valid_api_result(tmp_path,tree):
 class Empty(dev.Sources):
  def send_once(self,*,body,ticket):
   view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
   if stage.startswith('source-law-sources-'):
    self.views.append((stage,deepcopy(view)));return wire({'target_id':None,'query':None,'reason':'현재 조사 원문 미확보'})
   raw=super().send_once(body=body,ticket=ticket)
   if stage=='workflow-intake':
    value=json.loads(raw['body_json']['choices'][0]['message']['content']);value['internal_queries']=value['external_queries']=['미등록용어ZZQ98451'];return wire(value)
   return raw
 app,_=dev.app_for(tmp_path,tree);app.state.pipeline.term_agent.transport=Empty()
 with TestClient(app) as c:
  result=c.post('/v1/rag/ask',json={**dev.prior.BODY,'question':'대사: 미등록용어ZZQ98451'});assert result.status_code==200,result.text
  value=result.json()
  for child in value['rag_results'].values():
   assert child['bundle']['export_mode']=='SOURCE_HANDOFF' and child['evidence_ids']==[] and child['status']=='partial',child
   assert child['answer'] is None and child['investigation_return']['absence_proven'] is False

def test_reference_title_coordinate_fallback_preserves_original(tmp_path,linked_tree,monkeypatch):
 from semantic_runtime import term_references
 original=term_references.reference_targets
 # Simulate the existing resolver returning no target; witness and document catalogue remain real.
 monkeypatch.setattr(term_references,'reference_targets',lambda r:[] if r.get('document_name_hint')=='연결내규' else original(r))
 app,_=dev.prior._base.application(tmp_path,linked_tree,principal={'user_id':'u','team_id':'risk_team','document_ids':['inside','linked','outside']});app.state.pipeline.term_agent.transport=dev.Sources()
 with TestClient(app) as c:
  result=c.post('/v1/rag/ask',json=dev.BODY);assert result.status_code==200,result.text
  refs=result.json()['rag_results']['internal']['investigation_return']['acquisition']['references']
  linked=next(r for r in refs.values() if r['document_name_hint']=='연결내규')
  assert linked['resolution_path']=='WITNESSED_TITLE_COORDINATE' and linked['status']=='COMPLETE' and linked['candidate_document_ids']==['linked']

def test_source_terminal_schema_rejects_legal_answer_promotion():
 from jsonschema import validate,ValidationError
 from semantic_runtime.legal_agent.source_handoff import schema
 value={'status':'sources_returned','terminal':'SOURCE_HANDOFF','next_action':'DONE','needs_fulltext':False,'final_ids':[],'selected_originals':[],
   'selected_evidence':[],'investigation_state':{},'source_return':{'schema_version':'source-investigation-v1','read_evidence_ids':[],
    'reason':'미확보','stop_reason':None,'acquisition':{},'research_tasks':{},'semantic_quality_certified':False,'absence_proven':False}}
 validate(value,schema())
 for change in ({'answer':'legal answer'},{'status':'READY'},{'final_ids':['invented']}):
  with pytest.raises(ValidationError):validate({**value,**change},schema())
