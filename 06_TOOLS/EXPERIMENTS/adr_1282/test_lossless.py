from copy import deepcopy
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import assessment_input as ai
from semantic_runtime.legal_agent import compact_model_input as minimal
from semantic_runtime.legal_agent import requirement_coverage as rc, scenario_review as scenario
from semantic_runtime.legal_agent import review_explanation as display
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.errors import ContractError, ProposalError


def case_view(stage='memory-assess'):
    question = '현재 신청의 조건과 예외를 알려 주세요. ' * 8 + '단, 승인을 받은 것으로 가정하지 않습니다.\r\n'
    text = '  제1조 관련 조건을 정확히 확인한다.\n' * 80 + '단, 최종 승인 없이는 시작할 수 없다.\t\n'
    return {'source_stage':stage, 'question':question, 'current_request':question,
        'current_facts':[{'name':'cost','value':'735000 KRW'},{'name':'approval','value':'미확인'}],
        'hypothetical_scenario':{'kind':'FACT','changes':{'cost':{'type':'money','unit':'KRW','value':'735000'}}},
        'baseline_history':{'authority':'HISTORICAL_ONLY_NOT_CURRENT_FACTS','records':{'question':question}},
        'issues':[{'id':'Q1','question':question}],
        'evidence_options':[{'id':'S1','document_id':'d1','text':text},{'id':'S2','document_id':'d2','text':text}],
        'ontology_bundles':[{'basis':{'quote':text,'source_refs':['S1']}}],
        'repair_feedback':{'reason':text,'tail':'오래된 승인을 현재 승인으로 쓰지 마세요.'}}


@pytest.mark.parametrize('stage',['memory-assess','memory-assess-repair'])
def test_exact_shared_text_restores_long_suffixes_and_authority(stage):
    original=case_view(stage);before=deepcopy(original)
    projected=ai.project(original)
    assert original==before and ai.restore(projected)==original
    assert projected['current_case']['facts']==original['current_facts']
    assert 'current_facts' not in projected and 'hypothetical_scenario' not in projected
    for text in (original['question'],original['evidence_options'][0]['text']):
        assert sum(row['text']==text for row in projected[ai.META]['texts'])==1
        assert json.dumps(projected,ensure_ascii=False).count(json.dumps(text,ensure_ascii=False))==1
    restored=ai.restore(projected)
    assert restored['evidence_options'][0]['document_id']!='d2'
    assert restored['evidence_options'][1]['id']=='S2'
    assert restored['evidence_options'][0]['text'].endswith('승인 없이는 시작할 수 없다.\t\n')


@pytest.mark.parametrize('length',[1,79,80,500,501,600,601,10000])
def test_sharing_threshold_never_cuts_text(length):
    view=case_view();text=('가'*length)+'\n끝: 예외가 아니다. 👩🏽‍💻 e\u0301'
    view['repair_feedback']={'a':text,'b':text}
    assert ai.restore(ai.project(view))==view


@pytest.mark.parametrize('fault',['suffix','reference','extra_ref_field','duplicate','hash','authority'])
def test_projection_tampering_rejected(fault):
    projected=ai.project(case_view())
    if fault=='suffix':projected[ai.META]['texts'][0]['text']+='다른 결론'
    if fault=='reference':projected['question']={ai.REF:'unknown'}
    if fault=='extra_ref_field':projected['question']['text']='changed'
    if fault=='duplicate':projected[ai.META]['texts'].append(deepcopy(projected[ai.META]['texts'][0]))
    if fault=='hash':projected[ai.META]['source_hash']='bad'
    if fault=='authority':projected['current_case']['facts'][1]['value']='승인됨'
    with pytest.raises(ContractError):ai.restore(projected)


def test_only_scenario_assessment_changes_and_instructions_are_connected():
    view=case_view();wire=minimal.project(view)
    assert ai.META in wire and ai.INSTRUCTIONS in minimal.instructions(wire)
    for stage in ('memory-compose','source-law-navigation-1-read-choice'):
        other=case_view(stage)
        assert ai.project(other)==other
    general=case_view();general.pop('hypothetical_scenario')
    assert ai.project(general)==general


def test_old_display_version_remains_readable_without_reprojection():
    view=case_view();old=minimal.bind(view,{},version='compact-model-input-v1')
    projected=minimal.project(old)
    assert ai.META not in projected and 'hypothetical_scenario' in projected
    current=minimal.project(minimal.bind(view,{}))
    assert ai.restore(current)==projected
    with pytest.raises(ContractError):minimal.bind(view,{},version='foreign')


def gap_case(reason):
    options=[{'id':'S1','source_id':'s','text':'승인이 없으면 시작할 수 없다.'}]
    ctx=rc.context('금액 조건과 승인 미확인을 설명해 주세요.',[{'id':'Q1','question':'금액·승인'}],options)
    value={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S1']}],
        'gaps':[{'issue_id':'Q1','material':True,'kind':'MISSING_FACT','reason':reason,
                 'material_id':None,'missing_target':'','suggested_action':'REQUEST_FACT'}],
        rc.FIELD:[{'request_refs':['R1'],'issue_refs':['Q1'],'requirement':'금액·승인 설명','reason':'검토 내용',
                   'status':'SATISFIED','basis_refs':['S1'],'claim_refs':['C1'],'gap_indices':[],'scope_quote':''}]}
    return value,ctx,options


