from copy import deepcopy
from pathlib import Path
import gzip,json
import pytest
from semantic_runtime.legal_agent import completion_v6 as v6,completion_v5 as v5
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from test_source_span_norm import proposal,accepted

@pytest.mark.parametrize('obligation',['보고하여야 하되','보고해야 하되','허가를 받아야 하되'])
@pytest.mark.parametrize('tail',['정해진 서식을 쓴다.','신고로 갈음할 수 있다.'])
def test_connective_obligation_and_mixed_permission_are_distinguished(obligation,tail):
    quote=obligation+', '+tail
    expected='UNSPECIFIED' if '수 있다' in tail else 'OBLIGATION'
    assert v6.source_modality(quote)==expected

@pytest.mark.parametrize('order',['obligation_first','permission_first'])
def test_mixed_source_keeps_both_selected_effects_without_host_label_rewrite(order):
    obligation='보고서를 45일 이내에 제출하여야 한다.'
    permission='연결 기준이면 60일 이내에 제출할 수 있다.'
    quote='보고서를 45일 이내에 제출하여야 하되, 연결 기준이면 60일 이내에 제출할 수 있다.'
    if order=='permission_first':quote='연결 기준이면 60일 이내에 제출할 수 있다. 보고서를 45일 이내에 제출하여야 하되, 서식은 별도로 정한다.'
    p=proposal(obligation,'OBLIGATION');second=deepcopy(p['claims'][0]);second['claim_id']='C2'
    second['rule']['norms'][0].update(kind='PERMISSION',text=permission);p['claims'].append(second)
    before=deepcopy(p);out=accepted(p,[{'id':'S1','source_id':'s','text':quote}])
    norms=[c['answer_content']['rule']['norms'][0] for c in out['claims']]
    assert [n['kind'] for n in norms]==['OBLIGATION','PERMISSION']
    assert [n['text'] for n in norms]==[obligation,permission]
    assert all(n['source_quote']==quote for n in norms)
    assert out['model_proposal']['norm_label_corrections']==[] and p==before
    for claim in out['claims']:v5.verify_content(claim)

def test_actual_cm033_original_no_longer_rejects_correct_45day_obligation():
    R=Path(__file__).resolve().parents[3]
    path=R/'04_EXPERIMENTS/ADR/ADR-0893-reference-delivery-continuity/artifacts/run-001/cm-033/canonical/019.json.gz'
    view=json.loads(gzip.decompress(path.read_bytes()))['view']
    source=next(o for o in view['evidence_options'] if o['id']=='Sf27d71109b5982c0a2d4b5569763')
    assert '제출하여야 하되' in source['text'] and '60일 이내에 제출할 수 있다' in source['text']
    assert v6.source_modality(source['text'])=='UNSPECIFIED'
    p=proposal('사업보고서 제출대상법인은 반기·분기보고서를 해당 기간 경과 후 45일 이내에 제출하여야 한다.','OBLIGATION')
    out=accepted(p,[{'id':'S1','source_id':source['source_id'],'text':source['text']}])
    assert out['claims'][0]['answer_content']['rule']['norms'][0]['kind']=='OBLIGATION'
    assert out['model_proposal']['norm_label_corrections']==[]

@pytest.mark.parametrize('source,wrong',[
    ('보고하여야 하되, 정해진 서식을 쓴다.','보고할 수 있다.'),
    ('보고할 수 있다.','보고하여야 한다.'),
    ('양도하여서는 아니 된다.','양도할 수 있다.')])
def test_unambiguous_opposite_wording_still_rejected(source,wrong):
    with pytest.raises(ProposalError,match='wording reverses'):
        accepted(proposal(wrong,'UNSPECIFIED'),[{'id':'S1','source_id':'s','text':source}])

@pytest.mark.parametrize('quote',['보고하여야 하되 의무가 없는 경우는 제외한다.','보고하여야 하는 것은 아니다.'])
def test_negative_or_uncertain_effect_is_not_promoted_to_obligation(quote):
    assert v6.source_modality(quote)=='UNSPECIFIED'

def test_mixed_modality_does_not_relax_exact_receipt_integrity():
    quote='보고하여야 하되, 신고로 갈음할 수 있다.'
    out=accepted(proposal('신고로 갈음할 수 있다.'),[{'id':'S1','source_id':'s','text':quote}])
    bad=deepcopy(out['claims'][0]);bad['span_receipts'][0]['text']='변조'
    with pytest.raises(ContractError,match='receipt'):v5.verify_content(bad)
