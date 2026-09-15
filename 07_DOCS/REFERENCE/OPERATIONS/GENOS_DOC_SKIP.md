# GENOS DOC 지원 · 실패 문서 건너뛰기 (2026-09-10)

이번 패치는 데이터 구축 전용이다. 기존 URL·키·현장 genos.py·원본·Git·CURRENT는
변경하지 않는다. 실패 문서는 삭제하지 않고 사유를 남겨 건너뛴다.

## 설치

메일의 ZIP과 `.sh.b64.txt`를 `/home/genos/DEV/TRANSFER`에 업로드한다.
`unzip`은 필요 없다. 알 수 없는 현장 수정은 설치 전 중단하고, 알려진 이전 파일은 백업한다.

```bash
cd /home/genos/DEV/TRANSFER
base64 -d genos_apply_doc_skip.sh.b64.txt > genos_apply_doc_skip.sh
bash genos_apply_doc_skip.sh
```

## 입력 위치와 DOC 준비

내규: `/home/genos/DEV/data/corpus/internal` 아래 임의 깊이의 하위 폴더.
외규: 기존 `data/corpus/law,krx,kofia,expc,fsc,moleg,prec`와 각 manifest 그대로 사용.
폴더 경로와 문서 제목을 묶은 메타데이터를 유지한다.

`.doc`는 LibreOffice(또는 soffice)가 실행 경로에 있어야 한다. `pip install docling`과는
별도 시스템 프로그램이다. 설치 여부는 아래 명령으로만 확인하며 자동 설치하지 않는다.

```bash
command -v libreoffice || command -v soffice
```

없으면 관리자에게 승인된 LibreOffice 설치를 요청하거나 Word에서 DOCX로 저장한다.
DOC → DOCX는 원본과 별도인 빌드 폴더에서 수행한다. 원본 SHA, 변환본 SHA 및 변환 도구
지문을 conversion.json에 남긴다. 원문 좌표는 실제 파싱한 DOCX에 묶고 원본 DOC 계보를
메타데이터로 보존한다. 변환 실패·암호 문서·파싱/게이트 실패는 건너뛴다.
변환 후 기존 DOCX 파서(Docling 포함)와 등록 형식/태그를 그대로 사용한다.
실제 LibreOffice와 현장 DOC 전수 변환은 현장 검증이 필요하다.

## 실행 (패치 전 실행과 다른 새 run-id 사용)

리비전 필수 조건 제거 패치 이후에는 `GENOS_LLM_REVISION`과 `--model-revision`이 필요 없다.
기존 URL·키·서빙 ID 환경변수만 유지한다. [최신 설치 안내](GENOS_NO_REVISION.md).
기본 실행은 입력 점검만 한다. 입력 점검 통과는 변환/모델/적재 완료가 아니다.

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id doc-skip-001 --check-only
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id doc-skip-001 --execute --embed-batch-size 64 --max-calls 10000
```

기본값은 `--skip-failed`. 문서마다 구조화 → LLM 스키마 추출/검토/재추출 → 임베딩 →
DRAFT 적재/재열기 검증을 수행하고, 끝까지 완료한 문서만 성공으로 센다.
청크 일부가 실패한 문서는 문서 전체를 성공 목록에서 제외한다. 임베딩은 요청당 최대 64개.
`--max-calls`는 문서마다가 아니라 이번 배치 실행 전체의 LLM authoring 호출 한도다.
디스크 부족·권한 등 시스템 오류는 전체 중단할 수 있다. 모델 호출은 --execute 때만 한다.

## 비율과 결과

`[input_only]`는 입력 점검, `[e2e]`는 실제 적재까지의 비율이다.
진행 중에는 대기 건수가 있으므로 통과+건너뜀 비율이 100% 미만일 수 있다.
비율의 분모는 선택한 중복 제거 문서 + 문서 단위 입력 실패 항목이다.
ZIP·시스템 캐시·대체 본문 표현·중복 별칭은 제외 수를 따로 표시한다.
manifest 누락처럼 문서 수를 알 수 없는 소스 단위 오류는 source_errors에 별도 기록하며
비율에 임의 문서 1개로 넣지 않는다. source_errors가 있으면 비율이 100%여도 부분 완료다.

- 일부 성공/일부 건너뜀: `COMPLETED_WITH_SKIPS`, 종료 코드 0, `ok: false`.
- 모두 끝까지 통과하고 소스 오류 없음: `COMPLETED`, 종료 코드 0, `ok: true`.
- 성공 문서 0개: `FAILED`, 종료 코드 1. 전체 입력 점검 대상 0개도 종료 코드 1.

결과는 **문서별 독립 DRAFT**다. 기존 단일 통합 generation과 혼동하지 않는다.
완료 목록 `data/builds/doc-skip-001/batch-result.json`의 `generations`에 실제 경로가 나온다.
실물은 `data/builds/doc-skip-001/documents/<원본ID>/generation`에 있다.
실패 문서의 중간 산출물은 감사/재개용으로 남기며 성공 목록에 넣지 않는다.
이 catalog를 서비스 CURRENT로 지정하면 안 된다. 통합 운영 적재/활성화는 별도 작업이다.

```bash
tail -n 100 -f /home/genos/DEV/data/logs/doc-skip-001/progress.log
python3 -m json.tool /home/genos/DEV/data/builds/doc-skip-001/batch-result.json
```

로그: progress.log, events.jsonl, inventory-*.json, attempt-*.json.
실패 경로/단계/사유: batch-result.json records 및 문서 build_dir의 structure-errors.json/queue.
비밀값은 마스킹하지만 내부 경로·문서 제목·내용이 포함될 수 있으니 공유 전 확인한다.

## 재개 / 엄격 모드

같은 입력·코드·태그·스키마·리비전일 때만 재개한다. 성공 문서는 원본/결과를 검증하고
재사용하며 이미 끝난 추출·임베딩은 반복하지 않는다. 큐에서 재시도 한도를 모두 소진한
문서는 --resume만으로 자동 재추출되지 않는다. 파일/코드/설정을 고쳤으면 새 run-id로 실행한다.

```bash
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id doc-skip-001 --execute --resume --embed-batch-size 64 --max-calls 10000
```

기존 전체 중단/단일 DRAFT 방식은 새 run-id와 `--fail-fast`로 선택한다.
DOC 지원은 동일하지만 하나라도 실패하면 전체 적재를 중단한다.
두 모드의 같은 run-id를 혼용하지 않는다. OQL·질문답변·운영 승격은 실행하지 않는다.

변환 명령 참고: [LibreOffice 공식 CLI 안내](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html).