@pytest.mark.parametrize('length',[499,500,501,599,600,601,10000])
def test_gap_reference_preserves_entire_reason_and_does_not_confirm(length):
    reason='검토 문맥. '*length+'끝의 필수 조건: 서면 승인을 확인하지 못했다.'
    value,ctx,options=gap_case(reason);before=deepcopy(value)
    fixed,receipt=rc.reconcile_material_gaps(value,ctx,options)
    assert value==before and fixed['gaps']==value['gaps'] and fixed['claims']==value['claims']
    assert fixed[rc.FIELD][-1]['gap_indices']==[1] and fixed[rc.FIELD][-1]['status']=='UNRESOLVED'
    assert reason not in (fixed[rc.FIELD][-1]['requirement'],fixed[rc.FIELD][-1]['reason'])
    assert receipt['original_proposal']==value and receipt['gap_references'][0]['gap_hash']==digest(value['gaps'][0])
    assert rc.reconcile_material_gaps(fixed,ctx,options)==(fixed,None)
    saved={k:deepcopy(v) for k,v in fixed.items() if k!=rc.FIELD}
    rc.retain(saved,fixed,ctx,options,reconciliation=receipt);rc.verify_saved(saved,ctx,options)
    assert saved['gaps'][0]['reason']==reason


@pytest.mark.parametrize('fault',['foreign_claim','wrong_evidence','ambiguous','blank','full'])
def test_gap_reference_does_not_guess_or_bypass(fault):
    value,ctx,options=gap_case('필수 확인 사항. '*100+'미승인')
    if fault=='foreign_claim':value[rc.FIELD][0]['claim_refs']=['C9']
    if fault=='wrong_evidence':value['claims'][0]['evidence_refs']=[]
    if fault=='ambiguous':
        ctx=rc.context('첫째 요구\n둘째 요구',ctx['issues'],options)
        value[rc.FIELD].append({**value[rc.FIELD][0],'request_refs':['R2']})
    if fault=='blank':value['gaps'][0]['reason']=' '
    if fault=='full':value[rc.FIELD]*=64
    before=deepcopy(value)
    with pytest.raises(ProposalError):rc.reconcile_material_gaps(value,ctx,options)
    assert value==before


def test_gap_failure_has_exact_reference_and_public_reason():
    value,ctx,options=gap_case('담당자 승인 미확인')
    with pytest.raises(ProposalError) as error:rc.validate_review(value,ctx,options)
    failure=error.value.issues[0]
    assert failure['expected_constraint']['gaps']==[{'gap_index':1,'issue_id':'Q1','kind':'MISSING_FACT','reason_path':'/gaps/0/reason'}]
    value.update(model_proposal={'review_status':'INCOMPLETE','failure':{'issues':[failure]}},issue_assessments=[])
    explanation=display.build(value,[])
    assert explanation['failed_checks'][0]['code']=='REQUIREMENT_GAP_COVERAGE'
    assert '연결' in explanation['failed_checks'][0]['reason']


def scenario_context():
    return {'schema_version':'scenario-context-v3','content_sha256':'current-branch','kind':'FACT',
        'changes':{},'unresolved':[], 'evaluations':[
            {'package_sha256':'approved','node_id':'N1','result':{'status':'TRUE'}},
            {'package_sha256':'approved','node_id':'N2','result':{'status':'UNKNOWN'}}]}


def test_server_restores_condition_constants_and_retains_unknown():
    context=scenario_context()
    schema=scenario.attach({'type':'object','properties':{},'required':[],'additionalProperties':False},context)
    projection=Projection(schema)
    assert 'condition_results' not in projection.wire['properties']['scenario_review']['properties']
    raw={'scenario_review':{'outcome':'UNCONFIRMED'}};before=deepcopy(raw)
    expanded=projection.expand(raw)
    assert raw==before and expanded['scenario_review']['condition_results']==scenario.results(context)
    scenario.check(expanded,context,[])
    expanded['scenario_review']['condition_results'].reverse()
    scenario.verify_saved({'claims':[],'model_proposal':expanded},context,[])
    expanded['scenario_review']['outcome']='CONDITIONS_MET'
    with pytest.raises(ProposalError):scenario.check(expanded,context,[])


def test_model_cannot_override_or_change_branch_condition_table():
    context=scenario_context();schema=scenario.attach({'type':'object','properties':{},'required':[],'additionalProperties':False},context)
    raw={'scenario_review':{'outcome':'UNCONFIRMED','condition_results':[{'package_sha256':'approved','node_id':'N1','status':'FALSE'}]}}
    with pytest.raises(ProposalError):Projection(schema).expand(raw)
    other={**context,'content_sha256':'other-branch'}
    raw={'scenario_review':{'outcome':'UNCONFIRMED','context_hash':context['content_sha256']}}
    with pytest.raises(ProposalError):Projection(scenario.attach({'type':'object','properties':{},'required':[],'additionalProperties':False},other)).expand(raw)


def test_compound_constants_use_wire_ids_without_rewriting_source_text():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    node='N'+'a'*32
    context=scenario_context();context['evaluations'][0]['node_id']=node
    context['evaluations'][1]['node_id']='N'+'b'*32
    references=NavigationReferences({'context':context,'source_quote':node,'question':'N1'})
    assert references.forward[node]=='N2'
    schema=scenario.attach({'type':'object','properties':{},'required':[],'additionalProperties':False},context)
    wire=references.schema(schema)
    rows=wire['properties']['scenario_review']['properties']['condition_results']['const']
    assert rows[0]['node_id']=='N2'
    # Server reconstruction must happen in the same namespace as model output.
    value=Projection(wire).expand({'scenario_review':{'outcome':'UNCONFIRMED'}})
    restored=references.restore(value)
    assert restored['scenario_review']['condition_results']==scenario.results(context)
    nested={'type':'object','properties':{'rows':{'const':[{'node_id':node,'source_quote':node,'reason':node}]}}}
    row=references.schema(nested)['properties']['rows']['const'][0]
    assert row=={'node_id':'N2','source_quote':node,'reason':node}
