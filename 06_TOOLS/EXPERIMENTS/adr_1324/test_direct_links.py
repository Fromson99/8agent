from copy import deepcopy
from pathlib import Path
import json
import pytest
from jsonschema import Draft202012Validator, ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import assessment_links as links, read_judgment_final as final, source_work_review as work
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.output_contract import validate_shape
from conftest import term_glossary

# Historical suites contain the same test basename. Load the intended current
# fixture by its exact path rather than whichever module conftest imported.
import importlib.util
_spec=importlib.util.spec_from_file_location('direct_link_scope_fixture',Path(__file__).resolve().parents[3]/'05_TESTS/CONTRACTS/test_scope_review.py')
_fixture_module=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture_module)
fixture=_fixture_module.fixture


def case(host=False):
    ctx,options,value=fixture()
    base={'type':'object','additionalProperties':False,
          'properties':{k:{} for k in ('claims','gaps','issue_assessments')},
          'required':['claims','gaps','issue_assessments']}
    schema=links.attach(final.attach(base,ctx,options),options,direct=True)
    projected,expand_host=work.projection(schema,ctx,options) if host else (schema,deepcopy)
    wire,expand_links=links.projection(projected)
    if host:
        ids={n['id'] for n in work.eligible(ctx,options)}
        value['read_judgment_review']['needs']=[r for r in value['read_judgment_review']['needs'] if r['id'] not in ids]
    return ctx,options,value,schema,wire,lambda raw:expand_host(expand_links(raw))


@pytest.mark.parametrize('host',[False,True])
def test_direct_roundtrip_keeps_every_model_decision_and_repairs_same_format(host):
    ctx,opts,raw,schema,wire,expand=case(host)
    before=deepcopy(raw)
    assert 'review_links' not in wire['properties'] and 'link_ref' not in json.dumps(wire)
    result=expand(raw);validate_shape(result,schema);final.validate_review(result,ctx,opts)
    assert raw==before and result['claims']==raw['claims'] and result['gaps']==raw['gaps']
    assert result['read_judgment_review']['judgments']==raw['read_judgment_review']['judgments']
    assert result['read_judgment_review']['scope_reviews']==raw['read_judgment_review']['scope_reviews']
    receipt=result['review_links']
    assert receipt['version']==links.DIRECT_VERSION and receipt['proposal_hash']==digest(raw)
    assert len(receipt['links'])<len(receipt['bindings'])
    assert links.repair_proposal(work.repair_proposal(result,ctx,opts) if host else result)==raw


@pytest.mark.parametrize('disposition',['USE','CONDITIONAL','UNRESOLVED','NOT_USED'])
@pytest.mark.parametrize('has_claim',[False,True])
def test_judgment_cardinality_exists_in_generation(disposition,has_claim):
    c,o,v,s,w,expand=case()
    row=w['properties']['read_judgment_review']['properties']['judgments']['items']
    sample=deepcopy(v['read_judgment_review']['judgments'][0])
    sample.update(disposition=disposition,claim_refs=['C1'] if has_claim else [])
    assert Draft202012Validator(row).is_valid(sample)==(has_claim==(disposition in ('USE','CONDITIONAL')))


@pytest.mark.parametrize('disposition',['USE','EXCLUDE','OPEN'])
@pytest.mark.parametrize('has_claim',[False,True])
@pytest.mark.parametrize('has_gap',[False,True])
@pytest.mark.parametrize('has_quote',[False,True])
def test_scope_all_field_combinations_match_execution_contract(disposition,has_claim,has_gap,has_quote):
    c,o,v,s,w,expand=case()
    row=w['properties']['read_judgment_review']['properties']['scope_reviews']['items']['properties']['groups']['items']
    sample=deepcopy(v['read_judgment_review']['scope_reviews'][0]['groups'][1])
    sample.update(disposition=disposition,claim_refs=['C1'] if has_claim else [],gap_indices=[1] if has_gap else [],scope_quote='사용자 한정' if has_quote else '')
    expected=(has_claim==(disposition=='USE') and has_gap==(disposition=='OPEN') and (not has_quote or disposition=='EXCLUDE'))
    assert Draft202012Validator(row).is_valid(sample)==expected


@pytest.mark.parametrize('fault',['empty_adoption','open_without_gap','excluded_claim','foreign_evidence','fake_claim','wrong_judgment','missing_target','duplicate_range'])
def test_rejection_preserves_original_and_does_not_adopt_or_erase(fault):
    c,o,v,s,w,expand=case();g=v['read_judgment_review']['scope_reviews'][0]['groups'][1]
    if fault=='empty_adoption':v['read_judgment_review']['judgments'][0]['claim_refs']=[]
    if fault=='open_without_gap':g.update(disposition='OPEN',claim_refs=[])
    if fault=='excluded_claim':g['disposition']='EXCLUDE'
    if fault=='foreign_evidence':g['basis_refs']=['not-offered']
    if fault=='fake_claim':g['claim_refs']=['C404']
    if fault=='wrong_judgment':v['read_judgment_review']['judgments'][0]['basis_refs']=['S5']
    if fault=='missing_target':v['read_judgment_review']['scope_reviews'].pop()
    if fault=='duplicate_range':v['read_judgment_review']['scope_reviews'][0]['groups'].append(deepcopy(g))
    before=deepcopy(v)
    with pytest.raises((ProposalError,ValidationError,ContractError)):
        final.validate_review(expand(v),c,o)
    assert v==before


