from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0838-comparison-judgment-qualification'
v=json.loads((A/'MAIN_RESULT.json').read_text());assert v['status']=='PASS' and v['active_pointer']['generation']==79
p=R/'AGENTS.md';s=p.read_text();s=s.replace('`comparison-task-guidance-20261016-r1`(포인터 generation 77)','`llm-comparison-judgment-20261016-r1`(포인터 generation 79)')
heading='### 대사 의미 판단 — 사용자 지시 2026-10-16'
if heading not in s:
 anchor='## 데이터와 법률 근거'
 section=heading+'\n\n- 비교의 충분성·적용성·예외·차이·충돌은 LLM이 원문을 보고 판단한다. 사용자가 결과를 검토하고 수정을 요청할 수 있게 의견·이유·인용·미확보 내용을 함께 보여준다.\n- 미확보 설명, 표현 차이, 의미 상태값 조합, 수치 차원 목록 미완성만으로 결과를 버리거나 반복 수정시키지 않는다. 모델에게 위치·근거 ID·도구명·중복 상태를 재작성시키지 않고 시스템이 확정 가능한 값은 조립한다.\n- 실제 선택한 인용의 원문 일치, 내규·외규 구분, 문서 접근권한, 코드·데이터·상태 해시와 재개·중복·예산 검사는 유지한다. LLM 의견을 검증된 법률 정답이나 원문 부재의 증명으로 승격하지 않는다.\n\n'
 assert anchor in s;s=s.replace(anchor,section+anchor,1)
p.write_text(s)
text='2026-10-16 현행 로컬 RAG 서빙은 **MAIN79 `llm-comparison-judgment-20261016-r1` / workflow 1.5.2**다. 비교의 의미 판단은 LLM에 맡기고, 미확보 설명·표현 차이·수치 차원 목록과 메타데이터의 부족을 이유로 비교 전체를 거절하던 검사를 줄였다. 위치에 따른 도구·근거 연결은 시스템이 조립하고 실제 인용·권한·해시·상태 보존은 검사한다. 후보와 선택342파일 동일, 작업 회귀53개·기술 상태84개·활성 서비스13개를 확인했다. 알려진 원문 묶음의 새 모델 응답1건을 보존했으며, 전체 대사 품질·검색 범위 문제는 미검증/미해결이다. GENOS 미반영.'
for name,link in [('00_SYSTEM/ARCHITECTURE.md','../09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/LLM_JUDGMENT_MAIN79.txt'),('07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md','../../../09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/LLM_JUDGMENT_MAIN79.txt')]:
 p=R/name;s=p.read_text();s=s.replace('2026-10-16 현행 로컬 RAG 서빙은 **MAIN77','2026-10-16 이전 로컬 RAG 서빙 **MAIN77',1)
 first,rest=s.split('\n',1);s=first+'\n\n'+text+' [반영·검증·한계·원복]('+link+').\n'+rest
 if name.endswith('RISK_TEAM_COMPARE_WORKFLOW.md'):
  s=s.replace('"workflow_version": "1.1.0"','"workflow_version": "1.5.2"')
  s=s.replace('문서 JSON의 검증된 `workflow_version`과 명시한 기준일이 일치해야 적용 여부를 확정한다. 반입 과정에서 유효성을 임의 승인하지 않으며 판본 정보가 없으면 판정을 보류한다.','선택 판본과 기준일 정보를 모델에 제공한다. 판본 유효성은 임의 승인하지 않으며, 정보 부족은 모델의 이유·미확인 사항에 남긴다. 판본 메타데이터가 없다는 이유만으로 비교 호출을 막지 않는다.')
  s=s.replace('직접 인용, 상위 내규를 거친 연속 경로, 내용 대응, 미확인, 무관을 구분한다. 직접·간접 관계의 연결은 읽은 원문의 정확한 인용과 대상 문서명으로 검증한다. 중간 문서의 판본·원문 범위도 확인한다. 내용 유사성만으로 제정 근거를 확정하지 않는다. 이미 관계가 확인된 상충은 상충으로 보고하고 부합할 때까지 검색하지 않는다.','직접 인용, 상위 내규를 거친 경로, 내용 대응, 미확인, 무관은 LLM이 판단한다. 시스템은 선택한 원문 ID·인용·내외규 구분을 검사한다. 명시 근거 관계·적용성·판본·원문 완전성은 판단 맥락이며 기계적인 비교 허용 조건이 아니다. 내용상 대응해도 비교할 수 있고, 제정 근거 확정과 내용 비교는 구분해서 설명한다. 이미 판단한 상충이 부합으로 바뀔 때까지 재검색하지 않는다.')
  s=s.replace('수치 항목은 정의·분자·분모·대상·단위·주기·시점·예외·방향의 양측 근거를 요구한다. 기준 수치나 산식이 없으면 “현재 확보한 내규에서 수치 기준 미확인”으로 남긴다. 미확보 원문과 사용자가 답해야 할 사실은 별도로 기록한다.','수치 항목은 이번 판단에 필요한 정의·분자·분모·단위·기간·예외 등을 LLM이 선택해 검토한다. 전체 차원을 반드시 채우도록 요구하지 않는다. 기준 수치나 산식이 미확보이면 그 내용을 남기며 규정 자체가 없다고 단정하지 않는다. 항목 상태와 설명은 LLM 의견이고, 인용이 없는 내용에는 근거 미선택 표시를 붙인다. 미확보 원문과 사용자 사실 부족은 구분한다.')
  s=s.replace('의미 판단 수정은 같은 단계·근거에서 최대 1회이며 물리 호출은 기존 gateway의 총 예산에 포함한다.','잘못된 형식·인용·조사 위치의 수정은 같은 단계·근거에서 최대 1회이며 물리 호출은 기존 gateway의 총 예산에 포함한다. 의미 상태값 조합과 누락 설명만으로 수정 호출하지 않는다.')
 p.write_text(s)
print('Current status and LLM judgment operating policy documented')
