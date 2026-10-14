# GENOS 전체 데이터 상주 캐시 R4

16GB 서버 기준 RAM 예산 8GB로 선택된 검색 데이터 전체를 최초 사용 때 한 번 준비하고 모든 질문·세션이 재사용한다. RAM이 부족한 데이터도 전체 로컬 복사본을 유지한다. 기존 계측 R3와 누적 시스템 로그를 포함한 307파일 ZIP이며 검색 결과 LRU는 보조 기능이다.

- [현장 적용·설정 안내](GUIDE_UTF8.txt)
- [전체 코드 ZIP](GENOS_QUERY_LATENCY_20261007_R4.zip)
- [check/apply/verify/gate/push/rollback TXT](GENOS_QUERY_LATENCY_20261007_R4_APPLY.txt)
- [별도 원격 push TXT](GENOS_QUERY_LATENCY_20261007_R4_PUSH_NEW_REMOTE.txt)
- [로그 요약 Python TXT](GENOS_QUERY_LATENCY_20261007_R4_SUMMARIZE.txt)
- [검증 기록](VALIDATION.json), [코드 manifest](CODE_MANIFEST.json), [해시](SHA256SUMS)

통합 검사118개와 실제 TXT 반입·원복·gate·mock push 검사9개가 통과했다. 기존 로컬 workspace activation receipt 불일치는 합성 앱에 명시적인 임시 runtime_root를 준 테스트 harness로 분리했고 생산 receipt는 수정하지 않았다. 이전에도 실패한 구 adoption fixture 2개는 별도 기록했다.

워크플로우 편집기 변경은 캐시 기능의 필수가 아니다. 별도 진행 UI 작업과 현재 작업 코드 수정은 보존하며, 이 ZIP은 검증된 누적 system logging 기준에 캐시 수정만 결속했다. workflow 전체 TXT는 참고용이며 기존 편집기를 덮어쓰지 않는다. 로컬 MAIN45 포인터, NFS generation은 변경하지 않았다. GENOS 반입·배포·현장 속도는 미확인이다.

삼성메일 발송 완료: SENT 1a1151de7ae334ad에서 수신자와 첨부7개 이름/크기를 확인했다.
