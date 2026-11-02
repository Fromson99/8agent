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
  'low':'최초/보완 모두735000원 금액충족·승인 미확인·개시 미확정으로 설명했다. 가정 해시는 서버에서 정상 결속. 그러나 material MISSING_FACT gap을 requirement_review에서는 SATISFIED/gap_indices=[]로 두어 REQUIREMENT_GAP_COVERAGE가 반복되고 최종 주장0/원문응답. 실제 reason에서 gap1 문구를45/34회 반복해 각각600자에 도달한 점은 wire audit에 보존했다.',
  'high':'실제 최종5주장. 변경1725000원 금액불충족, 승인 별도 미확인, 일반작업에 긴급예외 미적용, 개시불가. 가정 해시 결속과 재조회 통과.',
  'rule':'최초/보완 모두 조건표 N2=TRUE/N3=UNKNOWN을 제출했지만 적용 설명은 원래1000000원 한도로1380000원 금액불충족을 주장했다. 새 가정 검증기가 SCENARIO_CHANGED_VALUE_MISSING/SUPERSEDED_RULE/APPLICATION_LINK로 직접 거절했다. 오답 채택 차단은 확인됐으나 실제 가정 답변 생성은 미통과.'}
 rows.append({'label':label,'http_status':response['status'],'claims':len(b['answer']['claims']),'expected_cost_condition':expected,
  'actual_typed_conditions':[(r['node_id'],r['result']['status']) for r in ctx['evaluations']],
  'final_receipt':view.get('scenario_review'),'failed_checks':view['failed_checks'],'semantic_and_publication_pass':label=='high',
  'observation':observations[label],'proposals':proposal_records})
put(P/'semantic-review.json',{'method':'Recorded exact model proposals and final native API responses inspected offline by coding agent; no external judge','all_passed':False,'passed':1,'total':3,'rows':rows,
 'followup_required':['One authoritative current-case projection with historical references; do not repeat old case as current issue text','Host retains deterministic evaluation and fixed metadata; model supplies semantic application links only','Consolidate repeated review edges and clarify request satisfaction versus case-outcome uncertainty','Replace spelling/old-number bans with typed role-aware assertions; keep source and authority checks','Emit precise expected fields/values/claim IDs in repair diagnostics'],
 'not_a_quality_certificate':True})
print('Actual branch success 1/3; failed branches and original proposals preserved')
