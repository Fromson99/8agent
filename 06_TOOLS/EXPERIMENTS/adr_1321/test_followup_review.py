from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import gzip,json,os
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import output_contract as oc,read_judgment_final as rjf
from test_memory_runtime_v2 import memory,command,start
ROOT=Path('/home/jin/8-AGENT');OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1319-multiturn-command-assessment-repair/artifacts/public-live/repeat-repaired/canonical'
def read(n):return json.loads(gzip.decompress((OLD/n).read_bytes()))

@pytest.mark.parametrize('answer_first',[False,True])
def test_followup_instructions_reach_resolve_and_check_independently_of_navigation(memory,answer_first):
 mem,f,w,send,p=memory;gid=start(send)['goal_id'];calls=[]
 f.model=SimpleNamespace(pipeline=SimpleNamespace(term_agent=SimpleNamespace(profile={'candidate_navigation':{'answer_first':answer_first}})))
 f.pipeline=f.model.pipeline
 def invoke(system,data,schema,phase):
  calls.append((phase,system))
  if phase=='memory-resolve':return command('PURPOSE_REVISE',target=gid,task='그럼 임시총회 소집 시기는?')
  assert phase=='memory-command-check';return {'valid':True,'reason':'동일 제도 후속 질문'}
 mem.invoke=invoke
 result=mem.execute({'question':'그럼 임시총회는 언제 소집하나요?','session_id':'s','request_id':'followup'},p)
 assert result['goal_id']==gid
 assert [p for p,s in calls]==['memory-resolve','memory-command-check']
 assert all('같은 조문·제도·사건' in s and '기존 목표와 관계없는 별도 주제' in s for _,s in calls)


def canonical_review():
 view=read('014.json.gz')['view'];value=read('014-output.json.gz');links={x['id']:x for x in value['review_links']}
 def expand(v):
  if isinstance(v,list):return [expand(x) for x in v]
  if not isinstance(v,dict):return v
  result={k:expand(x) for k,x in v.items() if k!='link_ref'}
  if 'link_ref' in v:result.update({k:deepcopy(links[v['link_ref']][k]) for k in ('claim_refs','basis_refs')})
  return result
 schema=rjf.review_schema(view['read_judgments'],view['evidence_options'],enforce_claim_shape=True)
 return value,expand(value['read_judgment_review']),schema


def test_actual_parent_response_errors_identify_empty_claims_under_exact_judgment_id():
 raw,review,schema=canonical_review();before=deepcopy(review)
 errors=list(Draft202012Validator(schema).iter_errors(review));assert errors
 issues=oc.schema_issues(errors)
 paths={i['path'] for i in issues if i['code']=='SCHEMA_MINITEMS'}
 assert {f'/judgments/{i}/claim_refs' for i in range(1,9)}<=paths
 assert review==before and not Draft202012Validator(schema).is_valid(review)
 assert not any(i['code']=='SCHEMA_ANYOF' for i in issues)


def test_actual_shared_link_failure_gets_alternatives_without_mutation():
 raw=read('014-output.json.gz');before=deepcopy(raw)
 failure=read('015.json.gz')['view']['repair_feedback']['validation']
 error=oc.OutputContractError('invalid links',failure['issues'],category=failure['category'])
 rows=rjf.repair_choices(raw,error)
 empty=[r for r in rows if r['cause']=='ADOPTED_WITHOUT_CLAIM']
 assert {r['path'] for r in empty}=={f'/read_judgment_review/judgments/{i}' for i in range(1,9)}
 assert all(len(r['alternatives'])==2 for r in empty)
 assert raw==before and all(x['disposition']=='USE' for x in raw['read_judgment_review']['judgments'])


def test_diagnostics_do_not_choose_between_ambiguous_same_id_branches():
 schema={'anyOf':[{'type':'object','properties':{'id':{'const':'same'},'x':{'const':n}},'required':['id','x']} for n in (1,2)]}
 raw={'id':'same','x':3}
 with pytest.raises(oc.OutputContractError) as e:oc.validate_shape(raw,schema)
 assert any(i['code']=='SCHEMA_ANYOF' for i in e.value.issues)
 assert raw=={'id':'same','x':3}


def test_missing_wire_link_cannot_be_used_as_an_adoption_suggestion():
 raw={'claims':[{'claim_id':'C1','evidence_refs':['S1']}],'review_links':[],
  'read_judgment_review':{'judgments':[{'id':'J1','disposition':'USE','link_ref':'review-link:99'}]}}
 error=oc.OutputContractError('bad link',[oc.issue('SCHEMA_ANYOF','/read_judgment_review/judgments/0')])
 assert rjf.repair_choices(raw,error)==[]
