# GENOS 외규 전용 데이터 적재

이번 ZIP/설치기는 no-revision 메일 이후 누적 패치다. URL/키/현장 genos.py,
의존성 파일, 원본, 기존 빌드, Git, CURRENT는 변경하지 않는다. 실행 중인
파이프라인이 있다면 Ctrl+C로 멈추고 프로세스 종료를 확인한 후 설치한다.

메일의 ZIP과 설치 TXT를 /home/genos/DEV/TRANSFER에 업로드한다.

```bash
cd /home/genos/DEV/TRANSFER &&
base64 -d genos_apply_external_only.sh.b64.txt > genos_apply_external_only.sh &&
bash genos_apply_external_only.sh --install-only
```

내규 제외 옵션: `--exclude-internal`. 기본값은 기존처럼 내규+외규다.
내규는 순회/해시/파싱/모델 호출 대상에서 제외한다. 원본을 이동/삭제하지 않는다.
선택 범위는 inventory, batch-plan, attempt 로그에 남는다. 내규는 통과/건너뜀 분모에
포함하지 않는다. 외규의 DRM/지원 불가 문서는 기존처럼 실패를 기록하고 건너뛴다.

먼저 점검 (모델 호출 없음):

```bash
cd /home/genos/DEV &&
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-001 --exclude-internal --check-only
```

외규 전체 적재 (LLM/임베딩 실제 호출):

```bash
cd /home/genos/DEV &&
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-001 --exclude-internal --execute --embed-batch-size 64 --max-calls 10000
```

외규 7종 law,krx,kofia,expc,fsc,moleg,prec가 대상이다. 검사 통과는 실제 파싱/모델/적재
성공이 아니다. LLM 추출·검토·재추출 후 임베딩하며 결과는 문서별 DRAFT catalog다.
통합 운영 세대/질문답변/자동 활성화는 포함하지 않는다.

기존 doc-skip-001을 재사용하지 않는다. external-001도 이미 구축했다면 새 ID를 사용한다.
이번 옵션으로 시작한 실행만 같은 명령에 `--resume`을 추가하여 재개한다.
재개 시에도 `--exclude-internal`을 유지한다. 코드/입력/스키마가 바뀌면 새 ID가 필요하다.
`--max-calls 10000`은 실행당 LLM 호출 한도이며 전수 완료 보장이 아니다.

로그: `data/logs/external-001/progress.log`, `events.jsonl`, `attempt-*.json`.
결과: `data/builds/external-001/batch-result.json`과 `documents/*/generation`.
Ctrl+C로 중단한다. 설치 백업은 `runtime/patch-backups/genos-compatible-*`에 남는다.
롤백은 설치 receipt에 나열된 파일만 백업으로 복구하며 원본/이전 산출물은 지우지 않는다.
