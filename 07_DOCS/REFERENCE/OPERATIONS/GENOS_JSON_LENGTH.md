# GENOS JSON / 출력 길이 패치

증상: HTTP 200인데 content의 ```json 포장으로 파싱 실패하거나 finish_reason=length,
8192 토큰에서 출력 잘림. 이번 변경은 오프라인 구축 경로만 적용한다.

- 정확히 한 개의 JSON 코드블록을 해석한다. 일반 설명/think 태그/미완성 JSON을 수선하지 않는다.
- 저장된 응답과 해시는 그대로 보존한다. validation/feedback/handoff에서 같은 파서를 사용한다.
- 빈 응답, 모델 불일치, 거부, 도구 응답, stop 아닌 종료는 통과시키지 않는다.
- 기본 LLM 원문 조각은 1500자. 전체 원문과 원래 문자 좌표를 보존한다.
- length일 때 같은 작업/단계의 출력 한도를 8192→16384→32768까지 늘린다.
  --max-attempts와 --max-calls를 그대로 준수한다. 상한에서도 실패하면 해당 문서가 건너뛰어진다.
  잘림 응답에 없는 데이터를 생성하거나 부분 성공으로 처리하지 않는다.
- --json-mode prompt (기본): 기존 서버 호환. 스키마는 프롬프트에 넣고 로컬에서 엄격 검증한다.
  서버가 지원한다고 확인한 경우 json_object 또는 json_schema를 명시할 수 있다.
  미지원 API 옵션에서 자동 우회하지 않는다. json_schema는 기존 strict 스키마 전송이다.
- 모델이 32768 출력 토큰/입력+출력 컨텍스트를 지원하는지는 현장 설정에 달려 있다.
  서버가 거절하면 지원 한도로 --max-output-tokens를 낮추고 --segment-chars를 더 줄인다.
  입력 축소는 호출 수를 늘릴 수 있다. 이 패치는 모든 문서 성공 보장이 아니다.

## 설치

실행 중인 파이프라인은 Ctrl+C 후 종료를 확인한다. ZIP과 설치 TXT를 TRANSFER에 둔다.

```bash
cd /home/genos/DEV/TRANSFER &&
base64 -d genos_apply_json_length.sh.b64.txt > genos_apply_json_length.sh &&
bash genos_apply_json_length.sh --install-only
```

원본/키/URL/현장 genos.py/의존성/Git/CURRENT/기존 빌드 보존. 알 수 없는 수정은 사전 중단.
설치 백업은 runtime/patch-backups/genos-compatible-*에 저장된다.

## 점검과 실행

새 큐 런타임과 작은 조각을 사용하므로 이전 external-001에 --resume하지 않는다.
새 ID로 시작한다. 이전 결과/실패 기록은 보존된다.

```bash
cd /home/genos/DEV &&
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-json-001 --exclude-internal --check-only
```

```bash
cd /home/genos/DEV &&
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-json-001 --exclude-internal --execute --segment-chars 1500 --max-tokens 8192 --max-output-tokens 32768 --json-mode prompt --embed-batch-size 64 --max-calls 10000
```

이번 새 실행을 중단 후 재개할 때는 위 실행 명령에 --resume만 추가한다.
스키마/코드/입력/json-mode/토큰상한/분할 크기를 바꾸면 다시 새 ID를 사용한다.
서버 구조화 출력이 확인되면 --json-mode json_object 등을 새 실행에서 선택한다.
운영 답변/OQL/자동 활성화는 수행하지 않으며 결과는 문서별 DRAFT 목록이다.

로그 data/logs/external-json-001/progress.log, 결과 data/builds/external-json-001/batch-result.json.
큐 documents/*/queue/queue.sqlite의 response는 원 응답 표현이며 코드펜스가 남는 것이 정상이다.
추출 candidate/검증 parsed/handoff bundle이 파싱된 데이터다. 원응답을 일반 json.loads로
재점검하는 과거 진단 스크립트는 코드펜스를 여전히 문법 오류로 표시할 수 있으니
attempt.state=VALIDATED 및 job 상태와 함께 판단한다.

롤백: 종료 후 설치 receipt에 나열된 변경 파일만 백업으로 복구한다.
이전 런타임/옵션의 큐는 그 버전에서만 재개하며 서로 섞지 않는다.
