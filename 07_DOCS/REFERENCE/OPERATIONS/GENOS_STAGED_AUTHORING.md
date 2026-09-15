# 공통 데이터 파이프라인 / GENOS 단계별 추출

최신 메일의 한글 진행 로그/JSON 처리/외규 전용/DOC 지원을 포함한 누적 코드 패치다.
원본·환경변수·현장 genos.py·Git·기존 결과·서비스 CURRENT를 바꾸지 않는다.
실제 GENOS 모델 호출은 현장에서 실행해야 한다. 로컬 검증은 합성 문서/가짜 provider 계약 검사다.

## 달라지는 점

`--extraction-mode staged`: 같은 원문 조각을 4단계로 처리한다.

1. 개념·언급·근거
2. 절·역할 (이전 ID 참조)
3. 규칙·단서·관계 (이전 ID 참조)
4. 원문 커버리지 → 코드 병합 → 기존 전체 스키마·근거·참조 검사

그 뒤 별도의 전체 리뷰 → 임베딩 배치 → 문서별 DRAFT 적재다.
스키마 정의는 기존 SSOT에서 각 단계에 필요한 필드와 참조 정의만 뽑는다. enum/필수 필드를 완화하지 않는다.
뒤 단계는 앞 단계의 ID를 참조한다. 코드가 의미나 빈 역할을 임의로 채우지 않는다.
형식 오류는 해당 단계만 재시도한다. 전체 의미 검증 실패는 오류 소유 단계와 그 이후 결과를
무효화한다. 위치가 불명확한 오류/리뷰 지적은 첫 단계부터 재추출한다. 이미 쓴 재시도 횟수는 초기화하지 않는다.
부분 단계 성공만으로 적재하지 않는다. 스키마 오류/잘림은 분할 후에도 발생할 수 있다.
개념의 미래 definition_rule_ids는 후속 rules 단계가 같은 ID로 정의하고 마지막에 검증한다.

모든 실제 호출은 queue.sqlite의 attempt에 개별 저장한다. 원요청/원응답/usage/latency/실제 모델 ID를 보존한다.
stage_checkpoint는 통과한 응답만 가리킨다. handoff 리뷰 영수증의 staged_extraction은 실제 네 요청/응답과
HOST_DETERMINISTIC_MERGE 표시를 포함한다. 합성 결과를 한 번의 모델 원응답으로 위장하지 않는다.

## 설치 (먼저 기존 실행을 Ctrl+C로 중단)

이번 메일의 ZIP과 b64.txt를 `/home/genos/DEV/TRANSFER`에 함께 업로드한다. unzip은 필요 없다.

```bash
cd /home/genos/DEV/TRANSFER
base64 -d genos_apply_staged_authoring.sh.b64.txt > genos_apply_staged_authoring.sh
bash genos_apply_staged_authoring.sh --check-only
bash genos_apply_staged_authoring.sh --install-only
```

알 수 없는 현장 수정은 자동으로 덮어쓰지 않고 변경 전에 모두 보고한다. 기존 코드 백업은
runtime/patch-backups/genos-compatible-*/receipt.json에 기록한다. 이 패치는 모델 호출을 하지 않는다.

## 외규 전체 실행 (내규 DRM 제외)

코드/옵션이 바뀌었으므로 기존 external-log-001/external-001에 덮어쓰거나 resume하지 않는다.
아래 두 명령은 같은 새 ID를 쓴다. check-only는 모델을 호출하지 않고 build 디렉터리를 만들지 않는다.

```bash
cd /home/genos/DEV
.venv/bin/python 06_TOOLS/pipeline.py build-data --run-id external-staged-001 --exclude-internal --extraction-mode staged --check-only
.venv/bin/python 06_TOOLS/pipeline.py build-data --run-id external-staged-001 --exclude-internal --extraction-mode staged --execute --segment-chars 1500 --max-tokens 8192 --max-output-tokens 16384 --max-attempts 3 --embed-batch-size 64 --max-calls 10000
```

기존 GENOS 명령도 똑같은 구현을 실행한다. 둘 중 하나만 실행한다:

```bash
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-staged-001 --exclude-internal --extraction-mode staged --execute --segment-chars 1500 --max-tokens 8192 --max-output-tokens 16384 --max-attempts 3 --embed-batch-size 64 --max-calls 10000
```

내규를 함께 처리하려면 DRM 해제된 승인 원본을 data/corpus/internal 아래에 넣고
`--exclude-internal`을 빼며 새로운 run-id를 쓴다. 외규 위치는 기존 law/krx/kofia/expc/fsc/moleg/prec 그대로다.
`--segment-chars`는 LLM 입력 분할, `--max-tokens`는 단계별 출력 상한,
`--embed-batch-size 64`는 임베딩 요청당 개수다. 서로 다른 제한이다.
`--max-calls`는 이번 실행의 전체 LLM 호출 한도다. 단계별 4회+리뷰와 재시도 때문에
대형 외규 전체를 10000회로 끝낸다고 보장하지 않는다. 한도 도달/중단 시 결과와 로그를 보고 재개한다.

## 중단·재개·로그

Ctrl+C로 중단한다. 코드/원본/모델/옵션을 바꾸지 않았다면 위 execute 명령 끝에 `--resume`만 추가한다.
받아 저장한 단계 응답은 재호출하지 않는다. 응답 저장 전에 프로세스가 죽으면 해당 호출은 반복될 수 있다.
이미 FAILED로 재시도 예산을 모두 쓴 청크는 resume만으로 무한 재시도하지 않는다.

```bash
cd /home/genos/DEV
tail -f data/logs/external-staged-001/console.log
```

상세: data/logs/external-staged-001/progress.log, events.jsonl, current-status.json.
문서별 원응답: data/builds/external-staged-001/documents/<원본ID>/queue/queue.sqlite.
최종 문서 통과/건너뜀: data/builds/external-staged-001/batch-result.json.
단계 검증 통과와 문서 적재 완료는 다르다. 실패 문서는 기록하고 건너뛰며 부분 실패를 전체 성공이라고 표시하지 않는다.

롤백: 새 ID에 `--extraction-mode single` 사용 (기존 기본값). 운영 RAG/engine-host legal-authoring
등록·승격은 이 데이터 명령과 별개이며, 서비스 활성화는 하지 않는다.
