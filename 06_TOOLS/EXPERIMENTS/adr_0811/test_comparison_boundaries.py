"""General comparison boundaries; synthetic source observations, no legal gold."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json
import pytest
from jsonschema import validate as schema_validate
from workflow.adapters.projection import prepare
from workflow.risk_team_compare_workflow import compare as comparison
from workflow.risk_team_compare_workflow import report
from workflow.risk_team_compare_workflow.contracts import BASIS, COMPARE, DIMENSIONS


def fixture():
    evidence=[]
    for ident,side,quote in [('I','internal','외부기준에 따라 평가값은 30 이상이다.'),
                            ('E','external','외부기준: 평가값은 45 이상이다.')]:
        evidence.append({'evidence_id':ident,'side':side,'text':quote,'spans':[{'text':quote}],
            'source_complete':True,'version_verified':True,'document_id':side,
            'metadata':{'document_name':side,'heading':'기준 조항'},'generation_id':'synthetic',
            'source_artifact_hash':side+'-hash'})
    citations=[{'evidence':e['evidence_id'],'quote':e['text']} for e in evidence]
    issues=[{'id':'measure-17','label':'평가 기준','numeric':True}]
    pair={'pair_id':'P1','issue_id':issues[0]['id'],'internal':['I'],'external':['E'],
        'applicability':{'status':'MATCH','reason':'모의 적용','as_of':'2026-10-01','citations':citations},
        'basis_relation':'DIRECT','basis_path':[],'comparison_eligibility':True,'reason':'모의 근거',
        'content_difference':'모의 내용','content_citations':citations}
    row={'pair_id':'P1','item':'평가 기준','verdict':'CONFLICT','difference':'모의 임계값 차이',
        'reason':'모의 판단','citations':citations,'numeric':True,
        'dimensions':[{'name':name,'status':'DIFFERENT' if name=='value' else
                       ('NOT_APPLICABLE' if name in ('numerator','denominator') else 'MATCH'),
                       'citations':citations,'reason':'양측 원문에서 검토한 모의 차원'} for name in DIMENSIONS],
        'unresolved':[]}
    return evidence,issues,pair,{'rows':[row],'answer':'모의 비교','unresolved':[]}


def test_numeric_threshold_difference_can_be_conflict_without_fake_formula():
    evidence,issues,pair,value=fixture()
    schema_validate(value,COMPARE)
    comparison.validate(value,evidence,{'pairs':[pair]},issues)
    assert len(value['rows'][0]['dimensions'])==len(DIMENSIONS)
    assert next(d for d in value['rows'][0]['dimensions'] if d['name']=='value')['status']=='DIFFERENT'


@pytest.mark.parametrize('status',['MATCH','DIFFERENT','NOT_APPLICABLE'])
def test_resolved_dimension_cannot_use_only_one_side(status):
    evidence,issues,pair,value=fixture()
    value['rows'][0]['dimensions'][0].update(status=status,citations=[value['rows'][0]['citations'][0]])
    with pytest.raises(ValueError,match='both original sides'):
        comparison.validate(value,evidence,{'pairs':[pair]},issues)


@pytest.mark.parametrize('verdict',['CONFORMS','CONFLICT','ADDITIONAL_INTERNAL','POSSIBLE_GAP'])
def test_unknown_dimension_never_becomes_substantive_judgment(verdict):
    evidence,issues,pair,value=fixture()
    value['rows'][0]['verdict']=verdict
    value['rows'][0]['dimensions'][0]['status']='UNKNOWN'
    with pytest.raises(ValueError,match='all dimensions resolved'):
        comparison.validate(value,evidence,{'pairs':[pair]},issues)


def test_numeric_verdict_cannot_conceal_or_invent_difference():
    evidence,issues,pair,value=fixture()
    value['rows'][0]['verdict']='CONFORMS'
    with pytest.raises(ValueError,match='cannot conceal'):
        comparison.validate(value,evidence,{'pairs':[pair]},issues)
    value['rows'][0]['verdict']='CONFLICT'
    for dimension in value['rows'][0]['dimensions']:
        dimension['status']='MATCH'
    with pytest.raises(ValueError,match='differing dimension'):
        comparison.validate(value,evidence,{'pairs':[pair]},issues)


def test_not_applicable_cannot_erase_entire_numeric_question():
    evidence,issues,pair,value=fixture()
    for dimension in value['rows'][0]['dimensions']:
        dimension['status']='NOT_APPLICABLE'
    with pytest.raises(ValueError,match='applicable comparison dimension'):
        comparison.validate(value,evidence,{'pairs':[pair]},issues)


@pytest.mark.parametrize('original',['조건🙂\r\n예외\t'*1300,'가'*24003])
def test_citation_is_one_intact_original_span(original):
    evidence,issues,pair,_=fixture()
    for e in evidence:e.update(text=original,spans=[{'text':original}])
    before=deepcopy(evidence)
    view,wire,expand,receipt=prepare('BASIS',{'sources':evidence,'scope':{'issues':issues},'as_of':None},BASIS)
    assert receipt['citation_count']==len(evidence)
    for source in view['sources']:
        assert source['citation_options']==[{'citation_id':source['citation_options'][0]['citation_id'],'text':original}]
    assert evidence==before
    pair.pop('pair_id');pair['applicability'].pop('as_of')
    chosen=[{'citation_id':s['citation_options'][0]['citation_id']} for s in view['sources']]
    pair.update(content_citations=chosen);pair['applicability']['citations']=chosen
    value={'pairs':[pair],'gaps':[],'summary':'정확 원문'}
    schema_validate(value,wire)
    got=expand(value);schema_validate(got,BASIS)
    assert [c['quote'] for c in got['pairs'][0]['content_citations']]==[original,original]


def test_deferred_does_not_publish_unaccepted_absence_or_gap_claims(monkeypatch):
    import workflow.presentation as presentation
    evidence,issues,pair,_=fixture()
    invented='미조사 규정은 존재하지 않는다고 단정한다'
    pair.update(reason=invented,content_difference=invented,comparison_eligibility=False,basis_relation='CONTENT_ONLY')
    pair['applicability'].update(status='UNKNOWN',reason=invented)
    for e in evidence:e['version_verified']=False
    before=deepcopy(pair)
    compared=comparison.deferred(pair,issues,invented,evidence=evidence)
    schema_validate(compared,COMPARE)
    comparison.validate(compared,evidence,{'pairs':[pair]},issues)
    assert invented not in json.dumps(compared,ensure_ascii=False) and pair==before
    assert all('['+e['evidence_id']+']' in compared['rows'][0]['difference'] for e in evidence)
    assert all(any(c['quote']==e['text'] for c in compared['rows'][0]['citations']) for e in evidence)
    state={'basis':{'pairs':[pair],'gaps':[{'issue_id':issues[0]['id'],'kind':'MISSING_REFERENCE',
           'reason':invented,'action':{'side':'external','question':invented,'reason':invented,'context_evidence':['E']}}],
           'summary':invented},'comparison':compared,'scope':{'issues':issues,'missing_user_facts':[]},
           'gaps':[],'rag_results':{}}
    monkeypatch.setattr(presentation,'evidence',lambda *args:evidence)
    monkeypatch.setattr(presentation,'active_ids',lambda state:{'I','E'})
    ctx=NS(request={'question':'평가기준 비교','as_of':None,'workflow_id':'risk_team_compare_workflow',
        'workflow_version':'1.1.0','request_id':'synthetic','return_to':None},
        context=NS(run_id='synthetic',binding_hash='binding',binding={}),
        repo=NS(state=lambda:{'revision':1},work=NS(budget=lambda:{})))
    result=report.build(ctx,state)
    assert invented not in result['answer']['text']
    assert invented not in json.dumps(result['answer']['unresolved'],ensure_ascii=False)
    assert invented not in json.dumps(result['report']['display_basis'],ensure_ascii=False)
    assert result['report']['basis']['pairs'][0]['reason']==invented
    assert result['report']['basis_status']=='AUDIT_MODEL_PROPOSALS'
    assert 'external 기준 조항' in result['answer']['text']
    assert pair==before


def test_deferred_preserves_repair_exhaustion_without_raw_model_reason():
    evidence,issues,pair,_=fixture()
    result=comparison.deferred(pair,issues,'MODEL_REPAIR_EXHAUSTED',evidence=evidence)
    assert '해당 비교 판단의 수정 한도를 소진했습니다.' in result['unresolved']


def test_no_pair_does_not_forward_unaccepted_gap_reason():
    invented='미조사 규정은 존재하지 않는다고 단정한다'
    state={'basis':{'pairs':[],'gaps':[{'reason':invented}]}}
    result=comparison.compare(NS(request={'use_llm':True}),state)
    assert invented not in json.dumps(result,ensure_ascii=False)


def test_model_deferred_row_is_projected_once_and_reused(monkeypatch):
    import workflow.presentation as presentation
    evidence,issues,pair,value=fixture()
    invented='미조사 규정은 존재하지 않는다고 단정한다'
    value['rows'][0].update(verdict='DEFERRED',difference=invented,reason=invented,unresolved=[invented])
    value['unresolved']=[invented]
    calls=[];saved=[]
    def decide(*args):
        calls.append(args[0]);args[-1](value);return deepcopy(value)
    def packets(*args,**kwargs):
        return [({'packet':{'plan_hash':'one','index':0,'count':1,'dependency_closure_complete':True}},evidence)]
    monkeypatch.setattr(presentation,'packets',packets)
    monkeypatch.setattr(presentation,'checkpoint',lambda *args:None)
    ctx=NS(request={'use_llm':True},model=NS(decide=decide),
        repo=NS(save=lambda state:saved.append(deepcopy(state)),work=NS(event=lambda *args:None)))
    state={'basis':{'pairs':[pair],'gaps':[]},'scope':{'issues':issues},'rag_results':{}}
    first=comparison.compare(ctx,state)
    assert invented not in json.dumps(first,ensure_ascii=False)
    restored=json.loads(json.dumps(saved[-1]));second=comparison.compare(ctx,restored)
    assert second==first and calls==['COMPARE']


def inherited_gap_context(monkeypatch,*,material=True,mapped=True,use_llm=True,blocked_eligible=False):
    from workflow.risk_team_compare_workflow import basis
    import workflow.presentation as presentation
    evidence,issues,pair,_=fixture()
    issues.append({'id':'measure-29','label':'독립적인 다른 기준','numeric':False})
    evidence[1]['citation_names']=['외부기준']
    pair['basis_path']=[{'from_evidence':'I','to_evidence':'E','citation':pair['content_citations'][0]}]
    independent=deepcopy(pair);independent.update(pair_id='P2',issue_id=issues[1]['id'])
    pair['comparison_eligibility']=blocked_eligible if material else True
    gap={'issue_id':'Q1','kind':'MISSING_SOURCE','material':material,
        'reason':'조사하지 않은 규정이 없다고 단정하는 원래 제안',
        'missing_target':'추가 별지 원문','suggested_action':'RESEARCH',
        'target_binding':{'source_ids':['native-source-I'],'absence_proven':False},
        'parent_issue_refs':[issues[0]['id']] if mapped else [],
        'unmapped_child_issue_refs':[] if mapped else ['Q1']}
    bundle={'bundle_hash':'current-bundle','gaps':[gap],'evidence_ids':['I'],
            'origin_refs':{'I':[{'receipt':{'source_id':'native-source-I'}}]}}
    state={'scope':{'issues':issues,'missing_user_facts':[]},
           'rag_results':{'internal':{'run_id':'child-current','bundle':bundle}},
           'retained_pairs':[deepcopy(pair),deepcopy(independent)]}
    values={'pairs':[pair,independent],'gaps':[],'summary':'모델은 자식 부족을 생략했다.'}
    if material and not mapped:
        for item in values['pairs']:item['comparison_eligibility']=False
    calls=[];saved=[]
    def decide(stage,data,schema,prompt,checked):
        assert use_llm
        calls.append(deepcopy(data));schema_validate(values,schema);checked(values)
        return deepcopy(values)
    def packets(*args,**kwargs):
        return [({'packet':{'plan_hash':'both','index':0,'count':1,'dependency_closure_complete':True}},evidence)]
    monkeypatch.setattr(presentation,'packets',packets)
    monkeypatch.setattr(presentation,'checkpoint',lambda *args:None)
    ctx=NS(request={'use_llm':use_llm,'as_of':'2026-10-01'},model=NS(decide=decide),
        repo=NS(save=lambda current:saved.append(deepcopy(current))))
    return basis,ctx,state,values,calls,saved


def test_child_material_gap_cannot_be_erased_and_independent_issue_remains_eligible(monkeypatch):
    basis,ctx,state,proposal,calls,saved=inherited_gap_context(monkeypatch)
    original=deepcopy(proposal)
    result=basis.assess(ctx,state);schema_validate(result,BASIS)
    assert proposal==original
    assert [(p['issue_id'],p['comparison_eligibility']) for p in result['pairs']]==[
        ('measure-17',False),('measure-29',True)]
    assert result['gaps'][0]['issue_id']=='measure-17'
    assert result['gaps'][0]['action']['question']=='추가 별지 원문'
    assert result['gaps'][0]['action']['context_evidence']==['I']
    assert calls[0]['child_gap_constraints']['blocked_issue_ids']==['measure-17']
    assert [p['issue_id'] for p in state['retained_pairs']]==['measure-29']
    assert state['basis_child_gaps'][0]['original_gap']['target_binding']['absence_proven'] is False
    assert '원래 제안' in saved[0]['basis_child_gaps'][0]['original_gap']['reason']
    assert '원래 제안' not in result['gaps'][0]['reason']


def test_child_material_gap_rejects_parent_model_eligibility_override(monkeypatch):
    basis,ctx,state,_,_,saved=inherited_gap_context(monkeypatch,blocked_eligible=True)
    with pytest.raises(ValueError,match='current child material gaps'):
        basis.assess(ctx,state)
    assert saved[0]['basis_child_gaps'][0]['material'] is True


def test_optional_child_reference_is_preserved_without_blocking_other_issues(monkeypatch):
    basis,ctx,state,_,calls,_=inherited_gap_context(monkeypatch,material=False)
    state['rag_results']['internal']['bundle']['gaps'][0]['kind']='UNRESOLVED_REFERENCE'
    result=basis.assess(ctx,state);schema_validate(result,BASIS)
    assert result['gaps']==[] and all(p['comparison_eligibility'] for p in result['pairs'])
    assert calls[0]['child_gap_constraints']['blocked_issue_ids']==[]
    assert state['basis_child_gaps'][0]['original_gap']['kind']=='UNRESOLVED_REFERENCE'


def test_unmapped_material_gap_preserves_unknown_scope_instead_of_guessing(monkeypatch):
    basis,ctx,state,_,calls,_=inherited_gap_context(monkeypatch,mapped=False)
    result=basis.assess(ctx,state);schema_validate(result,BASIS)
    assert calls[0]['child_gap_constraints']['unmapped_material_gap_count']==1
    assert set(calls[0]['child_gap_constraints']['blocked_issue_ids'])=={'measure-17','measure-29'}
    assert {g['issue_id'] for g in result['gaps']}=={'measure-17','measure-29'}
    assert all(g['kind']=='QUERY_SCOPE' and g['action'] is None for g in result['gaps'])
    assert state['basis_child_gaps'][0]['parent_issue_refs']==[]
    assert state['basis_child_gaps'][0]['mapping_complete'] is False


def test_only_current_child_bundle_controls_active_gap_requirements(monkeypatch):
    basis,_,state,_,_,_=inherited_gap_context(monkeypatch)
    first=basis.child_gap_requirements(state)
    state['basis_child_gaps']=first['audit']
    state['rag_results']['internal']['bundle']['gaps']=[]
    state['rag_results']['internal']['bundle']['bundle_hash']='completed-new-bundle'
    current=basis.child_gap_requirements(state)
    assert first['blocked_issue_ids']==['measure-17']
    assert current=={'gaps':[],'blocked_issue_ids':[],'unmapped_material_gap_count':0,'audit':[]}


def test_no_model_path_keeps_child_gaps_in_existing_basis_contract(monkeypatch):
    basis,ctx,state,_,calls,_=inherited_gap_context(monkeypatch,use_llm=False)
    result=basis.assess(ctx,state);schema_validate(result,BASIS)
    assert calls==[] and result['pairs']==[]
    assert any(g['action'] and g['action']['question']=='추가 별지 원문' for g in result['gaps'])
    assert len(state['basis_child_gaps'])==1


def test_many_child_gaps_are_preserved_without_a_count_slice(monkeypatch):
    basis,ctx,state,_,_,_=inherited_gap_context(monkeypatch,use_llm=False)
    bundle=state['rag_results']['internal']['bundle'];original=bundle['gaps'][0]
    bundle['gaps']=[{**deepcopy(original),'missing_target':'독립 원문 대상 '+str(n)} for n in range(31)]
    result=basis.assess(ctx,state);schema_validate(result,BASIS)
    assert len(state['basis_child_gaps'])==31
    assert {g['action']['question'] for g in result['gaps'] if g['action']}=={
        '독립 원문 대상 '+str(n) for n in range(31)}
