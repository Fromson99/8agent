from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import requirement_coverage as rc
from semantic_runtime.legal_agent import completion_execution as ce,completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError,ProposalError

def fixture():
    options=[{'id':'S1','source_id':'one','text':'대상자는 신고한다.'},{'id':'S2','source_id':'two','text':'서류 목록은 세칙에 따른다.'}]
    issues=[{'id':'Q1','question':'신고 요건'}, {'id':'Q2','question':'제출 서류'}]
    ctx=rc.context('신고 요건을 알려줘.\n제출 서류도 알려줘.',issues,options)
    value={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S1']}],
        'gaps':[{'issue_id':'Q2','material':True,'kind':'MISSING_SOURCE','reason':'위임된 제출 서류 목록의 본문이 필요하다.','material_id':None,'missing_target':'','suggested_action':'RESEARCH'}],
        'issue_assessments':[{'issue_id':'Q1','status':'COVERED','reason':'현재 원문 확인'}, {'issue_id':'Q2','status':'INSUFFICIENT','reason':'목록 원문 필요'}],
        rc.FIELD:[{'request_refs':['R1'],'issue_refs':['Q1'],'requirement':'신고 요건','reason':'신고 규칙과 직접 연결',
            'status':'SATISFIED','basis_refs':['S1'],'claim_refs':['C1'],'gap_indices':[],'scope_quote':''},
            {'request_refs':['R2'],'issue_refs':['Q2'],'requirement':'제출 서류','reason':'위임 위치만 있고 목록 본문이 없다',
            'status':'UNRESOLVED','basis_refs':['S2'],'claim_refs':[],'gap_indices':[1],'scope_quote':''}]}
    return value,ctx,options

def test_full_request_preserved_even_when_intent_omits_second_demand():
    v,c,o=fixture();c=rc.context('신고 요건을 알려줘.\n제출 서류도 알려줘.',c['issues'][:1],o)
    v['gaps'][0]['issue_id']='Q1';v[rc.FIELD][1]['issue_refs']=['Q1']
    rc.validate_review(v,c,o)
    v[rc.FIELD].pop()
    with pytest.raises(ProposalError) as exc:rc.validate_review(v,c,o)
    assert any(x['code']=='REQUIREMENT_COVERAGE_MISSING' for x in exc.value.issues)

@pytest.mark.parametrize('lines',[1,2,32,33,100])
def test_text_parts_never_truncate_or_infer_legal_requirements(lines):
    text='\n'.join(f'항목 {i}의 기준과 예외는?' for i in range(lines))
    c=rc.context(text,[{'id':'Q8'}],[])
    assert ''.join(x['text'] for x in c['request_parts'])==text
    assert len(c['request_parts'])<=32 and not c['semantic_completeness_certified']

@pytest.mark.parametrize('fault',['claim','cross_issue','evidence','missing_request','missing_issue','reason','gap_index','nonmaterial','gap_wrong_issue','unreviewed_gap'])
def test_false_coverage_cannot_pass_with_reason_only(fault):
    v,c,o=fixture()
    if fault=='claim':v[rc.FIELD][0]['claim_refs']=['C99']
    if fault=='cross_issue':v['claims'][0]['issue_refs']=['Q2']
    if fault=='evidence':v[rc.FIELD][0]['basis_refs']=['S2']
    if fault=='missing_request':v[rc.FIELD][1]['request_refs']=['R1']
    if fault=='missing_issue':v[rc.FIELD][1]['issue_refs']=['Q1']
    if fault=='reason':v[rc.FIELD][0]['reason']='   '
    if fault=='gap_index':v[rc.FIELD][1]['gap_indices']=[8]
    if fault=='nonmaterial':v['gaps'][0]['material']=False
    if fault=='gap_wrong_issue':v['gaps'][0]['issue_id']='Q1'
    if fault=='unreviewed_gap':v['gaps'].append(deepcopy(v['gaps'][0]))
    before=deepcopy(v)
    with pytest.raises(ProposalError):rc.validate_review(v,c,o)
    assert v==before

@pytest.mark.parametrize('basis',['original','request','none','fake_quote','fake_evidence'])
def test_grounded_exclusion_allowed_and_fabrication_rejected(basis):
    v,c,o=fixture();v['gaps']=[]
    row=v[rc.FIELD][1];row.update(status='EXCLUDED',gap_indices=[],reason='현재 요청 범위에서 불필요함',basis_refs=[])
    if basis=='original':row['basis_refs']=['S2']
    if basis=='request':
        c=rc.context('신고 요건을 알려줘.\n제출 서류는 제외해줘.',c['issues'],o)
        row['scope_quote']='제출 서류는 제외해줘.'
    if basis=='fake_quote':row['scope_quote']='제출 서류는 빼줘.'
    if basis=='fake_evidence':row['basis_refs']=['S404']
    if basis in ('original','request'):rc.validate_review(v,c,o)
    else:
        with pytest.raises((ProposalError,ValidationError)):rc.validate_review(v,c,o)

