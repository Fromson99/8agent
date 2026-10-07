# GENOS 용어집 ZIP + 통합 데이터 파이프라인

2026-09-11, ADR-0364. 현재 GENOS LLM·임베딩 API와 SQLite 구성을 그대로 쓴다.
`06_TOOLS/genos_pipeline.sh`는 기존 작성기·검토기·색인기를 호출하는 ZIP 호환 진입점이다.
`06_TOOLS/pipeline.py build-all-legacy`도 같은 SH를 호출한다. 현재 기본 `build-all`은
[새 용어 검토와 문서 DRAFT 단위 실행](GLOSSARY_ALIGNMENT.md)을 합성하며, 이 ZIP 경로와
데이터 계약이 다르다. 별도 RAG 구현은 만들지 않는다.

## 한 명령으로 실행

현재 저장소 코드를 GENOS에 반영하고, 완료 용어집 ZIP을 `TRANSFER`에 넣은 뒤 코드 루트에서 실행한다.
RAW 경로는 `internal`, `law`, `krx`, `kofia`, `expc`, `fsc`, `moleg`, `prec`와 각 수집 manifest가 있는 실제 경로다.

```bash
bash 06_TOOLS/genos_pipeline.sh \
  --knowledge-zip "$PWD/TRANSFER/genos-glossary-20260911.zip" \
  --corpus-root "$PWD/01_DATA/RAW" \
  --data-root "$PWD/01_DATA/GENOS" \
  --run-id all-001 \
  --execute --publish
```

점검만 하려면 `--execute --publish`를 `--check-only`로 바꾼다. 기본도 점검만 한다.
점검은 ZIP 반입과 입력 목록 검증이며, 원문 전수 파싱이나 실제 모델 접속 성공을 뜻하지 않는다.
원문 폴더를 직접 지정할 때는 `--corpus-root` 대신
`--input-root /내규폴더 --source internal --external-root /외규폴더`를 쓴다.
내규를 제외하려면 manifest RAW 방식에 `--exclude-internal`을 붙인다.

같은 명령·같은 run ID로 다시 실행하면 검증된 구조화 결과, 완료된 LLM 작업과 임베딩 배치를 재사용한다.
처음 선택한 법령 기준일도 재개 시 유지한다. ZIP·원문·코드·모델·주요 설정이 바뀌면 새 run ID를 쓴다.
`--max-calls 10000`은 실행당 작성 호출 상한이며 작업을 버리는 옵션이 아니다.
오류나 미완료 작업이 있으면 통합 세대와 CURRENT를 발행하지 않는다. 문서별 부분 성공 catalog는 발행하지 않는다.

## 동일 파이프라인의 단계

1. ZIP 파일·패키지·완료 체크포인트·해시를 확인하고 오프라인 반입한다.
2. 법제처 법령용어·지식용어·일상용어를 이름공간이 분리된 SQLite 용어집으로 만든다.
3. 내규·외규를 기존 수집 경로로 읽는다. 법령 XML은 태그로 구조화하고, 다른 형식은 기존 파서를 쓴다.
4. 같은 이름의 법령 XML은 확인된 시행일·공포일로 수집본 중 최신 유효 판본을 선택한다.
   날짜가 없는 중복이나 같은 날짜의 다른 내용은 임의 선택하지 않는다. 새로운 법령을 다운로드하지 않는다.
5. 기존 source-job 최적화와 코드 기반 표제어 조회를 적용하고, 기존 LLM 의미 추출·근거 검증·독립 검토를 실행한다.
6. GENOS 임베딩 결과를 `vectors.sqlite`에 저장하고 의미 번들과 원문을 하나의 source identity로 결합한다.
7. 반입된 공식 용어 관계와 조문 좌표를 해당 원문에 연결한다. 폴더 표시명과 XML 공식명을 연결할 때 원문 해시가 일치해야 한다.
8. 완성된 하나의 세대를 저장한다. `--publish`가 있으면 GENOS CURRENT만 원자적으로 선택한다.

