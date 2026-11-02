"""Offline evidence inspection of the completed actual responses, no dispatch."""
from common import *
P=ART/'live/review-whatif'
rows=[]
for label,expected in [('low','TRUE'),('high','FALSE'),('rule','TRUE')]:
 response=read(P/f'semantic-{label}-response.json.gz');b=response['body'];meta=b['assembly']['term_agent'];ctx=meta['scenario_context'];view=meta['review_explanation']
 proposal_records=[]
 for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=read(p)['view'];scenario=v.get('hypothetical_scenario')
  if not scenario or scenario['scenario_id']!=ctx['scenario_id']:continue
  op=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
  if not op.exists():continue
  o=read(op);receipt=o.get('scenario_review') or {}
  proposal_records.append({'path':str(op.relative_to(ROOT)),'current_facts':v['current_facts'],'user_fact_sources':v['user_fact_sources'],
   'context_hash_expected':scenario['content_sha256'],'context_hash_received':receipt.get('context_hash'),
   'copied_baseline_hash':receipt.get('context_hash')==scenario['baseline_hash'],
   'review':receipt,'application_explanations':[c.get('explanation') for c in o['claims'] if c.get('explanation')],
   'semantic_repair_feedback':v.get('repair_feedback',{}).get('validation') if v.get('repair_feedback') else None})
 observations={
  'low':'두 제안 모두735000원 금액 충족·승인 미확인·개시 미확정을 설명했으나 가정 해시 대신 baseline_hash를 반복 제출. 두 번 거절 후 원문만 반환. 의미가 맞는 제안과 최종 저장 성공을 구분한다.',
  'high':'실제 최종5주장. 변경된1725000원으로 금액 불충족, 승인 별도 미확인, 긴급 예외 미적용, 개시 불가를 설명. 가정임을 명시하고 원래1380000원을 현재값으로 재사용하지 않음.',
  'rule':'두 제안 모두 구조화 N2=TRUE/N3=UNKNOWN/UNCONFIRMED지만 설명은 원래1000000원 한도로1380000원 금액 불충족·개시 불가를 주장. 가정 한도2450000원을 설명에 적용하지 않음. 가정 검증기는 이 의미 모순을 잡지 못했고 별도의 SCOPE_CLAIM_EVIDENCE/NEED_CLAIM_LINK 검증에서 거절됨. 최종원문만/주장0이므로 오답이 발행되지는 않았으나 규칙 가정 의미 검증 실패는 미해결.'}
 rows.append({'label':label,'http_status':response['status'],'claims':len(b['answer']['claims']),'expected_cost_condition':expected,
  'actual_typed_conditions':[(r['node_id'],r['result']['status']) for r in ctx['evaluations']],
  'final_receipt':view.get('scenario_review'),'failed_checks':view['failed_checks'],'semantic_and_publication_pass':label=='high',
  'observation':observations[label],'proposals':proposal_records})
put(P/'semantic-review.json',{'method':'Recorded exact model proposals and final native API responses inspected offline by coding agent; no external judge','all_passed':False,'passed':1,'total':3,'rows':rows,
 'followup_required':['Let host bind immutable scenario identity instead of asking model to reproduce a hash; preserve contextual integrity checks','Bind rule-assumption application claims to changed conditions; copying condition_results is insufficient to verify prose semantics'],
 'not_a_quality_certificate':True})
print('Actual branch success 1/3; failed branches and original proposals preserved')
