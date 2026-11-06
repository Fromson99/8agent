from copy import deepcopy
from pathlib import Path
import gzip,json,pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import wire_schema as ws,source_work_review as sw,read_judgment_final as final
from semantic_runtime.legal_agent.errors import ProposalError
ROOT=Path(__file__).resolve().parents[3]
def record():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1361-repaired-qwen-bf16-answers/artifacts/public-live/B03-17-deepinfra/canonical/009.json.gz'
    v=json.load(gzip.open(p,'rt'))['view'];return v['read_judgments'],v['evidence_options'],v['repair_feedback']['rejected_assessment']
def test_same_key_order_in_every_finite_disposition_branch_without_constraint_changes():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1361-repaired-qwen-bf16-answers/artifacts/public-live/B03-03-deepinfra/raw/call-007/request.json.gz'
    s=json.load(gzip.open(p,'rt'))['response_format']['json_schema']['schema'];old=deepcopy(s);new,_=ws.discriminator_first(s)
    assert new==old and s==old
    item=new['properties']['read_judgment_review']['properties']['judgments']['items']
    assert list(item['properties'])[:2]==['id','disposition']
    assert all(list(b['properties'])[:2]==['id','disposition'] for b in item['anyOf'])
    assert ws.discriminator_first(new)[1]==0
    # const/enum data are never traversed as a schema.
    data={'const':{'properties':{'x':{'const':1}}}};assert ws.discriminator_first(data)==(data,0)
def projection():
    c,o,v=record();schema=final.attach({'type':'object','properties':{},'required':[]},c,o);wire,e=sw.projection(schema,c,o)
    return c,o,v,schema,wire,e

def test_unacquired_bound_need_cannot_generate_impossible_resolved_status():
    c,o,v,s,w,e=projection();row=v['read_judgment_review']['needs'][0];before=deepcopy((c,o,v,s))
    assert Draft202012Validator(s['properties']['read_judgment_review']['properties']['needs']['items']).is_valid(row)
    assert not Draft202012Validator(w['properties']['read_judgment_review']['properties']['needs']['items']).is_valid(row)
    assert (c,o,v,s)==before
@pytest.mark.parametrize('status',['OPEN','NOT_NEEDED'])
def test_model_keeps_both_open_and_exclusion_choices(status):
    c,o,v,s,w,e=projection();row=deepcopy(v['read_judgment_review']['needs'][0]);row.update(status=status,claim_refs=[],material=status=='OPEN',gap_indices=[1] if status=='OPEN' else [],scope_quote='' if status=='OPEN' else c['need_continuity']['question'])
    assert Draft202012Validator(w['properties']['read_judgment_review']['properties']['needs']['items']).is_valid(row)

def test_acquired_and_unbound_needs_retain_resolved_choice():
    c,o,v,s,w,e=projection();item=w['properties']['read_judgment_review']['properties']['needs']['items']
    unbound=[n['id'] for n in c['needs'] if not n.get('target_refs')]
    assert unbound
    for ident in unbound:
        row={'id':ident,'status':'RESOLVED','reason':'원문 확인','basis_refs':[o[0]['id']],
             'material':False,'claim_refs':['C1'],'gap_indices':[],'target_refs':[],'scope_quote':''}
        assert Draft202012Validator(item).is_valid(row)

def test_original_validator_still_rejects_missing_acquisition_and_adoption():
    c,o,v,s,w,e=projection()
    from semantic_runtime.legal_agent import need_continuity as nc
    _,join=nc.scope_claim_projection({'type':'object','properties':{'read_judgment_review':{'properties':{'scope_reviews':{}}}}})
    full=join(v);full['read_judgment_review']['needs'].extend(sw.derived(full,c,o))
    with pytest.raises(ProposalError):final.validate_review(full,c,o)
