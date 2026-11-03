from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent import assessment_input as ai, assessment_links as links, source_work_review as work, read_judgment_final as final
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.output_contract import validate_shape
from test_need_continuity import fixture
from fixtures import share

@pytest.mark.parametrize('stage',['memory-assess','memory-assess-repair'])
@pytest.mark.parametrize('scenario',[False,True])
def test_full_input_and_legacy_roundtrip(stage,scenario):
 text='현재 질문과 원문 '+('조건과 예외를 보존한다. '*100)+'끝의 승인 예외'
 v={'source_stage':stage,'current_request':text,'source':text,'current_facts':[{'text':text}]}
 if scenario:v['hypothetical_scenario']={'question':text}
 p=ai.project(v);assert p[ai.META]['version']==ai.VERSION
 assert len(p[ai.META]['texts'])==1 and json.dumps(p,ensure_ascii=False).count(text)==1
 assert ai.restore(p)==v
 old=deepcopy(p);old[ai.META]['version']='lossless-assessment-input-v1';assert ai.restore(old)==v
 forged=deepcopy(p);forged[ai.META]['texts'][0]['text']+='x'
 with pytest.raises(ContractError):ai.restore(forged)
 assert ('current_case' in p)==scenario

def test_other_stages_unchanged_and_no_slicing():
 for stage in ('read','source-law-navigation-read-choice','memory-compose'):
  v={'source_stage':stage,'text':'x'*1000,'again':'x'*1000};assert ai.project(v)==v
 v={'source_stage':'memory-assess','text':'x'*1000};p=ai.project(v)
 assert not p[ai.META]['texts'] and ai.restore(p)==v

def case(complete=True):
 inv,data,ctx,opts,value=fixture(target=True,complete=complete)
 ctx.pop('change_review',None)
 base={'type':'object','additionalProperties':False,'properties':{k:{} for k in ('claims','gaps','issue_assessments')},'required':['claims','gaps','issue_assessments']}
 schema=links.attach(final.attach(base,ctx,opts),opts)
 s,expand=work.projection(schema,ctx,opts);wire,expand_links=links.projection(s)
 def decode(raw):return expand(expand_links(raw))
 def model(v):
  v=deepcopy(v);ids={n['id'] for n in work.eligible(ctx,opts)}
  v['read_judgment_review']['needs']=[r for r in v['read_judgment_review']['needs'] if r['id'] not in ids]
  return share(v)
 return ctx,opts,value,schema,wire,decode,model

@pytest.mark.parametrize('disposition',['USE','EXCLUDE','OPEN'])
def test_source_work_follows_explicit_scope_without_semantic_closure(disposition):
 ctx,opts,v,s,wire,decode,model=case()
 assert len(work.eligible(ctx,opts))==1
 if disposition!='USE':
  v['claims']=[]
  for row in v['read_judgment_review']['judgments']:row.update(disposition='UNRESOLVED' if disposition=='OPEN' else 'NOT_USED',claim_refs=[])
  for row in v['read_judgment_review']['needs']:row.update(status='OPEN' if disposition=='OPEN' else 'NOT_NEEDED',claim_refs=[],gap_indices=[1] if disposition=='OPEN' else [])
  for review in v['read_judgment_review']['scope_reviews']:
   for row in review['groups']:row.update(disposition=disposition,claim_refs=[],gap_indices=[1] if disposition=='OPEN' else [])
 if disposition=='OPEN':
  v['gaps']=[{'material':True,'issue_id':'Q1','reason':'미확인 입력'}];v['issue_assessments'][0]['status']='PARTIAL'
 raw=model(v);saved=decode(raw);validate_shape(saved,s);final.validate_review(saved,ctx,opts)
 assert saved['claims']==v['claims'] and saved['gaps']==v['gaps']
 assert saved['read_judgment_review']['scope_reviews']==v['read_judgment_review']['scope_reviews']
 row=saved['read_judgment_review']['needs'][-1]
 assert row['status']==('OPEN' if disposition=='OPEN' else 'RESOLVED')
 assert row['claim_refs']==(['C1'] if disposition=='USE' else [])
 assert len(raw['read_judgment_review']['needs'])+1==len(saved['read_judgment_review']['needs'])
 assert links.repair_proposal(work.repair_proposal(saved,ctx,opts))==raw
 before=deepcopy(raw);assert work.repair_proposal(raw,ctx,opts)==before

