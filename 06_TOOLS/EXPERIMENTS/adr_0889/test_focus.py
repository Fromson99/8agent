from copy import deepcopy
from types import SimpleNamespace
import importlib.util
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator as V
from semantic_runtime.legal_agent import decision_projection as dp, relation_read_policy as policy, unit_relations as rel, tool_availability as available, unit_reading as reader, law_navigation as nav, completion_execution as ce, completion_v8 as v8, request_repair as rr
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent.local_gemma import provider_request
from test_batch_reference_navigation import connected,initial

def old_fixture():
 p=Path(__file__).resolve().parents[1]/'adr_0885/test_focus.py'
 spec=importlib.util.spec_from_file_location('prior_choice_fixture',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.mark.parametrize('reviews',[0,8,17,33])
def test_compact_choice_kept_under_global_budget(monkeypatch,reviews):
 m=old_fixture();inv,d,a,p,out=m.fixture(monkeypatch,m.choice(queries=['주체 의무']))
 inv.p['read_choice_reviews']={str(i):{} for i in range(reviews)}
 inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=reviews,finalization_reserve=3)
 assert dp.choose_read(inv,d,a,'p')['next_action']=='RESEARCH' and len(p)==1
 assert list(p[0]).index('sources')<list(p[0]).index('tool_options')

@pytest.mark.parametrize('used',[35,37,40])
def test_finalization_reserve_unchanged(monkeypatch,used):
 m=old_fixture();inv,d,a,p,out=m.fixture(monkeypatch,m.choice(queries=['질문']))
 inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=used,finalization_reserve=3)
 assert dp.choose_read(inv,d,a,'p') is None and not p

@pytest.mark.parametrize('obligation',['REQUIRED','CHECK_APPLICABILITY'])
@pytest.mark.parametrize('applicability',['DOES_NOT_APPLY','APPLIES','UNDETERMINED'])
def test_model_applicability_not_metadata_verdict(obligation,applicability):
 g={'connections':[{'reading_policy':{'obligation':obligation},'required_block_ids':['1','2']}], 'offers':{'full':({}, {'block_ids':['1','2']}),'partial':({}, {'block_ids':['1']})},'read_blocks':set()}
 d={'id':'R','action':'SKIP','scopes':[],'reason':'질문은 보고 대상이며 참조는 외국법인 감사 자격만 규정','applicability':applicability,'applicability_reason':'보고 대상에 관한 질문과 무관한 감사 자격'}
 if applicability=='DOES_NOT_APPLY':
  before=deepcopy(d);rel.validate({'decisions':[d],'needs_more':False},{'R':g});assert d==before
 else:
  with pytest.raises(rel.output.OutputContractError):rel.validate({'decisions':[d],'needs_more':False},{'R':g})
 d.update(action='FOLLOW',applicability='APPLIES',scopes=['partial'])
 with pytest.raises(rel.output.DecisionConflict,match='endpoint'):rel.validate({'decisions':[d],'needs_more':False},{'R':g})
 d['scopes']=['full'];rel.validate({'decisions':[d],'needs_more':False},{'R':g})
 d.update(action='SKIP',applicability='DOES_NOT_APPLY',scopes=[],applicability_reason=' ')
 with pytest.raises(rel.output.OutputContractError):rel.validate({'decisions':[d],'needs_more':False},{'R':g})

@pytest.mark.parametrize('mode',['partial','complete','excluded','revoked','recovery_blocked'])
def test_real_original_partial_article_offer_and_reader(connected,mode):
 s,_=connected;record,sid=initial(s);r=record['unit_reads'][0]
 p={'selected':{'G':r},'groups':{'G':{'status':'EXCLUDED' if mode=='excluded' else 'DEFERRED'}},'basis_history':{},'catalogue':{'query_fingerprint':'q'},'seen_actions':[]}
 inv=SimpleNamespace(s=s,p=p,read_records=lambda:p['selected'],recovery_blocked=lambda a:mode=='recovery_blocked')
 data={'sources':[{'source_id':sid}],'actions':[]};actions={};before=deepcopy(p)
 if mode=='complete':
  plan,why=available.article_plan(s,{'source_id':sid,'document_id':'d'});assert not why
  p['selected']['G']=reader.read(s,*plan,action_state=record['read_state']);before=deepcopy(p)
 if mode=='revoked':s.scope=set()
 dp.offer_partial_articles(inv,data,actions);assert p==before
 if mode!='partial':assert not actions;return
 assert len(actions)==1
 action=next(iter(actions.values()));assert action['action']=='READ_ARTICLES' and action['identity']=={'source_id':sid,'document_id':'d'}
 plan,why=available.article_plan(s,action['identity']);assert not why
 acquired=reader.read(s,*plan,action_state=record['read_state'])
 assert acquired['complete'] and '一般' not in acquired['text'] and '일반 승인은 제한한다' in acquired['text']
 p['selected']['G']=acquired;data['actions']=[];actions={}
 dp.offer_partial_articles(inv,data,actions);assert not actions and p['groups']['G']['status']=='DEFERRED'