@pytest.mark.parametrize('version',['assessment-review-links-v1','assessment-review-links-v2',links.DIRECT_VERSION])
def test_saved_versions_and_binding_tamper(version):
    c,o,v,s,w,expand=case();value=expand(v);receipt=deepcopy(value['review_links'])
    receipt['version']=version;receipt['receipt_hash']=digest({k:x for k,x in receipt.items() if k!='receipt_hash'})
    result={'assessment_basis':{'review_links_version':version},'review_links':receipt,
            'read_judgment_review':{'review':value['read_judgment_review']}}
    links.verify_saved(result)
    bad=deepcopy(result);bad['read_judgment_review']['review']['judgments'][0]['claim_refs']=['C404']
    with pytest.raises(ContractError):links.verify_saved(bad)
    bad=deepcopy(result);bad['review_links']['links'][0]['basis_refs']=['forged']
    with pytest.raises(ContractError):links.verify_saved(bad)


def test_no_change_to_legacy_projection_api():
    row={'type':'object','additionalProperties':False,'properties':{
        'claim_refs':{'type':'array','minItems':1,'items':{'type':'string'}},
        'basis_refs':{'type':'array','minItems':1,'items':{'type':'string','enum':['S1']}}},
        'required':['claim_refs','basis_refs']}
    base={'type':'object','additionalProperties':False,'properties':{'requirement_review':{'type':'array','items':row}},'required':['requirement_review']}
    s=links.attach(base,[{'id':'S1'}]);wire,expand=links.projection(s)
    raw={'requirement_review':[{'link_ref':'review-link:1'}],
         'review_links':[{'id':'review-link:1','claim_refs':['C1'],'basis_refs':['S1']}]}
    saved=expand(raw)
    assert saved['review_links']['version']==links.VERSION
    assert links.repair_proposal(saved)==raw


@pytest.mark.parametrize('disposition',['USE','EXCLUDE','OPEN'])
@pytest.mark.parametrize('valid',[False,True])
def test_scope_constraint_survives_final_provider_projection(disposition,valid):
    from semantic_runtime.legal_agent.minimal_output import Projection
    c,o,v,s,w,expand=case()
    schema=w['properties']['read_judgment_review']['properties']['scope_reviews']['items']['properties']['groups']['items']
    value=deepcopy(v['read_judgment_review']['scope_reviews'][0]['groups'][1])
    value.update(disposition=disposition,claim_refs=['C1'] if disposition=='USE' else [],gap_indices=[1] if disposition=='OPEN' else [])
    projection=Projection(schema);wire=projection.project(value)
    assert Draft202012Validator(projection.wire).is_valid(wire)
    assert projection.expand(wire)==value
    if not valid:
        if disposition=='USE':wire['claim_refs']=[]
        elif disposition=='OPEN':wire['gap_indices']=[]
        else:wire['claim_refs']=['C1']
        assert not Draft202012Validator(projection.wire).is_valid(wire)
        with pytest.raises(ProposalError):projection.expand(wire)


@pytest.fixture
def direct_wire(monkeypatch):
    root=Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root/'06_TOOLS/EXPERIMENTS/adr_1188'))
    import api_fixture_integrated as fixture
    from semantic_runtime.legal_agent import assessment_input as ai
    decode=fixture.decode;last={};observed=[]
    def read(value):
        result=decode(ai.restore(value) if ai.META in value else value)
        last.clear();last.update(deepcopy(result));return result
    monkeypatch.setattr(fixture,'decode',read)
    import test_legal_agent_double_harness as harness
    original=harness.wire
    def response(value):
        if isinstance(value,dict) and ('read_judgment_review' in value or 'requirement_review' in value):
            value=deepcopy(value);ctx=last.get('read_judgments',{})
            targets={t['id']:t for t in ctx.get('need_continuity',{}).get('targets',[])}
            ids={n['id'] for n in ctx.get('needs',[]) if n.get('origin') in ('SOURCE_GOAL','STRUCTURE_SELECTION') and n.get('target_refs')
                 and all(targets.get(t,{}).get('available_complete') and targets[t]['available_evidence_refs'] for t in n['target_refs'])}
            if 'read_judgment_review' in value:value['read_judgment_review']['needs']=[n for n in value['read_judgment_review']['needs'] if n['id'] not in ids]
            assert 'review_links' not in value
            observed.append(deepcopy(value))
        return original(value)
    monkeypatch.setattr(harness,'wire',response)
    return observed


@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice','need_first','need_twice','open'])
def test_actual_api_direct_wire_repair_stop_saved_and_duplicate(tmp_path,term_glossary,monkeypatch,direct_wire,fault):
    from need_continuity_fixture import run_api
    result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
    assert direct_wire and all('review_links' not in r for r in direct_wire)
    if fault in ('scope_twice','need_twice'):
        assert result is None;return
    response,calls,reviews=result
    assert len([p for p in calls if p.startswith('memory-assess')])==(2 if fault in ('scope_first','need_first') else 1)
    from semantic_runtime.legal_agent.journal_storage import connect
    journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+response['run_id']+'/journal.sqlite'))
    with connect(journal) as db:
        rows=[json.loads(r[0])['assessment'] for r in db.execute("SELECT payload_json FROM event WHERE kind='ASSESSMENT_VALIDATED'")]
    assert len(rows)==1 and rows[0]['review_links']['version']==links.DIRECT_VERSION
    links.verify_saved(rows[0])
