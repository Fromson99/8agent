# 조사 제어 통합 R2: GENOS 반입·문항별 결과

현재 로컬 MAIN `investigation-control-v6-20261007-r1` / 포인터 generation 43의 검증한 서빙 265파일을 그대로 반입한다. 설치기·배포 게이트·운영 문서와 게이트 의존성 17파일을 더한 ZIP은 282파일과 CODE_MANIFEST를 포함하며 약 1.35MB다. 원문/DB/환경 키/JavaScript는 포함하지 않는다. 기존 compact reader·AD·shortcut·wiki·SQL·NFS 경로와 선택 generation을 유지한다.

독립 질문 32개는 자동 세부 정답 23개, 판단 오류 3개, 미답변 6개다. 회귀 8개는 7개 정상 응답이며 별도 정답률로 재해석하지 않는다. 자동 평가 이유 일부의 불일치는 원판정 보존 상태로 보고서에 적었다. 준비부터 실험 최종 검증까지 1시간 31분 6초, 실제 MAIN 서비스 성공까지 1시간 40분 56초다. 독립 질의 처리 중앙값 2분 21초, p95 6분 39초, 실제 MAIN 확인 질의는 3분 45초다. GENOS 내부 모델 시간은 미측정이다.

- [40문항 실제 답변·판정·문제·시간](EXPERIMENT_RESULTS_UTF8.txt)
- [결과 원문 해시와 집계](RESULTS_REVIEW.json)
- [이전 통합·수정 실험을 포함한 전체 경과 4시간 45분](TOTAL_TIMELINE_UTF8.txt)
- [현장 반입·검증·push·리비전·워크플로우·원복](GUIDE_UTF8.txt)
- [배포 파일 검증 영수증](DELIVERY_VALIDATION.json)
- [모의 반입 검사 7개](DELIVERY_TESTS.log)
- [코드 ZIP](GENOS_INVESTIGATION_CONTROL_20261007_R2.zip)
- [별도 Bash 실행 TXT](GENOS_INVESTIGATION_CONTROL_20261007_R2_APPLY.txt)
- [워크플로우 편집기 전체 코드](GENOS_INVESTIGATION_CONTROL_20261007_R2_WORKFLOW_PASTE_ALL.txt)

코드/캐시/ZIP 변조 차단, 기존 checkout 별칭에서 적용·재실행·원복, 원문/상태 보존, 작은 모의 generation의 실제 checkout E2E·verify_assets·release gate, 로컬 bare Git remote push와 재실행을 확인했다. Python 서빙 3.11·워크플로우 3.10 문법을 확인했고 모델 호출은 없었다. 종료한 합성 검사 디렉터리는 검증 영수증·로그를 남기고 제거했다.

미발송 R1에서 배포 게이트가 테스트 지원 트리의 `term_serving_bundle` 의존성을 빌렸던 문제를 실제 고립 checkout 검사로 발견했다. R2에 기존 검증 지원 코드와 같은 의존성 13파일을 포함했으며 서비스 코드 265파일은 바꾸지 않았다. R1 실패 로그와 ZIP은 보존했다.

삼성파트너 `hyungjininfocz.son@partner.samsung.com`에 ZIP·별도 APPLY TXT·워크플로우 전체 TXT·40문항 보고서·안내서 5개를 발송했다. Gmail SENT 메시지 `1a1136fc78d836dc`에서 수신자·제목·첨부 이름과 크기를 재확인했다. [발송 확인 영수증](EMAIL_VERIFIED.json).

GENOS 코드 적용·현장 세대 gate·push commit·코드서빙 리비전 배포·워크플로우 편집기 적용·실제 내부 질의는 아직 수행하지 않았다. 실제 질의 검증은 워크플로우 테스트 화면에서 수행한다.
