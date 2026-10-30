"""Prospective behavior matrix; no live model or legal-quality score."""
from copy import deepcopy
import pytest
from conftest import term_glossary
from semantic_runtime.legal_agent import completion_contracts as cc

ISSUES=[{'id':'Q1','question':'신청 요건과 처리 기간'}]
STOPS=[None,*cc.STOP_WORDS,'SUPERVISOR_UNRESOLVED:TransportError','NEW_OPERATIONAL_STOP']
GENERIC='확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.'

def assessment(gaps=()):
 return {'completion_contract':cc.V8,'claims':[],'issue_assessments':[{'issue_id':'Q1','status':'COVERED' if not gaps else 'PARTIAL','reason':'합성 검토'}], 'gaps':deepcopy(list(gaps))}

@pytest.mark.parametrize('stop',STOPS)
def test_operational_history_does_not_invent_unread_scope(stop):
 a=assessment();before=deepcopy(a)
 cc.refresh_limitations(a,ISSUES,stop,notes=['ADOPTION_FALLBACK'])
 assert a['limitations']==a['limitation_items']==[] and a['stop_reason']==stop
 assert all(a[k]==v for k,v in before.items())
 assert cc.refresh_limitations(deepcopy(a),ISSUES,stop)==a

@pytest.mark.parametrize('kind',list(cc.GAP_WORDS))
@pytest.mark.parametrize('stop',[None,'SUPERVISOR_UNRESOLVED:TransportError'])
def test_material_gaps_and_specific_targets_survive(kind,stop):
 gap={'issue_id':'Q1','kind':kind,'material_id':None,'material':True,'missing_target':'접수 기준일','reason':'기준일 근거 부족'}
 a=assessment([gap]);cc.refresh_limitations(a,ISSUES,stop)
 assert a['gaps']==[gap] and a['issue_assessments'][0]['status']=='PARTIAL'
 assert len(a['limitations'])==1 and '접수 기준일' in a['limitations'][0]
 assert cc.GAP_WORDS[kind] in a['limitations'][0] and GENERIC not in a['limitations'][0]
 assert a['stop_reason']==stop

@pytest.mark.parametrize('status',list(cc.CLOSED_WORDS))
def test_closed_gap_explanation_is_preserved(status):
 g={'issue_id':'Q1','kind':'MISSING_SOURCE','material_id':None,'material':True,'missing_target':'위임 기준'}
 a=assessment([g]);cc.refresh_limitations(a,ISSUES,'NO_PROGRESS',closed={cc.gap_key(g):status})
 assert cc.CLOSED_WORDS[status] in a['limitations'][0]
 assert a['limitation_items'][0]['navigation_status']==status

@pytest.mark.parametrize('gaps',[[],[{'issue_id':'Q1','kind':'MISSING_SOURCE','material':True,'material_id':None,'missing_target':'별도 기준'}]])
def test_final_review_output_limit_warning_survives(gaps):
 a=assessment(gaps);cc.refresh_limitations(a,ISSUES,'ASSESSMENT_OUTPUT_LIMIT')
 assert len(a['limitations'])==1+len(gaps)
 assert any('답변 검토가 출력 한도에서 끝나 완료하지 못했습니다' in s for s in a['limitations'])

def test_nonmaterial_gap_is_not_promoted_by_stop_history():
 g={'issue_id':'Q1','kind':'MISSING_SOURCE','material':False,'material_id':None}
 a=assessment([g]);cc.refresh_limitations(a,ISSUES,'NO_PROGRESS')
 assert a['gaps']==[g] and not a['limitations']

@pytest.mark.parametrize('mode',['supported','limited_source','limited_fact'])
def test_native_api_preserves_stop_history_and_renders_only_real_gaps(tmp_path,term_glossary,monkeypatch,mode):
 from native_fixture import run_api
 old=cc.refresh_limitations
 def with_history(value,issues,stop_reason=None,**kw):
  return old(value,issues,'SUPERVISOR_UNRESOLVED:TransportError',**kw)
 monkeypatch.setattr(cc,'refresh_limitations',with_history)
 response,calls,reviews=run_api(tmp_path,term_glossary,mode,monkeypatch)
 import json
 import importlib.util
 if importlib.util.find_spec("semantic_runtime.legal_agent.journal_storage") is None:
  from sqlite3 import connect
 else:
  from semantic_runtime.legal_agent.journal_storage import connect
 ref=response['assembly']['term_agent']['case']['judgment_refs']['COMPOSE']
 journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+response['run_id']+'/journal.sqlite'))
 with connect(journal) as db:
  a=json.loads(db.execute('select payload_json from entity_version where kind=? and entity_id=? and version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone()[0])
 assert a['text']==response['answer']['text']
 assert a['stop_reason']=='SUPERVISOR_UNRESOLVED:TransportError'
 assert GENERIC not in a['text']
 assert bool(a['limitations']) is (mode!='supported')
 assert ('확인 범위' in a['text']) is (mode!='supported')
 assert len(calls)==8 and len(reviews)==1
