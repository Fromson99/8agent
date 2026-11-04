from copy import deepcopy
from pathlib import Path
import gzip,json,pytest
from jsonschema import ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import need_continuity as nc,read_judgment_final as final
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
ROOT=Path(__file__).resolve().parents[3]
def recorded():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1357-navigation-reason-bound-qwen-answer/artifacts/public-live/B03-17-parasail/canonical/008.json.gz'
    with gzip.open(p,'rt') as f:v=json.load(f)['view']
    c,o,value=v['read_judgments'],v['evidence_options'],v['repair_feedback']['rejected_assessment']
    # Repair input omits host-owned joins; restore them with production functions.
    _,expand=nc.scope_claim_projection({'type':'object','properties':{'read_judgment_review':{'properties':{'scope_reviews':{}}}}})
    value=expand(value)
    from semantic_runtime.legal_agent.source_work_review import derived
    value['read_judgment_review']['needs'].extend(derived(value,c,o))
    return c,o,value
def test_actual_rejected_review_exact_duplicate_targets_bind_without_legal_changes():
    c,o,v=recorded();before=deepcopy((c,o,v))
    with pytest.raises(ProposalError):final.validate_review(v,c,o)
    fixed,r=nc.bind_reviewed_targets(v,c,o);final.validate_review(fixed,c,o)
    assert len(r['changes'])==2 and r['extra_model_calls']==0 and not r['legal_content_changed']
    linked={x['target_id'] for x in r['changes']}
    assert linked=={c['need_continuity']['targets'][0]['id'],c['need_continuity']['targets'][2]['id']}
    reverted=deepcopy(fixed)
    for x in r['changes']:
        row=next(n for n in reverted['read_judgment_review']['needs'] if n['id']==x['need_id']);row['target_refs'].remove(x['target_id'])
    assert reverted==v and (c,o,v)==before
    assert nc.bind_reviewed_targets(fixed,c,o)==(fixed,None)
@pytest.mark.parametrize('fault',['different_document','different_range','different_source_hash','different_issue','absent_expected','changed_original','unknown_target','missing_adoption','missing_range_review'])
def test_nonidentical_or_invalid_review_remains_rejected(fault):
    c,o,v=recorded();target=c['need_continuity']['targets'][-1]
    if fault=='different_document':target['document_id']='another-document'
    if fault=='different_range':target['expected'][0]['end_cp']-=1
    if fault=='different_source_hash':target['expected'][0]['block_hash']='0'*64
    if fault=='different_issue':target['issue_refs'].append('another-issue')
    if fault=='absent_expected':target['expected']=[]
    if fault=='changed_original':o[0]['text']+='tampered'
    if fault=='unknown_target':v['read_judgment_review']['needs'][0]['target_refs'].append('unknown')
    if fault=='missing_adoption':v['read_judgment_review']['judgments'][0]['claim_refs']=[]
    if fault=='missing_range_review':v['read_judgment_review']['scope_reviews'].pop()
    if fault!='changed_original':c['need_continuity']['scope_input_hash']=digest([c['need_continuity']['targets'],o])
    before=deepcopy((c,o,v))
    with pytest.raises((ProposalError,ContractError,ValidationError)):
        fixed,_=nc.bind_reviewed_targets(v,c,o);final.validate_review(fixed,c,o)
    assert (c,o,v)==before
