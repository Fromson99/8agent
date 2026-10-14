# 별도 SSE 서버의 현재 판단 로그와 근거 그래프

2026-10-08 사진에서 본문 검색 후보가 관계 없는 법령 노드로 쌓여 실제 근거 관계를 밀어내고, 저장 근거 재결속의 TOOL_RESULT가 결과 수 미기록으로 표시되는 것을 확인했다. 사진만으로 현장 코드 hash·generation·리비전을 확정하지 않는다.

사용자 선택은 **별도 `stream_app:app` SSE 서버 → 기존 분리 Python 표시 단계**다. 서버는 `service.service`를 한 번 호출하고 `/stream`의 진행·답변·최종 원시 응답을 전달한다. Python 소비자는 동일 응답을 표시한다. `main_integrated`나 `GENOS_MAIN_MODE=integrated`를 선택할 필요가 없다.

SVG R10 `judgment-evidence-svg-20261008-r10`은 검증된 법령→원문→판단 관계를 우선 배치한다. 연결 없는 검색 후보는 SVG 밖의 접힌 목록에 전체 보존한다. 법령의 화면 라벨은 경로 마지막 이름이며 전체 경로는 SVG title·판단 상세·후보 목록에 남는다. 검색 후보를 판단 근거에 임의 연결하지 않는다. source_id·현재 route·judgment_ref·내용 hash 검증은 유지한다.

진행 R2 `rag-current-judgment-20261008-r2`는 승인된 SELECT/ASSESS의 선택 이유·모든 판단 문장·근거·미확인 사항을 생략 없이 전달한다. 권한 밖 근거와 hash가 다른 payload는 표시하지 않는다. MODEL RESPONSE의 native `claims`를 읽고 “모델 제안 (채택은 후속 검증)”으로 표시한다. 저장 근거 재결속 수는 `observation_evidence`의 실제 행 수로 표시하며, 다른 도구의 미기록 수를 추정하지 않는다. 현재 판단과 오류는 SSE 큐의 일반 진행 정리 대상에서 제외하고 연결 해제에 대응하는 backpressure로 전달한다. 원시 오류·traceback·저장 journal은 보존한다.

별도 서버 stdout/stderr에 `agent.current_judgment` 이벤트가 현재 판단과 이유를 request_id/run_id/journal_seq와 함께 출력한다. health/SSE_CHECK는 `execution_mode=separate-sse-server`, 진행 revision, `judgment_log_revision=sse-current-judgment-20261008-r1`을 보고한다. health는 HTTP 준비만 뜻하며 데이터나 현장 성공을 보증하지 않는다.

현장 시작 명령은 기존 리비전의 수신 포트를 그대로 사용한다.

```bash
cd ~/DEV
python3 08_DEPLOYMENT/GENOS/start_sse.py --app stream_app:app --port <기존_수신_포트>
```

포트 환경변수가 기존과 일치하면 `--port`를 생략한다. 워크플로우의 endpoint는 이 별도 서버의 `/json` 기준 URL이며 소비자가 `/stream`을 사용한다. 기존 코드서빙 ID·인증·데이터 설정을 사용하고 임의의 새 포트나 localhost 주소로 바꾸지 않는다. Python 편집기 전체 TXT 반영은 코드 ZIP 적용·Git push·리비전 배포와 별도다. 질의·warmup 검증은 워크플로우 테스트 화면에서만 한다.

반입은 `08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r5/`의 새 ZIP/RUN/WORKFLOW 전체 TXT와 GUIDE를 사용한다. 검증된 기존 DEV inventory에 필요한 코드만 백업 후 적용한다. 원문 generation/CURRENT, DB, 조사 예산, CM·오류 로그 변환과 이전 백업을 보존한다. 적용 DEV에서 만든 APPLIED_CODE.zip과 같은 committed checkout/generation gate를 통과한 뒤 push/새 리비전을 확인한다. 원복은 이번 receipt의 백업으로 수행한다.

로컬 표시·SSE·로그 계약 검증이며 신규 모델 호출은 없다. 원시 기록·실패 로그는 `09_ARTIFACTS/AUDITS/20261008-svg-judgment-standalone-r1/`에 보존한다. 기존 일부 구 진행 테스트는 R1 이전의 조문별 반복/모델 입출력 노출을 요구하여 수정 전 코드에서도 실패한다. 경험 재사용 fixture의 `knowledge_id` 스키마 불일치도 수정 전 동일 실패이며 이번 표시 검증 통과에 포함하지 않는다. 로컬 MAIN45의 활성 포인터와 선택 릴리스는 유지한다. GENOS 적용·push·배포·실제 화면은 미확인이다.
