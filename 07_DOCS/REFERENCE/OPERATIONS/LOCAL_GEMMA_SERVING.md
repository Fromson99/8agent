# 로컬 공개 모델 · GENOS 내부 모델 분기

2026-09-30 현재 로컬 활성 릴리스는
`legal-agent-qwen38-public-20260930-r1`(포인터 generation 32)이다.
승인된 공개 문서 145개만 `qwen/qwen3.8-27b` OpenRouter Parasail FP8로
전송하며 reasoning effort none, fallback 없음으로 고정했다. 활성 릴리스의
[release.json](../../../08_DEPLOYMENT/RELEASES/legal-agent-qwen38-public-20260930-r1/release.json)과
[ADR-0584](../../../04_EXPERIMENTS/ADR/ADR-0584-local-rag-qwen38-default-cutover/README.md)에
전환·롤백 근거를 기록했다. 공개 원문 확장 사례 3건은 근거를 회수했지만 조 전체
읽기로 확대되어 속도 개선은 확인되지 않았다. GENOS 내부 모델은 변경하지 않았다.

## 2026-09-23 Gemma 운영 이력

2026-09-23 사용자 정정에 따라 당시 로컬 활성 릴리스는
`legal-agent-local-gemma-20260923-r3`(포인터 generation 24)이다.
로컬 `service.py`는 검증된 릴리스 코드와 공개 범위 승인 파일을 읽고
`google/gemma-4-31b-it`을 OpenRouter Parasail FP8, thinking off, fallback 없이 호출한다.
키는 작업 공간 `.env`의 `OPEN_ROUTER`에서 메모리로만 읽으며 응답·릴리스에 기록하지 않는다.
GENOS 세대를 선택한 서비스는 이 로컬 분기를 타지 않고 기존 현장 환경 파라미터를 받는다.

## 요청과 데이터 경계

모델 호출에는 `public_question:true`가 필수다. 문서 필터가 없으면 승인된 공개 문서
145개만 선택한다. 명시 필터가 승인 목록 밖을 포함하면 422로 거절한다.
`use_llm:false`는 모델 호출 없이 기존 출처 조회를 수행한다.
로컬 `/rag/` 화면에서는 `LLM 답변 사용`과 공개 질문 확인란을 함께 선택한다.
선택 세대의 `export_allowed:false`는 변경하지 않았다. 대신 릴리스에 고정된
`00_SYSTEM/LEGAL_AGENT/local-gemma-public.json`의 세대·store 해시·문서 목록·모델·정책
해시를 요청 시작과 모델 전송 전 확인한다. 비공개 질문·문서에 이 표시를 사용하면 안 된다.

```json
{
  "API_TYPE": "RAG_ASK",
  "json": {
    "question": "정관 변경의 결의요건은?\n(업무 문맥: 주주총회와 이사회의 권한 배분)",
    "use_llm": true,
    "public_question": true
  }
}
```

로컬 CLI `06_TOOLS/pipeline.py check|plan|run --profile legal-rag`도 활성 릴리스의
서비스 경로를 호출한다. `run`의 해시 고정 `request.json`에는 모델 호출 시 같은
`public_question:true`를 넣는다. 결과는 지정한 출력 디렉터리의 `response.json`과
`receipt.json`에 기록한다.

## 확인 결과

- 현재와 같은 모델 경로인 r2 활성 릴리스의 CM-040 요청은 Gemma 실제 전송 6회와
  HTTP 200을 기록했다. 질문 계획과 초안 검증이 실패하여 법률 결론을 유보했다.
- 공개 질문 표시 없음과 비공개 문서 ID 포함은 각각 HTTP 422였다.
- r3 활성 `/health`가 릴리스 ID와 Gemma 모델 ID를 반환했고 `/rag/` 공개 질문 선택을 확인했다.
- r2 활성 서비스의 무관한 질문은 Gemma 4회 호출·HTTP 200 후 법률 근거 검토 미완료를 반환했다.
- 번호 참조 계약 27개, GENOS transport 경계 8개 통과. GENOS 현장 호출은 미확인이다.
- 품질 인증은 `false`다. Gemma 결속과 법률 답변의 정확도는 별도 문제다.

[전환 승인·검증·실행 출력](../../../09_ARTIFACTS/AUDITS/20260923-local-gemma-serving),
[활성 릴리스](../../../08_DEPLOYMENT/RELEASES/legal-agent-local-gemma-20260923-r3/release.json).
이전 릴리스로 되돌릴 때는 `PYTHONPATH=02_BACKEND .venv/bin/python -m semantic_runtime.control rollback --confirm-main`을 사용한다.