def gap_fixture():
 view={'presentation_id':'P1','state_version':3,'laws':[],'branches':[], 'issues':[{'id':'Q1','request_quote':'질문'}], 'completion_contract':nav.cc.V8,'control_contract':'control','investigation_scope':{'request':'질문'},'sources':[{'id':'E1'}],'basis':[{'id':'E1','branch_id':'G'}], 'assessment_gaps':[{'gap_id':'gap1','gap_key':'target1'}],'gap_action_receipts':[{'id':'A1'}]}
 original=nav.decision_schema(view,{},set());wire,expand,receipt=dp.prepare(original,view)
 return original,wire,expand,view

@pytest.mark.parametrize('status',['NOT_NEEDED','UNRESOLVED','NOT_AVAILABLE','RESOLVED'])
def test_gap_proof_generation_and_roundtrip(status):
 canonical,wire,expand,view=gap_fixture();projection=Projection(wire)
 row={'gap_id':'gap1','status':status,'reason':'확인한 범위에 대한 판단'}
 if status=='RESOLVED':row['basis_refs']=['E1']
 if status=='NOT_AVAILABLE':row['action_refs']=['A1']
 raw={'next_action':'FINISH','reason':'확보 범위 종료','evidence_sufficient':False,'sufficiency_reason':'미확인 유지','basis_refs':['E1'],'issue_refs':['Q1'],'gap_resolutions':[row]}
 request=provider_request({'response_format':{'type':'json_schema','json_schema':{'name':'gap','schema':projection.wire}}})
 compact=projection.project(projection.expand(raw))
 for schema in (projection.wire,request['response_format']['json_schema']['schema']):V.check_schema(schema);V(schema).validate(compact)
 out=expand(projection.expand(raw));V(canonical).validate(out)
 result=out['gap_resolutions'][0];assert result['status']==status and result['reason']==row['reason']
 if status in ('NOT_NEEDED','UNRESOLVED'):assert result['basis_refs']==result['action_refs']==[]
 if status=='NOT_AVAILABLE':assert result['basis_refs']==[] and result['action_refs']==['A1']
 if status=='RESOLVED':assert result['basis_refs']==['E1']
 if status in ('NOT_NEEDED','UNRESOLVED','NOT_AVAILABLE'):
  raw['gap_resolutions'][0]['basis_refs']=['E1']
  with pytest.raises(ProposalError):projection.expand(raw)


def test_absence_still_requires_completed_exact_target_proof():
 inv=SimpleNamespace(p={},current_gap_round=lambda:{'action_receipts':[]})
 d={'assessment_gaps':[{'gap_id':'g','gap_key':'K'}]}
 row={'gap_id':'g','status':'NOT_AVAILABLE','reason':'찾지 못함','basis_refs':[],'action_refs':[]}
 with pytest.raises(ProposalError):rr.validate_resolutions(inv,{'gap_resolutions':[row]},d)
 row['status']='UNRESOLVED';rr.validate_resolutions(inv,{'gap_resolutions':[row]},d)
 assert row['status']=='UNRESOLVED'


def test_general_assessment_conclusion_order_preserves_contract():
 schema=v8.assessment_schema([{'id':'Q1'}],[],[{'id':'S1','source_id':'source','text':'원문'}],[])
 wire,expand=ce.assessment_projection(schema);p=Projection(wire)
 request=provider_request({'response_format':{'type':'json_schema','json_schema':{'name':'assessment','schema':p.wire}}})
 def walk(x):
  if isinstance(x,dict):
   if {'condition_tree','action','exceptions','norms'}<=set(x.get('properties',{})):
    assert list(x['properties'])[-1]=='action'
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(request['response_format']['json_schema']['schema'])
 rule={'kind':'GENERAL_RULE','subject':'주체','scope':'범위','condition_tree':None,'norms':[{'kind':'OBLIGATION','text':'효과','evidence_refs':['S1'],'source_ref':'S1'}],'exceptions':[],'fact_refs':[],'action':'결론'}
 raw={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S1'],'content_contract':v8.CONTENT,'explanation':'','rule':rule}],'issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],'gaps':[]}
 decoded=expand(raw);V(schema).validate(decoded);assert decoded['claims'][0]['rule']==rule
