from copy import deepcopy
from pathlib import Path
import importlib.util,json,pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import need_continuity as nc,read_judgment_final as final,assessment_links as links
from semantic_runtime.legal_agent.errors import ProposalError
from conftest import term_glossary
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('prior1352_assignments',ROOT/'06_TOOLS/EXPERIMENTS/adr_1352/test_contracts.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
def assign(review):
    groups=[];indices={};rows={}
    for key,row in review['original_reviews'].items():
        decision={k:deepcopy(v) for k,v in row.items() if k!='basis_refs'};h=digest(decision)
        if h not in indices:groups.append(decision);indices[h]=len(groups)
        rows[key]={'basis_refs':deepcopy(row['basis_refs']),'group_index':indices[h]}
    review.update(original_review_groups=groups,original_reviews=rows)
def shape():
    c,o,raw,_,old_expand=prior.shape()
    base={'type':'object','properties':{k:{} for k in ('claims','gaps','issue_assessments')},'required':['claims','gaps','issue_assessments'],'additionalProperties':False}
    s=links.attach(final.attach(base,c,o),o,direct=True);w,e=links.projection(s)
    w=nc.generation_schema(w,c);w,j=nc.scope_claim_projection(w);w,u=nc.assigned_original_review_projection(w,c)
    expected=old_expand(raw);assign(raw['read_judgment_review'])
    return c,o,raw,w,lambda r:e(j(u(r))),expected

def test_every_original_has_required_model_assignment_and_exact_canonical_result():
    c,o,v,w,e,expected=shape();before=deepcopy(v);out=e(v);final.validate_review(out,c,o)
    assert out==expected and v==before
    r=w['properties']['read_judgment_review']['properties']['original_reviews']
    assert set(r['required'])==set(r['properties']) and len(r['properties'])==6
    assert sum(len(row['groups']) for row in out['read_judgment_review']['scope_reviews'])==9
@pytest.mark.parametrize('fault',['missing','foreign_original','unknown_group','unused_group','extra_slot','excluded_adopted','unsupported_use','wrong_issue','open_without_gap'])
def test_invalid_assignment_or_semantic_decision_remains_rejected(fault):
    c,o,v,w,e,_=shape();r=v['read_judgment_review'];a=r['original_reviews'];g=r['original_review_groups']
    used=next(x for x in g if x['disposition']=='USE');unused=next(x for x in g if x['disposition']=='EXCLUDE')
    if fault=='missing':a.pop('R1')
    if fault=='foreign_original':a['R1']['basis_refs']=['FOREIGN']
    if fault=='unknown_group':a['R1']['group_index']=len(g)+1
    if fault=='unused_group':g.append(deepcopy(g[0]))
    if fault=='extra_slot':a['R999']=deepcopy(a['R1'])
    if fault=='excluded_adopted':used['disposition']='EXCLUDE'
    if fault=='unsupported_use':unused['disposition']='USE'
    if fault=='wrong_issue':used['issue_refs']=['Q2']
    if fault=='open_without_gap':unused['disposition']='OPEN'
    before=deepcopy(v)
    with pytest.raises(ProposalError):final.validate_review(e(v),c,o)
    assert v==before
@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_actual_api_assignments_repair_and_terminal_failure(tmp_path,term_glossary,monkeypatch,fault):
    import test_legal_agent_double_harness as harness
    old=harness.wire
    from semantic_runtime.legal_agent import source_goal_control as sg
    project=sg.model_projection;current={}
    def capture(schema):
        result=project(schema);wire=result[0]
        current['fields']=set(wire.get('properties',{}))|{k for b in wire.get('anyOf',[]) for k in b.get('properties',{})}
        return result
    monkeypatch.setattr(sg,'model_projection',capture)
    def assigned_wire(value):
        response=old(value);msg=response['body_json']['choices'][0]['message'];v=json.loads(msg['content']);r=v.get('read_judgment_review',{}) if isinstance(v,dict) else {}
        if isinstance(r.get('original_reviews'),dict):assign(r)
        # This fixture's empty source-work lists are fixed-zero model omissions.
        for field in ('source_targets','source_goal_exclusions'):
            if v.get(field)==[] and field not in current.get('fields',set(v)):v.pop(field)
        msg['content']=json.dumps(v,ensure_ascii=False)
        return response
    monkeypatch.setattr(harness,'wire',assigned_wire)
    prior.test_actual_api_new_review_and_bounded_repair(tmp_path,term_glossary,monkeypatch,fault)