def test_receipt_reuse_binds_request_and_current_evidence():
    v,c,o=fixture();result={k:deepcopy(x) for k,x in v.items() if k!=rc.FIELD}
    rc.retain(result,v,c,o);rc.verify_saved(result,c,o)
    for changed in (rc.context('다른 질문',c['issues'],o),rc.context('신고 요건을 알려줘.\n제출 서류도 알려줘.',c['issues'],[{**o[0],'text':'변조'},o[1]])):
        with pytest.raises(ContractError):rc.verify_saved(result,changed,o)
    result[rc.FIELD]['rows'][0]['reason']='changed'
    with pytest.raises(ContractError):rc.verify_saved(result,c,o)

def test_unreviewed_fallback_preserves_known_claims_and_marks_limit():
    result={'claims':[{'claim_id':'C1'}],'disposition':'ANSWER','answer_coverage':'COVERED','limitations':[],'limitation_items':[]}
    rc.limit_unreviewed(result)
    assert result['claims']==[{'claim_id':'C1'}] and result['disposition']=='LIMITED_ANSWER'
    assert result['answer_coverage']=='PARTIAL' and result['limitations']

def test_new_unknown_locator_requirement_uses_existing_reentry():
    from semantic_runtime.legal_agent.corrected_memory import Reenter
    v,c,o=fixture();rc.validate_review(v,c,o)
    host=SimpleNamespace(s=SimpleNamespace(sources=SimpleNamespace(profile={'candidate_navigation':{'assessment_reentry_limit':2},'selection_time_reserve_seconds':3}),
        work=SimpleNamespace(budget=lambda:{'model_limit':40,'finalization_reserve':3,'model_reserved':5},event=lambda *a:None),context=SimpleNamespace(remaining=lambda:100)),issues=c['issues'],reentry_counters={})
    with pytest.raises(Reenter) as exc:ce.CompletionExecution.finish_assessment(host,v,{'investigation_state':{}},[],o,False,False,set(),{}, {},'test',{},[],'signature')
    assert exc.value.payload['gaps'][0]['missing_target']==''
    assert exc.value.payload['gaps'][0]['suggested_action']=='RESEARCH'

def test_projection_keeps_review_and_existing_correction_owner():
    v,c,o=fixture();schema=rc.attach(cc.assessment_schema(c['issues'],[],o),c,o)
    wire,expand=ce.assessment_projection(schema,allowed_targets=[''])
    assert rc.FIELD in wire['required']
    core,core_schema=rc.core(v,schema)
    assert rc.FIELD not in core and rc.FIELD not in core_schema['properties']
    assert v[rc.FIELD] and schema['properties'][rc.FIELD]

def test_policy_requires_supported_assessment_and_boolean():
    from semantic_runtime.legal_agent.law_candidates import validate_policy
    assert rc.enabled({'candidate_navigation':{'requirement_coverage':True}})
    assert not rc.enabled({})
    for policy in ({'requirement_coverage':'true'},{'requirement_coverage':True}):
        with pytest.raises(ContractError):validate_policy(policy)

def test_valid_gap_remains_extractable_after_rejected_coverage_without_read_review():
    from semantic_runtime.legal_agent.read_judgment_final import independent_core
    v,c,o=fixture();schema=rc.attach(cc.assessment_schema(c['issues'],[],o),c,o)
    wire,_=ce.assessment_projection(schema,allowed_targets=[''])
    raw={k:deepcopy(x) for k,x in v.items() if k!='disposition'}
    raw['claims'][0]['text']='신고 의무가 있다.'
    raw[rc.FIELD]=[]
    extracted=independent_core(raw,wire,None,'assess')
    assert extracted and extracted['gaps']==v['gaps']

@pytest.mark.parametrize('version',[5,6,7,8])
def test_modern_contract_extensions_strip_to_original(version):
    import importlib
    v,c,o=fixture();content=importlib.import_module('semantic_runtime.legal_agent.completion_v'+str(version))
    baseline=content.assessment_schema(c['issues'],[],o,[])
    full=rc.attach(baseline,c,o);_,restored=rc.core(v,full)
    assert restored==baseline
