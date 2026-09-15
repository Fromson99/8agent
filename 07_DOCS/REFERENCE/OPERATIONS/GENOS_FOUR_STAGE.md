# 문서 생성 — 구조화·용어 색인

2026-09-15 이후 기존 의미 추출·벡터 필수 단계는 제거되었다. 이 파일명은 기존 안내 링크를 유지한다.
현재 Codex 환경에서는 GENOS 현장에 접근할 수 없다. 아래 절차는 현장 인계용이며 현장 실행 완료 기록이 아니다.

아래는 현재 작업 코드 기준이다. 2026-09-15 사진으로 확인된 구버전 3개 파일에 대한
`PDF/internal` 입력 수정은 [현장 호환 기록](GENOS_INTERNAL_PDF_COMPAT_20260915.md)과 그 인계 명령을 따른다.
해당 호환 패치가 아래의 전체 엔진 변경까지 배포하는 것은 아니다.

## 입력과 실행

`06_TOOLS/pipeline.py build-data-stages`와 `build-data`가 같은 유지보수 runner를 실행한다.
외규는 논리 data root의 `RAW/<source>`, 내규의 준비된 PDF는 `PDF/internal`을 사용한다. 원본·변환 입력은 RAW에 보존한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-001 --check-only
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-001 --stage structure --execute
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id term-001 --stage index --execute
```

한 번에 실행하려면 `--stage all`을 사용한다. `--glossary-dir` 생략 시 현행 완료 검토 사전 또는 설정된 초안을 선택한다. 사전 검토 완료부터 실행하는 명령은 `pipeline.py build-all --run-id term-001 --execute`다. `--exclude-internal`로 내규 입력을 제외할 수 있다.

`llm`, `vector`, `--extraction-mode`, 문서 의미 추출 토큰/호출 옵션은 제거했다. 옛 build-all-legacy는 종료 안내를 낸다. 호환 wrapper genos_build_all/genos_data_e2e는 현재 runner에 전달하며 제거된 옵션을 묵인하지 않는다.

## 산출물과 재개

- `STRUCTURE/<fingerprint>/source.sqlite`: 원문·구조·문서만 저장. 원문 좌표와 해시를 검사한다.
- `LEXICON/LINKS/<fingerprint>`: 원문 출현과 범위 있는 정의 후보.
- `TERM/<run>/<document>/generation/manifest.json`: term-source-generation-v1, 원문과 navigation 색인 해시 결속.
- 같은 상위 폴더의 `result.json`: 입력·사전·코드 지문, 산출물 해시, DRAFT 상태.
- `LOGS/<run>/doc-status.html`, CSV 및 detail/progress 로그: 문서별 구조화·색인 결과.

같은 run ID는 같은 입력/코드일 때만 재개한다. 사전 또는 코드를 바꾸면 새 run ID를 사용한다. 구조 캐시의 파서 지문이 일치하면 구조화를 재사용하고 색인만 재생성한다. 의미 추출 모델은 호출하지 않는다. PDF 구조 복원에 필요한 내부 VLM·형식 파서·기존 `requirements-pipeline.txt` 의존성은 유지한다.

## 서빙 인계·검증·롤백

신규 데이터 생성은 CURRENT/MAIN을 자동 변경하지 않는다. 승인된 결과의 `generation` 디렉터리를 GENOS로 반입하고, 동일 코드 리비전과 의존성·환경 설정 이름을 기록한다. 서비스의 `GENOS_GENERATION`에 그 디렉터리의 절대 경로를 명시한다. generation 안의 navigation 바인딩을 사용하므로 개발 환경의 다른 색인을 자동 선택하지 않는다.

현장에서는 `/health`의 `term-runtime-v1`, 세대, term-agent 모드와 `/v1/rag/ask`의 `use_llm:false` 정의 조회부터 확인한다. 이후 내부 LLM으로 확인한다. 외부 로컬/모의 테스트는 현장 품질 검증을 대신하지 않는다.

이전 코드·데이터 경로·설정 값을 기록하고 문제가 생기면 함께 되돌린다. 새 코드에 옛 의미 세대를 연결하는 방식은 지원하지 않는다. 로컬 MAIN 롤백은 [제거·전환 감사](../../../09_ARTIFACTS/AUDITS/20260915-term-only-schema-removal/README.md)의 명령을 따른다.
