GENOS financial/risk 공통 법규 이관 r2 (2026-09-30)

범위: 사진의 financial_team 문서 61개. 기존 risk_team과 겹치는 문서 및 RAW 공유 파일 쌍을 financial_team으로 해시 검증 복사합니다. 개수는 현장 등록표에서 확인합니다. 로컬 기준 겹침은 19개 문서·150쌍이며
기존 financial_team 문서는 유지합니다. RAW/union_file/manifest.json은 정확히 같은
파일의 양쪽 경로, SHA-256, 권한/출처를 고정합니다.

기존 GENOS 세대의 61개 문서 버전과 source_block이 모두 있어야 합니다. 하나라도
없으면 누락 문서명을 출력하고 중단합니다. 기존 세대는 절대 수정하지 않습니다.
새 세대에는 동일한 문서 ID와 구조화 원문을 보존하고 document 위치 메타데이터에
financial_team을 추가합니다. navigation.sqlite와 fulltext.sqlite의 바이트 및
해시를 유지하며 결속 manifest만 새 store 해시로 갱신합니다. 색인 행을 복제하지
않습니다. 두 팀은 같은 문서/색인 행을 팀 선택 메타데이터로 함께 사용합니다.

실행: ZIP과 APPLY.txt를 같은 위치에 둡니다. GENOS 코드스페이스에서 다음
변수를 실제 값으로 설정해 bash APPLY.txt를 실행합니다.
  DEPLOY_ROOT=~/DEV
  GENOS_DATA_ROOT=<해당 환경의 실제 01_DATA 절대경로>
  GENOS_SOURCE_GENERATION=<현재 risk 세대의 generation 절대경로>
  GENOS_OUTPUT_ROOT=<새 불변 세대 패키지를 둘 기존 NFS 디렉터리>

실행 TXT는 먼저 지속 로그를 시작하고 ZIP 해시/목록, 기존 checkout의 변경
대상 코드 해시를 검사합니다. 기존 파일과 예상 기준이 다르면 덮어쓰지 않고
중단합니다. 맞으면 백업 후 checkout에 패치를 반영합니다. RAW 복사/등록,
union_file 생성, 새 세대 복제/메타데이터 결속/전체 자산 검증을 수행합니다.
출력된 새 GENOS_GENERATION과 migration-receipt.json을 보존하세요.

이후 코드 checkout 변경을 검토·커밋하고, 그 checkout에서
genos_generation_e2e.py 및 genos_release_gate.py를 새 generation 대상으로
실행합니다. PASS 후 같은 commit을 push하고 새 코드서빙 리비전에 출력된
GENOS_GENERATION 절대경로를 설정합니다. 실제 질문/원문 조회는 워크플로우
테스트 화면에서 확인합니다. Git push, 코드서빙 리비전, 현장 질의는 이 TXT가
자동 수행하지 않으며 각 결과를 별도로 기록해야 합니다.

기존 source generation 및 코드 백업은 롤백 시 보존됩니다. RAW 원본과 기존
완료 세대는 삭제하지 않습니다. 외부 로컬 검증은 현장 배포 완료 증거가 아닙니다.
