import pytest
from conftest import term_glossary

def coverage_rows(value,ctx):
    rows=[];request_refs=[r['id'] for r in ctx['request_parts']]
    for claim in value['claims']:
        rows.append({'request_refs':request_refs,'issue_refs':claim['issue_refs'],
            'requirement':'현재 원문으로 확인한 업무 요건','reason':'실제 채택 주장에 연결된 원문 범위',
            'status':'SATISFIED','basis_refs':claim['evidence_refs'],'claim_refs':[claim['claim_id']],
            'gap_indices':[],'scope_quote':''})
    for i,g in enumerate(value['gaps'],1):
        if g['material']:
            rows.append({'request_refs':request_refs,'issue_refs':[g['issue_id']],
                'requirement':'아직 확인하지 못한 추가 요건','reason':g['reason'],
                'status':'UNRESOLVED','basis_refs':[],'claim_refs':[],
                'gap_indices':[i],'scope_quote':''})
    return rows

@pytest.mark.parametrize('mode,fault',[('limited_source',None),('limited_fact',None),('limited_source','first'),('limited_source','twice')])
def test_native_api_review_repair_limit_storage_and_duplicate(tmp_path,term_glossary,monkeypatch,mode,fault):
    from native_fixture import run_api
    result=run_api(tmp_path,term_glossary,mode,monkeypatch,fault)
    if fault=='twice':return
    response,calls,reviews=result
    assert len([x for x in calls if x.startswith('memory-assess')])==(2 if fault=='first' else 1)
    assert not any('requirement' in phase for phase in calls)
    assert response['assembly']['term_agent']['accepted_outcome']['disposition']=='LIMITED_ANSWER'
    rows=reviews[0]['receipt']['rows']
    assert {r['status'] for r in rows}=={'SATISFIED','UNRESOLVED'}

def test_native_supported_answer_cannot_skip_review_via_ontology_shortcut(tmp_path,term_glossary,monkeypatch):
    from native_fixture import run_api
    from semantic_runtime.legal_agent import ontology_scenario_runtime as scenarios
    monkeypatch.setattr(scenarios,'catalog_from',lambda _:object())
    def forbidden(*a,**kw):raise AssertionError('scenario-only answer must not bypass requirement review')
    monkeypatch.setattr(scenarios,'assess',forbidden)
    response,calls,reviews=run_api(tmp_path,term_glossary,'supported',monkeypatch)
    assert response['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
    assert all(r['status']=='SATISFIED' for r in reviews[0]['receipt']['rows'])
