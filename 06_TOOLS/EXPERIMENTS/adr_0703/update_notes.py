"""Update live status only after exact selected-code/service verification."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout';m=json.loads((A/'artifacts/main-completion.json').read_text());assert m['status']=='local-main-verified';p=m['pointer'];release=p['release_id'];g=p['generation'];report='04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout/MAIN_RESULT.md'
a=R/'AGENTS.md';s=a.read_text();old='`native-cm-serving-20261008-r1`(포인터 generation 46)';assert old in s;s=s.replace(old,f'`{release}`(포인터 generation {g})',1);a.write_text(s)
a=R/'00_SYSTEM/ARCHITECTURE.md';s=a.read_text();old='2026-10-08 현재 로컬 RAG MAIN은';assert old in s
intro=f'2026-10-09 현재 로컬 RAG MAIN은 `{release}`(포인터 generation **{g}**)이다. MAIN46의 원문·색인·폴더 세대를 보존하면서 구조 우선 검색 → 선택한 문서/하위 구조 안의 본문 검색, 승인 판단·조건/예외 계약, 선택 범위 묶음 읽기·재개, 로그와 공개 표시 분리를 통합했다. 새 공개3문항과 알려진2회귀를 동일 코드로 검증했고 작업·검증 후보·선택 릴리스의 서빙284파일 해시와 실제 `service.service` HEALTH/RAG_SEARCH binding을 확인했다. 전체 MAIN의 상위 단계와 GENOS 현장 배포는 별도다. [검증·실제 선택·롤백](../{report}).\n\n'
s=s.replace(old,intro+'2026-10-08 전환 당시 로컬 RAG MAIN은',1);a.write_text(s)
a=R/'07_DOCS/REFERENCE/REPORTS/RAG_JUDGMENT_ERROR_ACTION_DESIGN_20261008.md';lines=a.read_text().splitlines()
for i,line in enumerate(lines):
 if line.startswith('> 구현 진행:'):lines[i]=f'> 구현 결과(2026-10-09): ADR-0693~0702의 선별 구현을 ADR-0703에서 같은 코드로 검증하고 로컬 MAIN{g} `{release}`에 반영했다. 실패0695/0697/0701과 미실행0699는 보존했다. [변경·검증·실제 서비스 선택·롤백](../../../{report}). 이하 본문은 작성 당시의 설계 기준이다. GENOS 현장 적용은 별도다.'
a.write_text('\n'.join(lines)+'\n')
a=R/'07_DOCS/BACKLOG.md';s=a.read_text();first=s.index('## BL-006');prefix=s[:first];tail=s[first:]
oldstates=[x for x in tail.splitlines() if x.startswith('- 상태:')];assert len(oldstates)>=3
updates=[f'- 상태: ADR-0703 동일 코드 검증 및 로컬 MAIN{g} 반영 완료. 새 공개3/3·기존 회귀2/2, 필수 작업 계약 전부 통과. GENOS 현장 미반영. [실제 선택·롤백](../{report})',f'- 상태: 채팅·진행 카드·SSE·저장 표시의 공개 경계를 로컬 MAIN{g}에 반영. 전체 오류는 로그 보존, 최종 실패는 안내·조회 번호만 표시. 실제 모델 실패와 계약검사에서 상세 노출0 확인. GENOS 현장 미반영.',f'- 상태: 구조 우선·명시 문서 결속·범위 내 본문 검색·선택 범위 묶음 읽기·재개를 로컬 MAIN{g}에 반영. ADR-0697 독립 비교와 ADR-0703 최종 전체 비교를 별도 보존. 비용·지연의 일반 개선을 보장하지 않음.']
for old,new in zip(oldstates[:3],updates):tail=tail.replace(old,new,1)
lines=tail.splitlines()
for i,l in enumerate(lines):
 if l.startswith('- 현재 할 일:'):lines[i]='- 완료 범위: 필요한 후보 변경만 현재 작업 경로에 통합하고, 승인 판단 revision·부족별 실제 해결·공통 claim·조건/예외 구조 및 동일 코드의 실제 서비스 선택을 확인했다. 세부 의미 일반화와 운영 관찰은 후속 과제다.'
 if l.startswith('- 남은 개선:'):lines[i]='- 남은 개선: 적용 조건과 이행 의무·예외의 의미 분리, 여러 대안을 한 조건에 묶는 표현, 공통 판단과 상세의 중복 서술을 후속 독립 사례로 검증한다. 0695/0697/0701 실패를 보존하며 예외 목록/상태의 모순은 0702에서 형식으로 결속했다. 원문 읽기는 BL-008, 표시 분리는 BL-007을 따른다.'
a.write_text(prefix+'\n'.join(lines)+'\n');print('Live status notes updated:',release,g)
