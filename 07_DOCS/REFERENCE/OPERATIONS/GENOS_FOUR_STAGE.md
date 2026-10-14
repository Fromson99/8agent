# 문서 구조화 · 용어집 · 연결과 색인

현재 작업 코드의 실행 계약이다. GENOS 전처리기 연결은 사용자 확인 기준이며,
이번 코드의 GENOS 배포·전체 문서 처리는 별도로 확인해야 한다.

## 실행 단위

- A 문서: `RAW/internal`과 지원 외부 source 폴더의 입력을 수집한다. XML/HTML은
  출처·형식 전용 파서, PDF는 GENOS 전처리기와 구조 복원·설정된 VLM 검수,
  Office는 기존 형식 경로를 사용한다. 용어집 없이 `STRUCTURE/<지문>/source.sqlite`를 만든다.
- B 통합: A의 전체 완료 영수증과 명시한 기존 세대로 원문을 통합하고, 기존 사전에
  문서의 명시 정의 후보를 추가한다. 기존 미검토 후보·완료 관측은 보존한다.
- C 검토: 기존 미검토 후보와 새 정의를 하나의 GENOS 검토 계획으로 처리한다.
  완료된 동일 근거는 재사용한다. 호출 한도 내에 끝나지 않으면 exit 3으로 재개한다.
- D 연결·색인: 검토된 사전으로 통합 원문 전체의 출현·정의·명시 참조를 연결하고
  navigation-v3와 서빙 자원을 검증한다. 이 단계의 LLM 호출은 없다.

2026-10-08 MAIN의 `build-all --execute` 기본값은 모델 없는 A → B → compact-v2 연결·색인이다.
팀 RAW의 native 원본 파서, VLM off, 로컬 PDF 파서를 명시한다. B에서 문서 근거를 교체한
새 용어 초안을 준비하며 C의 모델 검토는 실행하지 않는다. `document-release reindex`가
2026-10-03 최종 GENOS 방식의 compact-v2, navigation-v7/storage-v3와 단위 전문 색인을
명시 선택한다. 서빙 자원과 감사 원장을 포함한 후보를 만들고 오프라인 계약을 검사한다.
CURRENT·활성 MAIN 전환은 별도다. 완료 지식 묶음이 없으면 중단하며 legacy로 자동 전환하지 않는다.

`build-all --with-model-review --execute`는 기존 A → B → C → D 순서다. B 이후는 기존 `document-release`가 담당한다.
구조화 실패 시 용어 검토를 시작하지 않는다. 같은 명령으로 구조 캐시·검토 상태를 재사용한다.
기존 사전·지식 데이터가 없는 환경에서 이 명령이 외부 수집이나 사전 반입을 대신하지 않는다.

```bash
# A: 문서 구조화만 (용어집 불필요)
bash 06_TOOLS/COMMANDS/genos_data_stages.sh --run-id units-001 --check-only
bash 06_TOOLS/COMMANDS/genos_data_stages.sh --run-id units-001 --stage structure --execute

# XML/외규를 읽지 않고 내규 PDF 한 건으로 같은 구조화 경로 확인
bash 06_TOOLS/COMMANDS/genos_data_stages.sh --run-id pdf-structure-001 --only-internal-pdf --limit 1 --stage structure --execute

# 기본: 원본 직접 구조화 → 모델 없는 GENOS compact-v2 연결·색인
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id units-001 --execute

# 기존 모델 검토 구축을 명시적으로 선택
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id reviewed-units-001 --with-model-review --execute

# 이미 준비된 구조화 결과와 선택 용어집을 연결·색인
.venv/bin/python -B 06_TOOLS/pipeline.py build-data-stages --run-id units-001 --stage index --execute
```

## 입력과 재개

동일 폴더의 원본/PDF는 XML → HTML → HWPX → DOCX → PDF → HWP 순서로 선택하고,
PDF는 원본 우선 문서의 참고 파일로 연결한다. DOC만 있으면 PDF 반입 오류를 낸다.
`--only-internal`은 외규 지정 scope와 독립적으로 RAW/internal 전체 형식을 선택한다.
ZIP 병합·해시 중복 점검, 폴더명/별칭 전달은 [원본 우선 가이드](GENOS_NATIVE_PRIMARY.md)를 따른다.

논리 data root 아래 `RAW/internal`, `RAW/law`, `RAW/krx`, `RAW/kofia`, `RAW/expc`,
`RAW/fsc`, `RAW/moleg`, `RAW/prec`를 읽는다. `PDF/internal`은 더 이상 기본 입력이 아니다.
파일 이행은 별도 작업이다. PDF 이동·HWP 삭제는 자동으로 실행하지 않는다.
`--exclude-internal`은 내규를 제외한다. 입력 목록 검사도 목록·상태 파일을 쓴다.

A가 `LOGS/<run>/structure-selection.json`에 입력 명세 지문과 문서별 완료 구조화 영수증
해시를 남긴다. 후속 통합과 단독 index는 이 기록을 검증하며 파서·VLM 환경 설정을 다시 요구하지 않는다.
이전 실행의 선택 기록이 없으면 동일 입력으로 structure를 먼저 실행한다.
원문 선택이 바뀌면 새 run ID를 사용한다. 완료 캐시 파일의 변조는 재사용하지 않는다.
`--only-internal-pdf`는 RAW/internal의 PDF만 선택하며 `--limit`은 이 옵션과 함께만 쓴다.
한 건 확인 후 전체로 확대할 때 새 run ID를 지정한다. 청크 응답은 VLM을 끄고 적재할 수 없다.

전처리기는 ID 또는 URL과 실제 공유 경로를 사용한다. REVISION은 선택사항이다.
미설정 시 서버 버전을 확인했다고 간주하지 않고 같은 run ID 안에서만 구조 캐시를 재사용한다.
서버 설정·모델 변경 시 새 run ID를 사용한다. 명시한 revision이 있다면 캐시에 결속한다.

## 결과와 활성화

`LOGS/<run>`의 detail/progress 로그, 문서 상태표와 CSV를 확인한다.
중단 시 상태 원장에 중단을 기록하며 무거운 상태표를 다시 생성하지 않는다.
`TERM/<run>/<document>/generation`은 DRAFT다. MAIN/CURRENT·서빙 활성화는 하지 않는다.
RAG의 LLM 근거 탐색·답변 생성은 질의 시 별도 실행된다. 의미 추출·벡터 필수 단계는 없다.

## 추가 문서의 통합 서빙

`build-all`은 문서별 색인 단계를 선행하지 않고 통합 원문에 최종 색인을 만든다. `--base-generation`(반복 가능)으로 유지할 기존 세대를 명시하고, `--exclude-document`로 제외할 기존 버전 ID를 지정한다. 통합 용어 검토가 남으면 exit 3으로 재개한다. 기본 산출물은 `TERM_RELEASES/<run>/serving/generation`이며 CURRENT는 변경하지 않는다. [입력·검토·검증·활성화·롤백](GENOS_DOCUMENT_CONNECTIONS.md)을 따른다.
