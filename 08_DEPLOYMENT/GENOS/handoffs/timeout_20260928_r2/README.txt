GENOS timeout-sync-20260928-r2 — R1 용어집 캐시 호환 수정

1. generation이 무엇인가
코드서빙이 읽는 원문 DB, navigation/fulltext 검색 색인, 용어집 bundle/cache를 함께 묶은 데이터 폴더입니다.
폴더 바로 아래에 manifest.json이 있습니다. Git commit, ~/DEV 코드 폴더, 코드서빙ID, 모델 이름을 뜻하지 않습니다.
이번 수정에서 새 폴더를 만들거나 원문·검색 색인을 재구축하라는 뜻이 아닙니다.

2. 정확한 경로를 어디서 찾는가
GENOS의 코드 서빙 상세 → 환경 설정에서 GENOS_GENERATION의 실제 값을 복사하세요. 워크플로우 환경 화면이 아닙니다.
GENOS_GENERATION이 없으면 같은 코드서빙 화면의 GENOS_DATA_ROOT 값을 보고, 코드스페이스에서
그 데이터 루트 아래 generations/CURRENT.json을 읽어 JSON의 path 값을 복사하세요.
GENOS_GENERATION이 있으면 CURRENT의 path보다 우선합니다.
코드서빙 컨테이너 로그 event=binding.resolved의 generation_path가 실제 프로세스의 선택 경로입니다.
사진의 /nfs-root/diamo/8-agent/rag-request-reports/...는 로그 저장 경로이므로 generation으로 넣지 마세요.
메일의 /실제/선택/generation은 대체해서 넣을 자리였으며 실제 폴더가 아닙니다.
코드스페이스의 셸 환경은 코드서빙 환경과 자동 공유되지 않습니다. 셸에서 변수값이 비어 있다고 서빙 값도 빈 것은 아닙니다.
현장 실제 경로는 아직 전달받지 못했으므로 이 인계본에 임의 경로를 채우지 않았습니다.

3. 현재 오류의 원인과 R2 수정
사진: glossary compiler/cache binding mismatch → legal-agent internal contract failed → HTTP500.
R1에서 full_glossary.py의 사용되지 않는 옛 FullGlossaryAgent 기본 예산을 수정하면서
기존 캐시 receipt가 고정한 전체 코드 SHA256을 바꿨습니다. 배포 전 기존 캐시와의 호환 검증을 놓쳤습니다.
R2는 이 파일을 변경 전 바이트/해시 ba2c6ced8da72307934e627a7a7508fb29da45e35d09fc3e0a116884a0a5d058로 복구합니다.
현재 v5와 실제 연결된 navigation/document/term/task의 요청 예산1800 및 워크플로우2100은 유지합니다.
옛 FullGlossaryAgent는 현재 Pipeline 구현 선택 경로에 연결되지 않아 옛150 숫자가 현장 요청 시간을 결정하지 않습니다.
엔진 코드 pin은 복구한 파일에 맞춰 갱신합니다. 기존 데이터 manifest, cache receipt, CURRENT의 해시를 덮어쓰지 않습니다.
현장 receipt의 compiler_sha256이 위 해시일 때 기존 데이터 세대를 그대로 사용할 수 있습니다.
다른 해시라면 진단 FAIL이므로 실제 배포 코드/선택 세대를 확인해야 하며 캐시 삭제로 우회하지 마세요.

4. 실행 순서
R1 적용 상태에 R2 ZIP을 적용할 수 있습니다. R1 ZIP/TXT의 반복 실행 대신 이번 R2 ZIP/TXT를 사용하세요.
ZIP과 APPLY.txt를 같은 폴더에 두고: bash 8agent-genos-timeout-sync-20260928-r2_APPLY.txt
기존 ~/DEV 파일 백업 적용 후, 단계2에서 확인한 실제 값을 넣고:
MODE=inspect GENOS_GENERATION='코드서빙에서 복사한 절대경로' bash 8agent-genos-timeout-sync-20260928-r2_APPLY.txt
이 inspect는 모델 호출/캐시 생성 없이 receipt와 코드 해시를 대조합니다.
GLOSSARY_RECEIPT PASS와 GLOSSARY_COMPILER PASS를 확인하고 변경 파일 검토/commit하세요.
MODE=verify GENOS_GENERATION='동일 절대경로' bash 8agent-genos-timeout-sync-20260928-r2_APPLY.txt
verify가 통과한 commit을 push하고 코드서빙 새 리비전에 같은 commit과 같은 generation 경로를 설정하세요.
워크플로우 Python은 R1과 같은 바이트이며 timeout-sync-20260928-r1 / json2100 / stream2100을 유지합니다.
아직 워크플로우 R1이 미적용이면 이번 WORKFLOW_PASTE_ALL.txt 전체 교체/저장/배포도 하세요.
현장 질문/warmup은 워크플로우 테스트 화면에서 실행하세요.

5. 검증/한계
로컬 관련154개 검사 통과. 변경 전 캐시 컴파일러와 같은 해시를 확인하고,1800초 v5+모의 팀 질문HTTP200,
기존 generation manifest/receipt/cache SQLite 불변을 확인했습니다.
R1의 확대검사에서 기존 검색·참조5개 실패를 확인했고 이전시간으로 되돌려도 같았습니다. 해결된 것으로 표시하지 않습니다.
GENOS 실제 receipt/commit/배포 revision/내부 답변/300초500 해소는 현장 확인 전까지 미확인입니다.
원복: MODE=rollback ROLLBACK_FROM=/로그의/백업경로 bash ..._APPLY.txt
원복 대상이 R1이면 그 R1의 캐시 불일치 문제도 다시 나타날 수 있으므로 이전 검증 리비전과 데이터 세대도 함께 보존하세요.