서빙은 기존 `service.py`와 `retrieve → select → assemble → answer`를 그대로 사용한다.
일상 표현 → 수집된 용어 관계 → 실제 조문 → 기존 의미 관계/연결 조문 순서로 같은 RAG 안에서 처리한다.
용어 목록에 있다는 이유만으로 법제처 일상용어와 모든 조문 사이의 관계를 만들어내지는 않는다.

## 이미 반영된 최적화와 남은 작업

- 용어집을 만들거나 공식 용어 관계를 연결하는 데 LLM/법제처 API를 추가 호출하지 않는다.
- 용어집 전체를 프롬프트에 넣지 않는다. 현재 원문에서 문자 경계가 확인된 표제어만 작업당 최대 24개 전달한다.
- 원문 구조 소유권 검색의 기존 최적화, 작업별 구조 범위 축소, 검증된 구조 캐시와 완료 호출 재사용을 적용한다.
- 기본 `single`은 의미 추출과 독립 검토다. `--extraction-mode staged`는 기존 단계별 추출을 명시적으로 선택하며 호출 수가 늘 수 있다.
- Concept/Mention/Clause/Rule/Proviso/LegalRelation의 의미 추출은 여전히 필요하다.
  ADR-0360의 명시참조·위임 선처리 후보 전체와 잔여 작업 전용 LLM 큐가 이 명령에 승격된 것은 아니다.
  따라서 전수 실행 시간이나 LLM 호출 절감률은 아직 확정할 수 없다.

## 정의·출처를 포함한 새 용어집 경로

외부에서 `pipeline.py glossary complete --snapshot <name>`으로 전수 수집을 완료하면
`LEXICON/moleg-alignment/completion/<name>/glossary.zip`이 생성된다.
이 ZIP을 위 `--knowledge-zip`에 전달한다. 새 코드에는 `glossary_enrichment.py`와 `glossary_scope.py`도 포함해야 한다.
현재 문서 범위만 수집한 ZIP도 동일하게 반입하며 문서별 출현·정의 근거를 함께 보존한다.
망분리 GENOS는 공개 API를 직접 호출하지 않고 완료 ZIP만 사용한다. pulling은 현재 구현 범위가 아니다.

완료 사전은 `term` 목록 외에 `sense`, `term_sense`, `official_relation`, `official_article`을 가진다.
같은 표제어의 정의는 출처별로 보존하고, 표기 일치는 정의 후보로만 전달한다.
GENOS 작성 작업은 문자 출현과 출처별 정의 후보를 받고 원문에 대한 기존 의미 검토를 수행한다.
공식 관계의 각 행에 원천 요청 ID를 보존하므로 전수 수집한 묶음 패키지도 같은 조문 연결기로 처리한다.
사전 생성 결과와 통합 세대의 dictionary.coverage에서 실제 정의/관계 수를 확인한다.
아래 9개 패키지와 3개 출발 표현 설명은 기존 ZIP의 범위다. 새로운 전수 수집 완료를 뜻하지 않는다.

## 기존 반입본과 실행 환경

완료 패키지 9개를 묶은 `genos-glossary-20260911.zip`은 26,177,216 bytes다.
SHA-256: `ed898af2dc6298a601e6bf8d0e235f498bc70348bf3952f6882de330e22acb8b`.
복원된 목록은 법제처 법령용어 73,041건, 지식용어 144,361건, 일상용어 220,376건, 총 437,778건이다.
이 목록과 별도로 완료된 관계 패키지 6개를 포함한다. 현재 법제처 일상용어 관계 범위는 3개 출발 표현으로 제한된다.
수집 중인 패키지는 넣지 않는다. 추가 수집 완료 후 새 ZIP과 새 run ID로 갱신한다.

