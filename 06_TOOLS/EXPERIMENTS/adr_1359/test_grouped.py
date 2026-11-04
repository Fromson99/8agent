from copy import deepcopy
from pathlib import Path
import json,importlib.util,pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import need_continuity as nc,read_judgment_final as final,assessment_links as links
from semantic_runtime.legal_agent.errors import ProposalError
from conftest import term_glossary
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('prior1352_grouped',ROOT/'06_TOOLS/EXPERIMENTS/adr_1352/test_contracts.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
def group(rows):
    out={}
    for row in rows:
        key=digest({k:v for k,v in row.items() if k!='basis_refs'})
        if key not in out:out[key]={**deepcopy(row),'basis_refs':[]}
        out[key]['basis_refs'].extend(row['basis_refs'])
    return list(out.values())
def shape():
    c,o,raw,_,old_expand=prior.shape()
    base={'type':'object','properties':{k:{} for k in ('claims','gaps','issue_assessments')},'required':['claims','gaps','issue_assessments'],'additionalProperties':False}
    s=links.attach(final.attach(base,c,o),o,direct=True);w,e=links.projection(s)
    w=nc.generation_schema(w,c);w,j=nc.scope_claim_projection(w);w,u=nc.grouped_original_review_projection(w,c)
    expected=old_expand(raw);raw['read_judgment_review']['original_reviews']=group(raw['read_judgment_review']['original_reviews'].values())
    return c,o,raw,w,lambda r:e(j(u(r))),expected

def test_exact_partition_preserves_all_originals_and_decisions():
    c,o,v,w,e,expected=shape();before=deepcopy(v);out=e(v);final.validate_review(out,c,o)
    assert out==expected and v==before
    assert len(out['read_judgment_review']['scope_reviews'])==3
    assert sum(len(x['groups']) for x in out['read_judgment_review']['scope_reviews'])==9
    assert sum(len(r['basis_refs']) for r in v['read_judgment_review']['original_reviews'])==6
@pytest.mark.parametrize('fault',['missing','duplicate_across','duplicate_inside','foreign','excluded_adopted','unsupported_use','wrong_issue','open_without_gap'])
def test_grouping_never_bypasses_original_coverage_or_semantics(fault):
    c,o,v,w,e,_=shape();r=v['read_judgment_review']['original_reviews']
    used=next(x for x in r if x['disposition']=='USE');unused=next(x for x in r if x['disposition']=='EXCLUDE')
    if fault=='missing':r.pop()
    if fault=='duplicate_across':r.append(deepcopy(r[0]))
    if fault=='duplicate_inside':r[0]['basis_refs'].append(r[0]['basis_refs'][0])
    if fault=='foreign':r[0]['basis_refs'][0]='FOREIGN'
    if fault=='excluded_adopted':used['disposition']='EXCLUDE'
    if fault=='unsupported_use':unused['disposition']='USE'
    if fault=='wrong_issue':used['issue_refs']=['Q2']
    if fault=='open_without_gap':unused['disposition']='OPEN'
    before=deepcopy(v)
    with pytest.raises(ProposalError):final.validate_review(e(v),c,o)
    assert v==before
@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_actual_api_partition_repair_and_terminal_failure(tmp_path,term_glossary,monkeypatch,fault):
    import test_legal_agent_double_harness as harness
    old=harness.wire
    def grouped_wire(value):
        response=old(value);msg=response['body_json']['choices'][0]['message'];v=json.loads(msg['content']);r=v.get('read_judgment_review',{}) if isinstance(v,dict) else {}
        if isinstance(r.get('original_reviews'),dict):
            r['original_reviews']=group(r['original_reviews'].values());msg['content']=json.dumps(v,ensure_ascii=False)
        return response
    monkeypatch.setattr(harness,'wire',grouped_wire)
    prior.test_actual_api_new_review_and_bounded_repair(tmp_path,term_glossary,monkeypatch,fault)
