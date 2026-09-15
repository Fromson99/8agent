# GENOS 코드·용어집 반입 — 2026-09-15

이 문서는 앞서 만든 147MB 기본 사전 반입본의 범위다. 이후 사용자 지시로 추가한
Wikidata/FIBO·전체 관계 반입본은 [전체 관계 묶음 가이드](GLOSSARY_KNOWLEDGE_BUNDLE.md)를 따른다.

이 패키지는 현재 작업 코드와 `GLOSSARY_PIPELINE.json.current_draft`가 선택한
용어집을 새 작업 디렉터리에서 실행하기 위한 스냅샷이다. Git 커밋만으로 코드가
고정되지 않으므로 `HANDOFF_MANIFEST.json`의 파일별 SHA256을 실행 기준으로 삼는다.
기존 GENOS 코드·데이터·실행 결과 위에 압축을 덮어 풀지 않는다.

## 포함 범위와 실제 연결

- 실행 코드, 스키마, 엔진 명세, 현재 CLI, 구축기가 hash 검증하는 ADR-0252 의존 코드 3개.
- 현행 용어 초안의 `dictionary.sqlite`와 `report.json`. 원본 바이트·출처·과거 생성 경로를 보존한다.
  과거 절대 경로는 계보 기록이며 이 사전을 읽는 데 원래 로컬 폴더는 필요하지 않다.
- 현재 코드와 hash가 일치하는 미실행 검토 계획 1,793건(`review.sqlite`, `plan.json`,
  `prompt.json`). 호출 이력은 0건이다. 각 입력의 근거 본문/해시를 함께 보존한다.
  `build-all`은 이 상태를 재개하므로 과거 원문 저장소의 절대 경로에 접근하지 않는다.
  상태를 삭제해 `review prepare`를 새로 실행하는 작업에는 원래 결속한 corpus가 필요하다.
- 내부 모델 설정 예시, 파일 검증기, 실행·재개·복구 절차.
- 원문 RAW, 기존 서빙 세대, 실제 키, 가상환경, Python wheel 및 OCR 모델 파일은 별도 준비한다.
  번역/ID 연결 연구 산출물과 명시 조회용 법률 관계 projection은 현재 기본 사전 소비 경로에 포함되지 않는다.

현재 `build-all`은 용어 의미 검토 → 문서 구조화 → 문서–용어 연결 → 의미 추출·검토
→ 임베딩·문서별 DRAFT까지 호출한다. 통합 그래프/온톨로지/RAG 세대를 하나의 실행 묶음으로
선택하는 단계와 피드백 재구축은 미연결이다. `build-all-legacy --publish`는 v3 검토를
소비하지 않는 다른 경로이므로 이 패키지의 실행 명령과 혼용하지 않는다.

## 1. 새 디렉터리에 압축 해제·검증

GENOS 코드스페이스의 Linux/Python 3.11 환경에서 수행한다. ZIP 옆 SHA256 파일과
반입 ZIP을 대조한 뒤, **존재하지 않는 새 디렉터리**에 압축을 해제한다.

```bash
sha256sum -c genos-pipeline-glossary.zip.sha256
mkdir genos-pipeline-glossary
python3 -m zipfile -e genos-pipeline-glossary.zip genos-pipeline-glossary
cd genos-pipeline-glossary
python3 verify_handoff.py
```

이름을 바꾼 ZIP은 SHA256 파일의 파일명도 실제 이름에 맞춰 확인한다.
기존 Git 저장소의 배포 이력은 보존한다. 이 디렉터리에서 검증 후 내부 Git 반영·리비전
배포가 필요하면 기존 저장소의 정상 commit/push 절차를 사용한다. 압축 해제는 배포가 아니다.

## 2. Python 의존성과 원문 준비

```bash
python3 -m venv .venv
# 현장에 반입한 Python 3.11/Linux 호환 wheelhouse를 지정한다.
.venv/bin/python -m pip install --no-index --find-links /현장/wheelhouse -r requirements-pipeline.txt
```

내부 패키지 저장소를 쓰는 현장은 해당 저장소의 설치 절차를 사용한다.
Docling/OCR의 모델 캐시는 별도 반입해야 하며, DOC 변환용 LibreOffice도 해당 형식 사용 시
필요하다. 로컬 가상환경을 그대로 복사하는 방식은 사용하지 않는다.

