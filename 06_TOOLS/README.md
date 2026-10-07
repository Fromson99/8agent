# 06_TOOLS

얇은 CLI만 둔다. 재사용 로직은 `lawrag` 패키지로 옮기고 CLI는 인자 파싱과 출력만
담당한다.

`run_tool.py`는 `ACTIVE_TOOLS.json`에 등록된 운영 도구만 receipt-bound generation에서
실행한다. 단, `adr_structure.py`는 사용자 변경 실험 정책을 반영하기 위해
`COMMANDS/adr_structure.py` 작업 코드를 실행한다. 다른 도구의 불변 세대는 유지한다.

- `COMMANDS/`: 현재 운영 CLI 원본
- `EXPERIMENTS/ADR/`: ADR 번호에 결속된 재현 도구
- `EXPERIMENTS/RAG/`: `CLAIMS`, `DEFINITIONS`, `GRAPH`, `HAIKU`, `PROVISO`,
  `RETRIEVAL`, `GENERAL` 기능 축으로 나눈 RAG 분석·평가 도구
- `EXPERIMENTS/DATA/`: 데이터 구조 변환·검증 도구
- `EXPERIMENTS/DOCUMENTS/`: 보고서·도식 생성 도구
- `EXPERIMENTS/EVALUATION/`: 비-RAG 평가·골든셋 도구
- `EXPERIMENTS/OPERATIONS/`: 퇴역 운영 흐름의 재현 도구
- `MIGRATION/`: 구조 이행 전용 도구
- `AUDIT/`: 정적 감사 도구
- `GENERATIONS/`: 불변 배포 세대

운영 진입점은 항상 `06_TOOLS/run_tool.py`를 거친다.

GENOS 반입 패키지에 결속된 구축 실행은 패키지 TXT가 현재 `OFFLINE/genos_reindex_runner.py`를
직접 선택한다. `--serving --fulltext-granularity unit`은 준비 완료 source·용어집에서
문서–용어 연결 → 서빙 용어집 캐시 → navigation/감사 → 전문 색인 → 오프라인 검증을 수행한다.
`--completed-glossary`는 같은 입력에서 나온 완료 의미 검토 영수증까지 검증해 재사용한다.
`publish --shared-root`는 새 공유 세대만 만들며 CURRENT와 코드서빙을 활성화하지 않는다.
모델/구조화/의미 검토를 다시 호출하지 않는다. 기본 색인 전용 모드는 유지한다.
[실행·재개·롤백 안내](../08_DEPLOYMENT/GENOS/handoffs/sqlite_read_reuse_20261003_r1/GENOS_SQLITE_READ_REUSE_GUIDE_UTF8.txt).

## 서빙 코드 수정 뒤 해시 다시 맞추기

`00_SYSTEM/PIPELINE.json`과 `02_BACKEND/ENGINES/*/`의 엔진 manifest는 서빙 코드·스키마를 해시로 고정한다.
`semantic_runtime/*.py`를 고치면 다음 질문에서 `engine code hash mismatch`로 멈춘다(옛 코드로 돌지 않는다).

```bash
.venv/bin/python 06_TOOLS/semantic_runtime.py --root . rehash-engines            # 검사만, 어긋나면 exit 1
.venv/bin/python 06_TOOLS/semantic_runtime.py --root . rehash-engines --apply    # 코드·스키마 해시 갱신
.venv/bin/python 06_TOOLS/semantic_runtime.py --root . rehash-engines --apply --add-new  # 새 모듈도 manifest에 등록
```

색인·용어집·projection 같은 데이터 핀은 검사 결과만 보고하고 고쳐 쓰지 않는다. 데이터 선택은 의도적으로 바꾼다.
`PIPELINE.json`은 해시 문자열만 치환하므로 다른 필드의 동시 수정은 보존된다.
ACTIVE_RELEASE로 뜬 로컬 서버는 릴리스 코드 스냅샷을 쓰므로 작업 트리 수정이 반영되지 않는다.
작업 코드로 확인하려면 `GENOS_GENERATION=<세대 경로> 06_TOOLS/serve.sh`로 띄우고, 코드 수정 뒤에는 재시작한다.

관계 탐색 v3의 계약 등록은 `run_tool.py legal_agent_contracts.py --version v3`, 운영자 읽기 전용 이력 조회는 `run_tool.py legal_agent_trace.py --runtime-root <semantic runtime> --run-id <id>`를 사용한다. [설정·복구 계약](../07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V3.md).

2026-10-03 GENOS compact 구축: `genos_reindex_runner.py build --serving --storage-profile compact-v1`
은 완료 prepared/명시 glossary를 재사용해 작은 원문·용어집·정수 occurrence 세대와 unit FTS를 만들고
단계별 checkpoint로 재개한다. [구현·검증 기록](../07_DOCS/REFERENCE/REPORTS/GENOS_COMPACT_LIFECYCLE_IMPLEMENTATION_20261003.md),
[현장 안내](../08_DEPLOYMENT/GENOS/handoffs/compact_lifecycle_20261003_r2/GENOS_COMPACT_LIFECYCLE_GUIDE_UTF8.txt).
MAIN/CURRENT 및 코드서빙 리비전은 자동 변경하지 않는다.
