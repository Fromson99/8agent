"""Prospective synthetic clauses: no CM wording or answer enters product code."""
from copy import deepcopy
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import narrative_answer as n, completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.answer_stream import capture
from test_source_span_norm import accepted, proposal, SpanTransport
from test_main50_request_repair import tree
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_unified_legal_agent import ok

PARTS=['임차인(단기 전대사업자 제외)','국내에서 계약 갱신 후 지급한 보증금에 한정',
 '계약기간이 18개월 이상인 경우','담보권이 설정되지 않은 경우','납부일로부터 7일 이내',
 '최초 납부한 보증금의 월 4%를 초과하여 공제하여서는 아니 된다.',
 '천재지변으로 인한 연체에는 공제하지 않는다.']

def sample(mode='ANY', pure=False):
 p=proposal(PARTS[5],'PROHIBITION');c=p['claims'][0]
 if pure:c.update(rule=None,explanation='승인 통지는 전자문서로 전달할 수 있다. 단, 수신자가 종이문서를 요청하면 우편으로 전달한다.')
 else:
  r=c['rule'];r.update(subject=PARTS[0],scope=PARTS[1],action=PARTS[4],
   condition_tree={'mode':mode,'children':[{'mode':'LEAF','text':s,'evidence_refs':['S1']} for s in PARTS[2:4]]},
   exceptions=[{'target':'보증금 공제','text':PARTS[6],'evidence_refs':['S1']}])
 return accepted(p,[{'id':'S1','source_id':'s','text':' '.join(PARTS) if not pure else c['explanation']}])

@pytest.mark.parametrize('layout',['paragraphs','bullets','table'])
@pytest.mark.parametrize('mode',['ALL','ANY','UNKNOWN'])
def test_scope_conditions_basis_deadline_and_exception_all_survive(layout,mode):
 a=sample(mode);before=deepcopy(a);out=cc.compose(a,n.preserved_plan(a,layout))
 cc.verify_composition(a,out)
 assert all(s in out['text'] for s in PARTS)
 assert a==before and out['claims']==a['claims']
 assert out['composition_plan']['layout']==layout
 assert out['text'].count(PARTS[5])==1
 assert out['composition_plan']['presentation']==n.PRESERVED_VERSION

@pytest.mark.parametrize('layout',['paragraphs','bullets','table'])
def test_authored_prose_and_limitations_survive(layout):
 a=sample(pure=True);a['limitations']=['차임 변경의 사전 통지 기간은 확인하지 못했습니다.']
 a['stop_reason']='SUPERVISOR_UNRESOLVED:TransportError'
 out=cc.compose(a,n.preserved_plan(a,layout))
 assert a['claims'][0]['text'] in out['text'] and a['limitations'][0] in out['text']
 assert out['stop_reason']==a['stop_reason']
 cc.verify_composition(a,out)

@pytest.mark.parametrize('mutation',['text','conditions','norms','exception','source'])
def test_mutated_accepted_content_is_rejected_even_with_fresh_plan_hash(mutation):
 a=sample();c=a['claims'][0]
 if mutation=='text':c['text']=c['text'].replace(PARTS[2],'')
 elif mutation=='source':c['span_receipts'][0]['text']='다른 원문'
 else:
  r=c['answer_content']['rule']
  if mutation=='conditions':r['condition_tree']=None
  elif mutation=='norms':r['norms'][0]['text']='월 4% 공제'
  else:r['exceptions']=[]
 with pytest.raises(ContractError):n.preserved_plan(a)

@pytest.mark.parametrize('mutation',['hash','extra_text','extra_paragraphs','missing_id','duplicate_id','unknown_id'])
def test_invalid_plan_cannot_override_or_drop_content(mutation):
 a=sample();p=n.preserved_plan(a)
 if mutation=='hash':p['accepted_assessment_hash']='stale'
 elif mutation=='extra_text':p['text']='축약 답변'
 elif mutation=='extra_paragraphs':p['paragraphs']=[{'claim_ids':['C1'],'text':'축약 답변'}]
 elif mutation=='missing_id':p['claim_order']=[]
 elif mutation=='duplicate_id':p['claim_order']=['C1','C1']
 else:p['claim_order']=['private']
 with pytest.raises(ContractError):cc.compose(a,p)

def test_rendered_answer_tamper_and_stale_assessment_fail():
 a=sample();p=n.preserved_plan(a);out=cc.compose(a,p)
 bad=deepcopy(out);bad['text']=bad['text'].replace(PARTS[6],'')
 with pytest.raises(ContractError):cc.verify_composition(a,bad)
 a['stop_reason']='different'
 with pytest.raises(ContractError):cc.compose(a,p)