원문은 새 작업 디렉터리의 `01_DATA/RAW`로 반입한다. 공개 원문은 출처·버전·해시를 가진
기존 패키지/manifest와 함께, 실제 내규는 GENOS 안에서 준비한다.
내규는 `internal/부서/팀/문서`, 외규는 `law`, `krx`, `kofia`, `expc`, `fsc`, `moleg`, `prec`
하위에 둔다. 원본은 보존한다. 고정 공개 패키지까지 반입했다면 기존 `prepare-data`를 사용한다.

## 3. 내부 모델 설정

`08_DEPLOYMENT/GENOS/pipeline.env.example`을 현장 설정에 복사하고 빈 값을 채운다.
키는 현장 비밀 설정에만 저장한다. CLI에는 환경변수로 전달해야 한다.
파일 방식이면 로컬 작업 디렉터리에 `.env.genos.local`로 저장한 뒤 아래처럼 로드한다.

```bash
set -a
source .env.genos.local
set +a
```

구축 LLM/임베딩은 `semantic_runtime.genos.from_env`의 설정을 사용한다.
게이트웨이형은 `GENOS_BASE_URL`과 각 SERVING_ID/KEY/MODEL을 지정한다.
`GENOS_GATEWAY_API_PREFIX=none`이 현재 구축 코드 기본값이며 `/v1` 여부는 현장 라우트에 맞춘다.
직접 모델 URL 방식은 `GENOS_LLM_URL`/`GENOS_EMBED_URL`과 각각의 `*_API_PREFIX`를 사용한다.
PDF 구조화 VLM은 별도 호출 예산을 쓰며 미해결 검수는 후속 의미 구축을 보류한다.

## 4. 점검·실행·재개

```bash
# 포함된 검토 계획·입력 목록 점검. 로그는 생성하지만 모델은 호출하지 않는다.
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id genos-all-001 --check-only

# GENOS 내부 모델로 구축한다. 내부 원문까지 포함한다.
.venv/bin/python -B 06_TOOLS/pipeline.py build-all --run-id genos-all-001 --max-review-jobs 100 --execute
```

외규만 처리할 때는 두 명령에 `--exclude-internal`을 붙인다.
용어 검토에 남은 작업이 있으면 종료 코드 3이며 **동일 실행 명령을 반복**한다.
완료 작업은 재호출하지 않는다. 검토 원장은 설정된 `LEXICON/glossary-v1/reviews/` 아래에,
문서 결과는 `01_DATA/LOGS/genos-all-001/doc-status.html` 및 `result-*.json`에 기록된다.
문서 구축의 일부 실패/건너뜀은 종료 코드 2, 사용자 중단은 130이다.
실패 원인을 고친 뒤 용어 검토 실패를 재시도할 경우 `--retry-review-failed`를 명시한다.
완료 영수증 발행 후 재검토·모델/코드 변경은 기존 결과를 보존하고 새 상태/출력 설정으로 진행한다.
문서 의미 구축의 코드/모델/설정 변경에는 새 run-id를 쓴다.

## 5. RAG 연결과 롤백

문서별 DRAFT가 생겨도 통합 서비스 세대로 자동 활성화되지 않는다.
`service.py`에는 RAG 경로가 포함되어 있지만 이 ZIP은 서빙 세대를 포함하지 않는다.
현장에서 별도로 검증한 `semantic-runtime-generation-v1` 세대가 있을 때
`GENOS_GENERATION`을 해당 절대 경로로 지정하고 `SEMANTIC_LLM_BACKEND=genos`를 설정한다.
적재·질의 임베딩은 같은 모델·버전·전처리여야 한다. 현장 코드서빙의 리비전·볼륨 접근과
실제 검색/답변·인용 확인은 별도 검증 대상이다.

이 반입/구축 절차는 기존 CURRENT나 서비스 리비전을 변경하지 않는다.
중단 시 프로세스를 종료하고 새 작업 디렉터리를 보존한다. 서비스 리비전을 후속 변경했다면
종전 리비전과 종전 데이터 세대 설정으로 되돌리고 새 프로세스에서 선택 결과를 확인한다.

## 검증 범위

로컬 압축 해제본의 파일 해시, 파이프라인 진입점, 고정 의미 추출 의존성,
용어집 무결성/선택, 모델 없는 검토 계획과 입력 점검을 검증한다.
이 결과는 GENOS 내부 모델 호출·실제 내규 품질·전수 구축·플랫폼 배포 성공을 의미하지 않는다.
현재 외부 Codex 환경에서는 GENOS 접속을 시도하지 않는다.
