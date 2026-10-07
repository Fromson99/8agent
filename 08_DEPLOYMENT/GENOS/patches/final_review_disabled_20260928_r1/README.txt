GENOS 최종 답변 검토 OFF R1 (2026-09-28)
이 메일의 GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt를 사용하세요.
기존 ~/DEV Git checkout에 변경 파일 5개만 백업 후 적용하며 엔진/프로필 pin을 함께 갱신합니다.
현장에 이미 적용한 시간 설정·팀 로그·thinking·fulltext 진단 파일은 교체하지 않습니다.
메일 ZIP과 TXT를 같은 폴더에 저장하고 아래를 실행합니다.

bash GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt

기본 대상: ~/DEV. 다른 checkout이면 DEPLOY_ROOT=/실제/checkout 을 앞에 붙입니다.
로그의 BACKUP_READY 경로와 TRANSFER/final-review-disabled-20260928-r1/ 영수증을 보존하세요.
CHECK_PASS/APPLIED는 코드 적용 상태이며 배포 성공이 아닙니다.
지원된 변경 전/후 파일 해시만 허용합니다. 미지원 파일이나 기존 pin 불일치는 쓰기 전에 중단합니다.
중단한 경우 강제 덮어쓰지 말고 로그를 전달하세요.

적용 후 git diff와 changed_files를 확인해 해당 코드와 엔진/프로필/PIPELINE 파일만 commit합니다.
이 TXT는 자동 git add, commit, push, 플랫폼 배포를 하지 않습니다.
commit 후 MODE=verify bash GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt 를 실행합니다.
기존 설정/CURRENT에서 선택 generation을 확인해 같은 checkout에서 generation E2E/verify_assets를 실행합니다.
기존 설정을 찾지 못하면 GENOS_GENERATION=/실제/선택/generation 을 명시합니다. 새 generation 생성은 없습니다.
그 commit을 push하고 코드서빙 새 리비전이 같은 commit/generation을 선택하게 합니다.
워크플로우 Python 교체는 필요 없습니다. 확인은 워크플로우 테스트 화면의 새 질문으로 합니다.
응답 기록: final_review_policy=disabled, final_review_status=SKIPPED, claim_review_status=UNREVIEWED.
source-omission-review는 원문 선별 단계로 유지되며 최종 답변 검토만 꺼집니다.

원복: MODE=rollback ROLLBACK_FROM=/BACKUP_READY의/실제/경로 bash GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt
원복 후 이전 commit/코드서빙 리비전 선택도 별도로 처리합니다.
로컬 MAIN 계약·회귀 312개 통과. 현장 적용/배포/실제 속도는 미확인입니다.