새 ZIP은 현재 코드 루트에서 아래처럼 완료 manifest를 명시하여 만든다. 임의 폴더를 압축한 ZIP은 입력 계약과 다르다.

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -m lawrag.pipeline.knowledge_transfer \
  --package /완료패키지1/manifest.json \
  --package /완료패키지2/manifest.json \
  --output /새경로/glossary.zip
```

기존 GENOS 연결 환경변수와 설치된 Python 의존성을 사용한다. SH는 패키지를 자동 설치하지 않는다.
XML 외 문서의 Docling, DOC 변환의 LibreOffice 등 기존 형식별 의존성도 필요하다.
실행 기록은 `<data-root>/builds/<run-id>`의 plan, source, queue, provider, models, handoff와
`<data-root>/receipts`, `<data-root>/generations`에 남는다. 실행 큐에는 실제 모델 ID·입출력·시도 이력이 저장된다.
용어집/작업큐/원문/임베딩 SQLite 파일은 영속 실행 볼륨에 둔다.

서빙에 `GENOS_DATA_ROOT`를 같은 절대 경로로 설정하고 `SEMANTIC_LLM_BACKEND=genos`를 유지한다.
기존 `GENOS_GENERATION`이 설정되어 있으면 그것이 CURRENT보다 우선하므로 사용할 세대에 맞춰 정리한다.
진행 중인 서비스는 새 프로세스로 시작해야 새 CURRENT를 읽는다. 코드 전송·Git push·플랫폼 배포는 기존 배포 절차다.
스크립트 완료는 DRAFT 데이터 생성 완료이며 법률 품질 승인이나 로컬 MAIN 승격이 아니다.

## 검증 범위

합성 문서 2개에서 실제 큐·검토·저장·공식 좌표 연결·SQLite 검색·서빙 factory·재개·입력 오류 보고 계약 15개를 검증했다.
LLM과 임베딩 응답은 고정된 합성 응답이며 실제 GENOS 호출은 0회다. 실패한 임베딩 재개 시 완료 LLM과 배치를 다시 호출하지 않았다.
실제 완료 패키지 9개의 ZIP 복원과 용어집 SQLite 무결성·건수도 확인했다.
현장 모델 접속, 원문 전수 실행, 응답 정답률과 처리 속도는 아직 검증하지 않았다.

실제 `01_DATA/RAW` 전체 점검은 문서 3,290개를 인식했지만 다음 입력 오류 5개로 중단됐다.
내규가 없는 현장에서는 `--exclude-internal`을 명시한다. 나머지 4개 첨부는 기존 파서에 지원 형식 원문으로 제공해야 한다.
입력 오류는 `<data-root>/plans/<run-id>-input-inventory.json`에 상세 경로와 함께 남는다.

| 입력 | 현재 문제 |
|---|---|
| `internal` | 지원 문서 없음 |
| 금융투자업규정 개정전문 ZIP | 압축 첨부 미지원 |
| 금융기관의 업무위탁 등에 관한 규정 ZIP | 압축 첨부 미지원 |
| 은행업감독업무시행세칙 업무보고서 ZIP | 압축 첨부 미지원 |
| 자산대사 업무 표준양식 XLSX | 스프레드시트 첨부 미지원 |

위 3,290개는 최신 판본 선택 전 전체 RAW 후보 수다. 현재 RAG의 159문서와 다른 분모이며,
이 입력 점검을 전체 원문 구조화·LLM 생성 성공으로 해석하면 안 된다.

기존 작업공간의 일반 `pipeline.py check`에는 ACTIVE 릴리스와 5개 runtime 파일 지문의 불일치가 남아 있다.
이 명령은 별도 승인된 릴리스를 기준으로 하는 engine-host 검사다. 해당 과거 배선을 이번에 덮어쓰지 않았다.
`build-all-legacy`는 기존 데이터 작성기를 직접 호출하며 이 engine-host 경로를 사용하지 않는다.
현재 로컬 MAIN generation 11과 고정 릴리스 파일은 유지했다.