def test_shared_issues_show_all_content_once_and_link_second_issue():
 a=sample();a['claims'][0]['issue_refs']=['Q1','Q2']
 # Keep the canonical compiled content in sync; the server validates both.
 a['claims'][0]['answer_content']['issue_refs']=['Q1','Q2']
 issues=[{'id':'Q1','question':'보증금 공제'},{'id':'Q2','question':'적용 예외'}]
 out=cc.compose(a,n.preserved_plan(a,issues=issues))
 assert out['text'].count(PARTS[6])==1 and '공통 판단' in out['text']
 assert '보증금 공제' in out['text'] and '적용 예외' in out['text']

def test_legacy_saved_narrative_retains_exact_rendering():
 a=sample();value={'paragraphs':[{'claim_ids':['C1'],'text':'과거 저장된 답변'}]}
 p=n.plan(a,value);out=cc.compose(a,p)
 cc.verify_composition(a,out)
 assert out['text']=='과거 저장된 답변' and p['presentation']==n.VERSION

@pytest.mark.parametrize('layout',['paragraphs','table'])
@pytest.mark.parametrize('mode',['normal','read_repair','reentry','corrupt'])
def test_native_api_no_rewrite_no_draft_leak_duplicate_and_failure(tmp_path,tree,monkeypatch,layout,mode):
 from semantic_runtime.app import create_app
 from fastapi.testclient import TestClient
 gen,idx=tree;tokens=[];t=SpanTransport(mode=='reentry',mode=='read_repair')
 t.command['format']='table' if layout=='table' else 'prose'
 reached=[]
 profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,'final_review_enabled':False,
  'answer_presentation':n.PRESERVED_VERSION,
  'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
   'completion_policy_version':cc.V8,'compact_input':True}}
 # Any unexpected final writing request is a hard test failure, not a mock success.
 original=t.send_once
 def send(*,body,ticket):
  v=json.loads(body['messages'][1]['content'])['view']
  assert not v.get('source_stage','').startswith('memory-compose')
  return original(body=body,ticket=ticket)
 t.send_once=send
 if mode=='corrupt':
  old=n.preserved_plan
  def corrupt(a,*args,**kw):
   reached.append(True);p=old(a,*args,**kw);p['accepted_assessment_hash']='stale';return p
  monkeypatch.setattr(n,'preserved_plan',corrupt)
 app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
  legal_agent_profile=profile,legal_agent_transport=t,
  memory_identity=lambda _:{'user_id':'u','team_id':'test_team','document_ids':['d']})
 app.state.pipeline.term_agent.unit_fulltext=idx
 with TestClient(app) as api:
  body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'preserved','request_id':'r1'}
  with capture('r1',tokens.append):response=api.post('/v1/rag/ask',json=body)
  assert not tokens # No model-generated prefix can leak before final validation.
  if mode=='corrupt':
   assert response.status_code!=200 and reached
   return
  out=ok(response);calls=len(t.phases)
  assert out['answer']['text'].count('승인 후 보고한다.')==1
  meta=out['assembly']['term_agent']
  assert meta['text_integrity']=='ACCEPTED_CLAIMS_RENDERED'
  assert meta['narrative_presentation']['version']==n.PRESERVED_VERSION
  assert meta['narrative_presentation']['streaming']=='verified-complete-answer'
  assert len(meta['case']['judgment_refs'])==7
  again=ok(api.post('/v1/rag/ask',json=body))
  assert again['answer']==out['answer'] and len(t.phases)==calls

@pytest.mark.parametrize('primed',[False,True])
def test_workflow_displays_full_verified_answer_without_generation_tokens(primed):
 import asyncio,importlib.util
 path=ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
 spec=importlib.util.spec_from_file_location('preserved_workflow',path)
 w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
 a=sample();answer=cc.compose(a,n.preserved_plan(a))['text']
 async def run():
  d=w._ChatProgress({'socketIOClientId':'synthetic'});d.enabled=True;d.sid='synthetic';d.primed=primed;sent=[]
  async def emit(name,value,room):sent.append((name,value))
  d.emit=emit
  await d.finish(answer)
  actual=''.join(v for k,v in sent if k=='token')
  assert actual==('---\n\n**최종 답변**\n\n' if primed else '')+answer
  assert all(s in actual for s in PARTS)
  assert sum(k=='end' for k,v in sent)==1
 asyncio.run(run())
