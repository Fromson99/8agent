# GENOS 문서 한 개 E2E

기존 `genos_unified_pipeline.py`에 `e2e --backend genos` 명령을 추가했습니다.
기존 external/internal/bootstrap/publish 명령, 기본 Haiku, 현장 URL/인증 설정은 유지합니다.
이 명령은 실제 API를 호출하며 원문은 현재 설정된 GENOS LLM·임베딩 엔드포인트로 전송됩니다.

## 설치 후 한 번에 실행

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_e2e.sh
```

등록된 외부 법령 XML 중 작은 본문 하나를 자동 선택합니다. `GENOS_DATA_ROOT`가 없으면
코드 폴더의 `GENOS_DATA`, `01_DATA/INBOX/AUTHORING` 순서로 원문 저장소를 찾습니다.
자동 선택할 원문이 없으면 중단합니다. 전체 문서 처리를 시작하지 않습니다.

직접 원문과 질문을 지정하려면:

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_e2e.sh \
  --document '/home/genos/DEV/업로드한문서.pdf' \
  --source internal \
  --question '이 문서가 정한 담당자의 의무를 근거와 함께 설명해 줘.'
```

외부 자료는 `--source external`; 이미 등록된 파일은 `--source auto`로 출처를 유지합니다.
PDF/HWP/HWPX/DOCX는 기존 파서·변환 프로그램이 설치되어 있어야 합니다.
이미지뿐인 PDF/OCR, 연결 문서, 별도 첨부파일까지 자동 확장하지 않습니다.

파라미터가 들어간 원래 명령은 다음과 같습니다. Bash는 이것을 실행합니다.

```bash
.venv/bin/python -u 06_TOOLS/COMMANDS/genos_unified_pipeline.py \
  --data-root /home/genos/DEV/GENOS_DATA \
  e2e --backend genos --document auto \
  --chunk-chars 1400 --max-chunks 64 --batch-size 4 \
  --max-tokens 4096 --timeout 120 \
  --question '이 문서의 목적과 주요 의무 또는 적용 대상을 원문 근거와 함께 설명해 주세요.' \
  --execute
```

`--execute`를 빼면 파일 선택만 확인하며 LLM·임베딩을 호출하지 않습니다.
기본값으로 본문 전체가 64청크를 넘으면 첫 모델 호출 전에 중단합니다. 몰래 앞부분만
처리하지 않습니다. 필요할 때 명시적으로 `--max-chunks 128` 등으로 늘리세요.

## 실제 실행 과정

1. 원문 한 개 복사 및 SHA-256 기록. 기존 업로드 파일을 이동/삭제하지 않습니다.
2. 기존 공통 ingest로 구조화. 원문 블록의 좌표를 보존하여 긴 블록만 청크로 분할합니다.
3. GENOS LLM이 각 청크에서 검색에 중요한 원문 구절을 추출. 원문에 없는 구절은 거절합니다.
4. 원문 청크+추출 구절을 임베딩하여 `vectors.json`에 저장한 뒤 다시 읽고 검증합니다.
5. 질문도 같은 모델로 임베딩. 기존 legal-rag 파이프라인에서 파일 벡터 검색과 BM25를
   통합하고 LLM으로 근거를 선택합니다. 외부 vector DB는 쓰지 않습니다.
6. 기존 근거 조립·답변 계약으로 답변 생성. 인용 구절이 원문에 실제 존재하는지 검사합니다.

청크 수 N, 배치 크기 B이면 정상 실행 시 GET 모델조회 2회,
LLM POST `ceil(N/B)+2`회, 임베딩 POST `ceil(N/B)+1`회입니다.
호출별 재시도는 없고 읽기 제한 기본 120초입니다. 전체 실행시간 상한은 아닙니다.
조회된 API 모델 ID를 POST body에 사용합니다. URL의 serving ID와 혼동하지 않습니다.

## 결과

`GENOS_RUNTIME_DIR/e2e/one-doc-.../`에 저장하며, 환경변수가 없으면 코드 폴더의
`runtime/e2e/one-doc-.../`입니다. `--run-root`로 지정한 폴더 아래에도 `e2e`가 붙습니다.

- `run.log`: 단계, 경과 시간, 진행률, 최종 답변
- `chunks.json`, `reviews/`: 청크 원문 좌표, LLM 처리 결과(DRAFT)
- `calls/`: 요청·응답·usage·지연·검증 기록, 환경변수의 키/토큰 값은 마스킹
- `vectors.json`, `retrieval.json`: 실제 벡터와 검색 경로
- `selection.json`, `assembled.json`: 선택 및 답변에 전달된 근거
- `answer.txt`, `answer.json`: 최종 답변
- `result.json`: 전 과정 성공 시에만 생성
- `failure.json`: 실패 원인. Bash 종료 코드도 0이 아닌 값

일부 모델 호출이 성공해도 전체 성공으로 표시하지 않습니다. 검증된 인용 주장이 없는
답변은 이번 문서 E2E 성공 기준을 충족하지 않습니다. 질문을 해당 문서 범위로 좁히세요.

**범위:** 이번 연결은 원문 기반 RAG E2E입니다. LLM의 핵심 구절 추출은 검색 보조 DRAFT이며
정식 온톨로지/프레임 전체 구축·심사·승인이 아닙니다. `legal-authoring`의 미이관 단계가
이 명령으로 완성되는 것은 아닙니다. 모델 학습/파인튜닝이나 법률 정확도 평가도 아닙니다.
기존 CURRENT, MAIN, Git, 서빙 배포는 자동 변경하지 않습니다.

## 패치 및 복구

패치 ZIP에는 원문·벡터·환경변수·키·과거 LLM 데이터가 없습니다.
설치기는 대상 파일의 이전 해시를 확인하고 기존 변경 파일만
`runtime/patch-backups/genos-e2e-.../`에 백업합니다. 모르는 변경은 덮어쓰지 않습니다.
`semantic_runtime/genos.py`는 패치에 포함하지 않으므로 현장 연결 수정은 그대로 유지됩니다.
기존 ZIP에서 오래된 provider/storage 해시를 담고 있던 엔진 manifest와 PIPELINE의
해시 기록만 현재 포함 코드에 맞게 갱신했습니다. 해시 검사를 끄지 않습니다.

로컬 검증은 가짜 HTTP와 합성 XML을 사용하는 계약 검사입니다.
현장 GENOS의 실제 모델 응답까지 여기서 성공했다고 주장하지 않습니다.
