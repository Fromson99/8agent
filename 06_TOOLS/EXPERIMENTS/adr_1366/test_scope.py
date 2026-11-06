from pathlib import Path
from copy import deepcopy
import gzip,json,importlib.util,pytest
from jsonschema import Draft202012Validator
from conftest import term_glossary
from semantic_runtime.legal_agent import source_work_review as sw,read_judgment_final as final
ROOT=Path(__file__).resolve().parents[3]
def shape():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1365-repaired-qwen-parasail-answers/artifacts/public-live/B03-17-parasail/canonical/007.json.gz'
    v=json.load(gzip.open(p,'rt'))['view'];c,o=v['read_judgments'],v['evidence_options']
    s=final.attach({'type':'object','properties':{},'required':[]},c,o);w,e=sw.projection(s,c,o)
    host={x['id'] for x in sw.eligible(c,o)};n=next(x for x in c['needs'] if x['id'] not in host and x.get('origin')=='SOURCE_GOAL')
    row={'id':n['id'],'status':'NOT_NEEDED','reason':'질문의 직접 범위와 관련 없음','basis_refs':[o[0]['id']],
         'material':False,'claim_refs':[],'gap_indices':[],'target_refs':n['target_refs'],'scope_quote':c['need_continuity']['question']}
    return c,o,s,w,row

def test_recorded_exclusion_cannot_simultaneously_adopt_a_claim():
    c,o,s,w,row=shape();before=deepcopy((c,o,s));old=Draft202012Validator(s['properties']['read_judgment_review']['properties']['needs']['items']);new=Draft202012Validator(w['properties']['read_judgment_review']['properties']['needs']['items'])
    assert new.is_valid(row);bad=deepcopy(row);bad['claim_refs']=['C1']
    assert old.is_valid(bad) and not new.is_valid(bad) and (c,o,s)==before
@pytest.mark.parametrize('fault',['empty_scope','wrong_scope','excluded_gap','open_claim','open_without_gap','open_nonmaterial','unacquired_resolved'])
def test_generation_rejects_existing_canonical_contradictions(fault):
    c,o,s,w,row=shape()
    if fault=='empty_scope':row['scope_quote']=''
    if fault=='wrong_scope':row['scope_quote']='invented exclusion'
    if fault=='excluded_gap':row['gap_indices']=[1]
    if fault.startswith('open_'):
        row.update(status='OPEN',scope_quote='',claim_refs=[],material=True,gap_indices=[1])
        if fault=='open_claim':row['claim_refs']=['C1']
        if fault=='open_without_gap':row['gap_indices']=[]
        if fault=='open_nonmaterial':row['material']=False
    if fault=='unacquired_resolved':row.update(status='RESOLVED',scope_quote='',claim_refs=['C1'])
    assert not Draft202012Validator(w['properties']['read_judgment_review']['properties']['needs']['items']).is_valid(row)

@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_actual_api_scope_guidance_and_correct_generation_contract(tmp_path,term_glossary,monkeypatch,fault):
    from semantic_runtime.legal_agent import bounded_source_session as gateway,answer_progress,need_continuity as nc
    seen=[];original=gateway._Gateway.request
    def request(self,phase,view,schema_name,**kwargs):
        body=original(self,phase,view,schema_name,**kwargs)
        stage=view.get('source_stage','')
        if stage.startswith('memory-assess'):
            text=body['messages'][0]['content'];seen.append(stage)
            assert answer_progress.SCOPE_GUIDANCE in text
            assert '구체 날짜·금액 계산 요청을 구분한다' in text
            assert '상한이지 채워야 하는 분량이 아니다' in text
            assert nc.ASSIGNED_ORIGINAL_REVIEW_PROMPT in text
            assert nc.GENERATION_PROMPT not in text and nc.SCOPE_JOIN_PROMPT not in text
        return body
    monkeypatch.setattr(gateway._Gateway,'request',request)
    spec=importlib.util.spec_from_file_location('assigned_prior1363',ROOT/'06_TOOLS/EXPERIMENTS/adr_1363/test_assignments.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
    prior.test_actual_api_assignments_repair_and_terminal_failure(tmp_path,term_glossary,monkeypatch,fault)
    assert len(seen)==(1 if fault is None else 2)
