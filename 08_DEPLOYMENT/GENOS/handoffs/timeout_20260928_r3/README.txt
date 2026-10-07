GENOS timeout-sync-20260928-r3 — 기존 데이터 자동 확인

ZIP과 APPLY.txt를 같은 폴더에 두고 한 번 실행하세요.
bash 8agent-genos-timeout-sync-20260928-r3_APPLY.txt

기존 ~/DEV 백업/코드 적용 → 기존 데이터 선택값 자동 읽기 → 용어집 receipt/코드 해시 확인
→ generation E2E/verify_assets까지 같은 실행으로 진행합니다. generation 경로를 다시 입력할 필요가 없습니다.
기존 환경, 데이터 manifest/캐시 receipt/CURRENT를 수정하거나 새 데이터 세대를 만들지 않습니다.
R1/R2 적용 상태에도 R3를 적용할 수 있고, 재실행은 이미 적용한 바이트를 확인합니다.

자동 확인 순서
1. 현재 환경의 GENOS_GENERATION, 없으면 GENOS_DATA_ROOT의 CURRENT.
2. 셸에 값이 없으면 기존 ~/DEV/.env의 두 데이터 설정을 사용. 파일 내용을 셸로 실행하지 않으며 다른 키는 출력하지 않음.
3. 값이 없으면 기존 설정 절차의 ~/DEV/01_DATA 또는 ~/DEV/GENOS_DATA/generations/CURRENT.json.
4. CURRENT도 없으면 이전 TRANSFER의 VERIFIED_CHECKOUT.json이 결속한 동일 checkout/data manifest.
환경의 명시 값과 등록 포인터는 우선합니다. 날짜/폴더명으로 최신 데이터 세대를 임의 선택하지 않습니다.
등록 포인터가 서로 다른 세대를 가리키거나 해시가 틀리면 실패하며 검증을 생략하지 않습니다.

코드스페이스와 코드서빙의 설정은 자동 공유되지 않습니다. 서빙 화면에만 설정이 있고 위 자료가 전혀 없으면
CODE_APPLIED / DATA_CHECK_PENDING을 분리해 표시합니다. 코드 적용은 완료되고 기존 서빙 설정은 유지합니다.
확인할 수 없는 세대를 성공으로 표시하지 않습니다. 새 리비전은 기존 설정으로 데이터를 자동 선택하며
워크플로우 테스트 화면의 WARMUP/질문으로 현장 결속을 확인합니다. generation 값을 새로 등록할 필요는 없습니다.

적용 뒤 변경 파일 검토/commit하고 MODE=verify bash ..._APPLY.txt를 실행하면
ZIP/clean commit/자동 선택 데이터의 배포 전 결속 gate를 확인합니다. verify에도 경로 입력은 필요 없습니다.
통과 commit을 push하고 코드서빙 새 리비전에 반영하세요. 기존 generation 환경 설정을 유지하세요.
TXT는 자동 push/서빙 배포를 하지 않습니다.

R2의 캐시 호환 복구(기존 full_glossary.py 바이트), 실제 요청1800/워크플로우2100을 유지합니다.
워크플로우 Python은 R1/R2와 같은 바이트입니다. 이미 반영했다면 추가 교체가 필요 없습니다.
미적용이면 첨부 WORKFLOW_PASTE_ALL.txt를 전체 교체/저장/배포하세요.
워크플로우 WORKFLOW_SETTINGS의 revision은 timeout-sync-20260928-r1입니다.

원복: MODE=rollback ROLLBACK_FROM=/로그의/백업경로 bash ..._APPLY.txt
기존 검증 코드서빙 리비전과 데이터 세대도 보존하세요.
로컬 모의 검증이며 GENOS 실제 배포/내부 질문/300초500 해소는 현장 확인 전까지 미확인입니다.
R1 확대검사의 기존 검색·참조5개 실패는 해결된 것으로 표시하지 않습니다.