@pytest.mark.parametrize('fault',['missing_target','duplicate_target','missing_range','duplicate_range','foreign_range','fake_claim','open_without_gap','exclude_adopted','blank_reason','foreign_issue'])
def test_scope_faults_cannot_be_hidden_by_host_projection(fault):
 ctx,opts,v,s,wire,decode,model=case();reviews=v['read_judgment_review']['scope_reviews'];g=reviews[0]['groups'][0]
 if fault=='missing_target':reviews.clear()
 if fault=='duplicate_target':reviews.append(deepcopy(reviews[0]))
 if fault=='missing_range':reviews[0]['groups']=[]
 if fault=='duplicate_range':reviews[0]['groups'].append(deepcopy(g))
 if fault=='foreign_range':g['basis_refs']=['foreign']
 if fault=='fake_claim':g['claim_refs']=['fake']
 if fault=='open_without_gap':g.update(disposition='OPEN',claim_refs=[])
 if fault=='exclude_adopted':g.update(disposition='EXCLUDE',claim_refs=[])
 if fault=='blank_reason':g['reason']=' '
 if fault=='foreign_issue':g['issue_refs']=['foreign']
 with pytest.raises(Exception) as error:final.validate_review(decode(model(v)),ctx,opts)
 assert isinstance(error.value,(ProposalError,__import__('jsonschema').ValidationError)),type(error.value)

@pytest.mark.parametrize('fault',['incomplete','membership_gap','not_acquired','empty','legacy'])
def test_incomplete_or_legacy_needs_remain_model_owned(fault):
 ctx,opts,v,s,wire,decode,model=case(fault!='incomplete')
 if fault=='membership_gap':ctx['need_continuity']['targets'][0]['membership_gaps']=['missing']
 if fault=='not_acquired':ctx['need_continuity']['targets'][0]['acquired']=False
 if fault=='empty':ctx['need_continuity']['targets'][0]['available_evidence_refs']=[]
 if fault=='legacy':ctx['need_continuity']['version']='declared-need-continuity-v1'
 assert work.eligible(ctx,opts)==[]
 wire,expand=work.projection(s,ctx,opts);assert wire==s


def test_semantic_need_still_requires_own_issue_and_claim():
 ctx,opts,v,s,wire,decode,model=case()
 row=next(r for r in v['read_judgment_review']['needs'] if r['id'] not in {n['id'] for n in work.eligible(ctx,opts)})
 row['claim_refs']=['fake']
 with pytest.raises(ProposalError):final.validate_review(decode(model(v)),ctx,opts)


def test_host_rows_and_shared_links_saved_tamper_detection():
 ctx,opts,v,s,wire,decode,model=case();value=decode(model(v));result={}
 # Saved relationship verification does not need a mutable investigation.
 result['read_judgment_review']={'review':value['read_judgment_review']}
 result['review_links']=value['review_links'];result['assessment_basis']={'review_links_version':links.VERSION}
 links.verify_saved(result)
 path=result['review_links']['bindings'][0]['path'];node=result
 view={'read_judgment_review':result['read_judgment_review']['review']}
 for x in path.split('/')[1:]:view=view[int(x)] if isinstance(view,list) else view[x]
 view['claim_refs']=['forged']
 with pytest.raises(ContractError):links.verify_saved(result)

def test_mock_shared_branch_does_not_drop_previous_definitions():
 ctx,opts,v,s,wire,decode,model=case()
 raw=model(v);reshared=share(raw)
 assert decode(raw)==decode(reshared)
 assert reshared['review_links']
