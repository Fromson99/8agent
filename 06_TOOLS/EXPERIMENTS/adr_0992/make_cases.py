from common import *
cases=[
 {'id':'quorum-complete','question':'운영위원회의 의결 요건을 설명해줘.','originals':['제12조(운영위원회의 의결) 재적위원 과반수의 출석과 출석위원 3분의 2 이상의 찬성으로 의결한다.']},
 {'id':'formula-missing','question':'출장여비를 어떻게 계산하는지 알려줘.','originals':['제7조(출장여비) 출장여비는 제8조의 산식과 별표의 지역별 단가를 적용하여 계산한다.']},
 {'id':'comparison-missing','question':'상시점검과 특별점검의 완료 기한을 비교해줘.','originals':['제21조(상시점검) 상시점검은 착수일부터 7일 이내에 완료한다.']},
 {'id':'explicit-list-missing','question':'개인정보 열람을 제한할 수 있는 사유를 전부 알려줘.','originals':['제6조(열람 제한) 제1호: 다른 사람의 생명이나 신체를 해칠 우려가 있는 경우. 제2호부터 제4호의 사유는 별도 보충규정에 정한다.']},
 {'id':'stale-gap-unneeded','question':'계약 변경 신고기한만 알려줘. 신규 체결은 제외해.','originals':['제14조(계약 변경 신고) 계약을 변경한 자는 변경일부터 7일 이내에 신고하여야 한다.'],
  'old_gap':'신규 계약 체결 유형별 신고 대상 전체가 미확인이다.','previous_claim':'계약 변경 신고기한은 변경일부터 7일 이내다.'}]
gold={c['id']:{'material_required':c['id'] in ('formula-missing','comparison-missing','explicit-list-missing'),'claim_required':c['id'] in ('quorum-complete','comparison-missing','stale-gap-unneeded'),'required_terms':{'quorum-complete':['과반수','3분의 2'],'comparison-missing':['7일'],'stale-gap-unneeded':['7일']}.get(c['id'],[])} for c in cases}
save(ART/'cases.json',cases);save(ART/'grading-only.json',gold)
