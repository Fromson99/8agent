from copy import deepcopy
from types import SimpleNamespace
import pytest
from workflow import presentation
from workflow.risk_team_compare_workflow import basis
from workflow.contracts import WorkflowError
from semantic_runtime.legal_agent.law_navigation import Investigation


def source(i,side='external',doc='law',root='article',issues=()):
 return dict(evidence_id=i,side=side,document_id=doc,source_id=root,parent_issue_refs=list(issues),text='original '+i,spans=[{'text':'original '+i}],source_complete=False)


def test_acquired_siblings_survive_item_selection_without_foreign_context(monkeypatch):
 originals=[source('head'),source('items'),source('other-issue',issues=['q2']),source('other-side',side='internal'),source('other-doc',doc='foreign'),source('other-root',root='else'),source('inside',side='internal',doc='reg',root='r')]
 by={e['evidence_id']:e for e in originals}
 def evidence(ctx,state,ids=None):
  if ids is not None and set(ids)-set(by):raise WorkflowError('WORKFLOW_STALE_EVIDENCE','stale',409)
  return deepcopy(originals if ids is None else [by[i] for i in ids])
 monkeypatch.setattr(presentation,'evidence',evidence)
 ctx=SimpleNamespace(request={'as_of':None},repo=SimpleNamespace(save=lambda s:None))
 assert presentation.source_context(ctx,{},['head'],'q1')=={'head','items'}
 with pytest.raises(WorkflowError):presentation.source_context(ctx,{},['stale'],'q1')
 def obs(i):return dict(text='review',citations=[{'evidence':i,'quote':'original '+i}],dependencies=[],missing='')
 state={'scope':{'issues':[{'id':'q1'}]},'task_board':{'rows':{'row':{'issue_id':'q1','field':'obligation','current':{'internal':obs('inside'),'external':obs('head')}}}}}
 monkeypatch.setattr(basis,'child_gap_requirements',lambda state:{'audit':[]})
 # Checks below exercise actual original citation validation and side checks.
 value=basis.from_items(ctx,state)
 assert value['pairs'][0]['external']==['head','items']
 assert value['pairs'][0]['internal']==['inside']
 assert value['pairs'][0]['content_citations']==[{'evidence':'inside','quote':'original inside'},{'evidence':'head','quote':'original head'}]
 assert state['task_board']['rows']['row']['current']['external']['missing']==''


def test_navigation_counts_read_actions_separately_without_absence_claim():
 data={'actions':[{'action':'READ_ARTICLES'},{'action':'READ_PARENT'},{'action':'SEARCH_STRUCTURE'},{'action':'VIEW_SAVED_SOURCE'}], 'sources':[], 'saved_inventory':[{'status':'EXCLUDED'}]}
 before=deepcopy(data);value=Investigation.model_view(data)
 assert value['reading_progress']==dict(offered_read_actions=2,presented_original_pages=0,saved_original_ranges=1,candidate_is_original=False,unread_is_absent=False)
 assert data==before


def test_compare_focus_reaches_api_and_survives_replay(tmp_path,tree):
 from test_sources import app_for,BODY
 from fastapi.testclient import TestClient
 app,t=app_for(tmp_path,tree)
 with TestClient(app) as client:
  value=client.post('/v1/rag/ask',json=BODY);assert value.status_code==200,value.text
  views=[v for stage,v in t.views if stage=='workflow-compare']
  assert views
  for v in views:
   f=v['comparison_focus'];assert f['issue']['id']
   assert f['field_reviews'] and all(r['issue_id']==f['issue']['id'] for r in f['field_reviews'])
  n=len(t.views);again=client.post('/v1/rag/ask',json=BODY)
  assert again.json()['answer']==value.json()['answer'] and len(t.views)==n

from test_sources import tree
