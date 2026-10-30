"""Post-run offline agent review; no product input, model requests or score revision."""
from common import *
import sqlite3
P=ART/'live/cm-007';a=read(P/'audit.json');answer=(P/'answer.txt').read_text();final=read(P/'canonical/009-output.json.gz');initial=read(P/'canonical/008-output.json.gz')
data=ROOT/read(DES/'baseline.json')['release']['data_path']
with sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 def source(sid):return json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0])
 bylaw=source('article:af4d6957c006feaf9b4ed8b9');rule=source('article:ece2450f99b261c5d36eb688')
b97=next(x['text'] for x in bylaw['blocks'] if x['block_id']=='97');b192=next(x['text'] for x in rule['blocks'] if x['block_id']=='192')
def strings(x):
 if isinstance(x,str):yield x
 elif isinstance(x,dict):
  for v in x.values():yield from strings(v)
 elif isinstance(x,list):
  for v in x:yield from strings(v)
input_receipts=[]
for n in (9,10):
 p=P/'raw'/f'call-{n:03d}'/'request.json.gz';raw=read(p);user=json.loads(raw['messages'][1]['content']);vals=list(strings(user))
 input_receipts.append({'physical_call':n,'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bylaw15_paragraph5_exact_in_actual_wire':b97 in vals,'kosdaq13_paragraph5_exact_in_actual_wire':b192 in vals})
assert all(x['bylaw15_paragraph5_exact_in_actual_wire'] and x['kosdaq13_paragraph5_exact_in_actual_wire'] for x in input_receipts)
conditions=[c['rule']['condition_tree'] for c in final['claims'] if c['claim_id']=='C1'];assert any('취득하는 경우' in x for x in strings(conditions))
assert '최근 3년' not in answer and '투자주의 환기종목' not in answer and '관리종목' not in answer
review={'case_id':'cm-007','passed':False,'failure_type':'other: obligation_condition_confusion_and_delegated_detail_omission',
 'reason':'조사 복구는 실제 발동하여 코스닥 시행세칙15 본문 확보·인용을 완료했다. 그러나 최종 C1은 코스닥13(5)의 취득 의무를 취득하는 경우라는 적용 조건에 두었고,15(5)의 6개월 보유 사유는 최종ASSESS 최초·보완 입력에 정확히 있었으나 최종claims와 답변에서 빠졌다. 단순 원문 미확보나 마지막 조립 손실이 아니라 ASSESS 의미 구조화·내용 반영 실패다.',
 'review_method':'Offline Codex review of complete actual answer, initial and repaired ASSESS, frozen source blocks and reference; lexical assertions locate already-reviewed evidence, not a general semantic grader.',
 'criteria':str((DES/'criteria.json').relative_to(ROOT)),'criteria_sha256':sha(DES/'criteria.json'),
 'answer_sha256':sha(P/'answer.txt'),'initial_assessment_sha256':sha(P/'canonical/008-output.json.gz'),'repaired_assessment_sha256':sha(P/'canonical/009-output.json.gz'),
 'input_receipts':input_receipts,
 'findings':[{'id':'acquisition_obligation','passed':False,'source_id':rule['id'],'block_id':'192','source_text_sha256':rule['text_sha256'],'actual_condition':conditions[0],
 'explanation':'원문은 정해진 기한·가격·수량으로 취득하여 보유하도록 의무를 부과한다. 최종C1은 이행행위를 적용 전제로 분류하고 norms는 보유 중심으로 남겼다. C3의 취득방법·시기 의무를 읽어도 C1의 잘못된 조건 분류가 해소되지 않는다.'},
 {'id':'delegated_six_month_cause','passed':False,'source_id':bylaw['id'],'block_id':'97','source_text_sha256':bylaw['text_sha256'],
 'explanation':'15(5)의 최근3년 주선/상장후2년/투자주의환기·관리종목·상장폐지사유가 모두 입력되었지만 최종문장은 세칙으로 정하는 사유로만 남았다. 최초·보완 ASSESS 모두 이 세부 내용 누락.'},
 {'id':'recovery_original','passed':True,'explanation':'실제 모순 감독 지시 거절→독립RESEARCH 실행→두번째 감독REDIRECT READ→15본문 확보·최종인용.'},
 {'id':'both_markets_quantities_caps_durations','passed':True,'explanation':'코스닥 기업유형별3/5%,10/25/50억원,3/6개월·1년; 유가 외국주권등5%/50억원/6개월 보존. 세부 사유 누락은 별도 실패.'},
 {'id':'scope_classification_and_disposal_denominators','passed':True,'explanation':'국내소재외국지주회사 포함/제외, 유가 국내·예비심사신청후, 최초취득주식 월별5% 분모 보존.'},
 {'id':'acquisition_detail_and_exceptions','passed':True,'explanation':'15(4)의 사모/취득기간/미인수잔량 산입 반영. 코스닥 적용하지 않을 수 있다 재량과 대형법인 제외, 유가 적격해외시장3년 예외 반영.'},
 {'id':'final_server_content_preservation','passed':True,'explanation':'accepted-content-v1 전체claims 보존·추가COMPOSE모델0. 내용 손실은 최종 조립보다 앞 단계에 있다.'}],
 'reference_answer_used_in_product':False,'new_model_calls':0,'in_sample':True,'quality_certified':False,
 'followup_cm009':'Not run: CM007 full frozen content gate failed; no same-case automatic retry.'}
put(P/'content-review.json',review)
print(review['reason'])
