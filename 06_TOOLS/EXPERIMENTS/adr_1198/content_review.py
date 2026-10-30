"""Offline evidence review only. No product correction or external judge request."""
from common import *
import sqlite3

P = ART/'live/cm-007'
a = read(P/'audit.json')
assessment = a['assessments'][-1]['payload']
claim = assessment['claims'][0]
rule = claim['answer_content']['rule']
answer = (P/'answer.txt').read_text()
supervisor = next(iter(read(P/'investigation-state.json')['investigation_supervisor'].values()))
proposal = read(P/'canonical/004-output.json.gz')
original_proposal = read(P/'canonical/004.json.gz')['view']['proposed_action']
nav = sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro', uri=True)
def source(sid):
    return json.loads(nav.execute('select json from source where id=?', (sid,)).fetchone()[0])
original = source('article:ece2450f99b261c5d36eb688')
delegated = source('article:af4d6957c006feaf9b4ed8b9')
nav.close()
source_quote = next(b['text'] for b in original['blocks'] if b['block_id']=='192')
assert '取' not in source_quote and '취득하여' in source_quote and '보유하여야 한다' in source_quote
assert rule['condition_tree']['text'].endswith('취득하는 경우')
assert claim['text'] in answer
assert delegated['id'] not in a['read_source_ids']
assert proposal['directive']=='CONTINUE_TARGETED' and proposal['action']['choice']=='RESEARCH'
assert original_proposal['choice']=='FINISH' and proposal['source_targets']==[]
assert supervisor['failure']['reason']=='CONTINUE_TARGETED must retain the exact proposed action'
generations=[]
for n, physical in ((5,6),(6,7)):
    p=P/f'canonical/{n:03d}-output.json.gz'
    raw=read(p)['claims'][0]
    condition=raw['rule']['condition_tree']['leaves'][0]['text']
    assert condition==rule['condition_tree']['text']
    request=P/f'raw/call-{physical:03d}/request.json.gz'
    user=read(request)['messages'][1]['content']
    assert '취득하여 다음 각 호에서 정하는 기간까지 보유하여야 한다' in user
    generations.append({'canonical_generation':n,'physical_call':physical,'condition':condition,
        'original_acquisition_duty_in_input':True,'path':str(p.relative_to(ROOT)),
        'sha256':sha(p),'request_sha256':sha(request)})
checks={
    'both_market_article13_acquired_and_cited': all(s in a['read_source_ids'] and s in a['published_source_ids'] for s in (original['id'],'article:2fb3a39c3796bcda1905733a')),
    'foreign_holding_classification_preserved': '국내소재외국지주회사 제외' in answer and '국내소재외국지주회사 포함' in answer,
    'monthly_disposal_initial_acquisition_denominator_preserved':answer.count('최초에 취득한 주식의 100분의 5')==3,
    'kospi_domestic_post_application_scope_preserved':'상장예비심사신청 후에 국내에서 모집·매출한' in answer,
    'quantity_caps_and_base_holding_periods_match_read_originals':True,
    'article13_exemption_discretion_and_exclusions_preserved':True,
    'kosdaq_acquisition_duty_not_reclassified_as_condition':False,
    'delegated_quantity_and_extended_holding_terms_complete':False,
    'all_accepted_claim_text_preserved':read(P/'composition-audit.json')['passed'],
    'no_generic_unread_footer':'확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.' not in answer,
}
reason=('최종 조립은 accepted C1·C2를 모두 그대로 보존했으며 이전의 국내소재외국지주회사 분류·최초취득 분모 누락은 재현되지 않았다. '
        '그러나 최초 ASSESS와 보완 ASSESS 모두 코스닥 제13조제5항의 기한 내 취득·보유 의무를 조건 트리의 “취득하는 경우”로 바꾸고 의무에는 보유만 기록했다. '
        '해당 원문은 두 입력에 실제 존재했으므로 이 부분은 ASSESS 의미 분류 오류다. '
        '별도로 감독은 FINISH를 RESEARCH로 변경하면서 CONTINUE_TARGETED를 보내 정확한 행동 유지 계약에 거절됐고, source_targets=[]여서 세칙15가 목표로 등록되지 않은 채 확보 원문 답변으로 넘어갔다. '
        '코스닥 시행세칙15의 미인수 잔량 포함 기준과 혁신기술기업 6개월 보유의 구체 사유도 미확보·최종 누락이다. 내용 기준 미통과로009는 실행하지 않는다.')
review={'case_id':'cm-007','passed':False,'failure_type':'other: assessment_modality_and_delegated_scope_incomplete',
    'content_evaluated':True,'model_claim_content_passed':False,'visible_answer_consistency_passed':True,
    'transport_completion_passed':True,'final_composition_loss':False,
    'previous_domestic_post_application_omission_reproduced':False,
    'previous_foreign_holding_classification_omission_reproduced':False,
    'generic_limitation_removed':True,'originals_and_final_input_complete':False,
    'reference_answer_used_in_product':False,'new_model_calls':0,'checks':checks,'reason':reason,
    'assessment_failure':{'source_id':original['id'],'block_id':'192','original_quote':source_quote,
        'source_text_sha256':original['text_sha256'],'accepted_condition':rule['condition_tree'],
        'accepted_norms':rule['norms'],'generations':generations},
    'supervisor_failure':{'failure':supervisor['failure'],'stop_reason':assessment['stop_reason'],
        'proposed_choice':original_proposal['choice'],'directive':proposal['directive'],
        'replacement_action':proposal['action'],'source_targets':proposal['source_targets'],
        'registered_source_goals':[{'document_id':g['document_id'],'coordinate':g['coordinate'],'status':g['status']} for g in supervisor['source_goals']],
        'missing_original':{'source_id':delegated['id'],'coordinate':delegated['article_coordinate'],
            'source_text_sha256':delegated['text_sha256'],'text':delegated['text']},
        'product_input_injected_by_audit':False},
    'scope':'Offline comparison with frozen source version. No current-law or general legal quality certification.',
    'answer_sha256':sha(P/'answer.txt')}
put(P/'content-review.json',review)
print(json.dumps({'passed':review['passed'],'checks':checks,'reason':reason},ensure_ascii=False))
