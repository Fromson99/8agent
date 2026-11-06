from copy import deepcopy
from pathlib import Path
import gzip
import importlib.util
import json
import pytest
from jsonschema import Draft202012Validator
from conftest import term_glossary
from semantic_runtime.legal_agent import source_work_review as work, read_judgment_final as final, need_continuity as nc
from semantic_runtime.legal_agent.errors import ProposalError

ROOT=Path(__file__).resolve().parents[3]


def saved():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1367-preserve-issue-order-and-review-scope/artifacts/public-live/B03-03-parasail/canonical/008.json.gz'
    with gzip.open(p,'rt') as f:
        v=json.load(f)['view']
    ctx,options=v['read_judgments'],v['evidence_options']
    proposal=deepcopy(v['repair_feedback']['rejected_assessment'])
    _,join=nc.scope_claim_projection({'type':'object','properties':{'read_judgment_review':{'properties':{'scope_reviews':{}}}}})
    proposal=join(proposal)
    proposal['read_judgment_review']['needs'].extend(work.derived(proposal,ctx,options))
    schema=final.attach({'type':'object','properties':{},'required':[]},ctx,options)
    wire,_=work.projection(schema,ctx,options)
    item=wire['properties']['read_judgment_review']['properties']['needs']['items']
    return ctx,options,proposal,Draft202012Validator(item)


def select(row,basis):
    row.pop('scope_quote')
    row['exclusion_basis']=basis


@pytest.mark.parametrize('basis',['ORIGINALS','CURRENT_REQUEST','REQUEST_SPAN'])
def test_real_rejected_proposal_has_three_explicit_valid_literal_choices(basis):
    ctx,options,proposal,validator=saved()
    q=ctx['need_continuity']['question']
    with pytest.raises(ProposalError):
        final.validate_review(proposal,ctx,options)
    row=proposal['read_judgment_review']['needs'][1]
    original=deepcopy(row)
    assert original['scope_quote'] not in q and not validator.is_valid(row)
    select(row,basis)
    if basis=='REQUEST_SPAN':
        start=q.index('제365조')
        row['quote_span']={'start_cp':start,'end_cp':start+len('제365조 제1항')}
    assert validator.is_valid(row)
    work._restore_exclusions([row],q)
    assert row['scope_quote']=={'ORIGINALS':'','CURRENT_REQUEST':q,'REQUEST_SPAN':'제365조 제1항'}[basis]
    assert {**row,'scope_quote':original['scope_quote']}==original
    final.validate_review(proposal,ctx,options)


@pytest.mark.parametrize('fault',['unsupported_originals','invented_quote','foreign_basis','adopted_claim','closed_gap','missing_span','beyond_question','reversed_span','blank_span'])
def test_invalid_exclusion_never_becomes_evidence(fault):
    ctx,_,proposal,validator=saved()
    q=ctx['need_continuity']['question']
    row=proposal['read_judgment_review']['needs'][1]
    select(row,'ORIGINALS')
    assert validator.is_valid(row)
    if fault=='unsupported_originals':row['basis_refs']=[]
    if fault=='invented_quote':row['scope_quote']='a fabricated quotation'
    if fault=='foreign_basis':row['exclusion_basis']='AUTOMATIC'
    if fault=='adopted_claim':row['claim_refs']=['C1']
    if fault=='closed_gap':row['gap_indices']=[1]
    if fault in ('missing_span','beyond_question','reversed_span','blank_span'):
        row['exclusion_basis']='REQUEST_SPAN'
        if fault=='beyond_question':row['quote_span']={'start_cp':0,'end_cp':len(q)+1}
        if fault=='reversed_span':row['quote_span']={'start_cp':2,'end_cp':1}
        if fault=='blank_span':row['quote_span']={'start_cp':q.index(' '),'end_cp':q.index(' ')+1}
    if fault in ('reversed_span','blank_span'):
        assert validator.is_valid(row)
        with pytest.raises(ProposalError):work._restore_exclusions([row],q)
    else:assert not validator.is_valid(row)


def test_unacquired_source_exclusion_must_select_a_question_literal():
    prior=load_prior('scope1366','adr_1366/test_scope.py')
    c,o,s,w,row=prior.shape()
    item=Draft202012Validator(w['properties']['read_judgment_review']['properties']['needs']['items'])
    select(row,'CURRENT_REQUEST')
    assert item.is_valid(row)
    row['exclusion_basis']='ORIGINALS'
    assert row['basis_refs'] and not item.is_valid(row)


def load_prior(name,relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/'06_TOOLS/EXPERIMENTS'/relative)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_normal_repair_and_terminal_refusal_through_api(tmp_path,term_glossary,monkeypatch,fault):
    from semantic_runtime.legal_agent import bounded_source_session
    import test_legal_agent_double_harness as harness
    request=bounded_source_session._Gateway.request
    wire=harness.wire
    bound={}
    def capture(self,phase,view,schema_name,**kwargs):
        result=request(self,phase,view,schema_name,**kwargs)
        if view.get('source_stage','').startswith('memory-assess'):
            bound['question']=view['read_judgments']['need_continuity']['question']
            assert work.EXCLUSION_PROMPT in result['messages'][0]['content']
        return result
    def fixture_wire(value):
        result=wire(value);message=result['body_json']['choices'][0]['message'];v=json.loads(message['content'])
        for row in v.get('read_judgment_review',{}).get('needs',[]):
            if row.get('status')!='NOT_NEEDED' or 'scope_quote' not in row:continue
            quote=row['scope_quote'];q=bound['question']
            if not quote:select(row,'ORIGINALS')
            elif quote==q:select(row,'CURRENT_REQUEST')
            elif quote in q:
                select(row,'REQUEST_SPAN');start=q.index(quote)
                row['quote_span']={'start_cp':start,'end_cp':start+len(quote)}
        message['content']=json.dumps(v,ensure_ascii=False)
        return result
    monkeypatch.setattr(bounded_source_session._Gateway,'request',capture)
    monkeypatch.setattr(harness,'wire',fixture_wire)
    load_prior('input1367','adr_1367/test_review_input.py').test_actual_intent_and_assessment_inputs(tmp_path,term_glossary,monkeypatch,fault)
