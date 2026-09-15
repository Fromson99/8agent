# GENOS 구조화 작업 최적화 실행

설치된 코드 파일을 교체하지 않는 opt-in 실행기다. 실행 프로세스에서만 작업 생성과
캐시 검증 함수를 대체한다. 원래 명령으로 돌아가면 기존 구현이 선택된다.
LLM 요청·스키마·원문·블록 순서·분할 크기를 바꾸지 않는다.

## 먼저 같은 한 문서 재측정

두 첨부를 DEV/TRANSFER에 둔다:

- genos_structure_optimized.py.txt (새 파일)
- genos_structure_timing.py.txt (앞서 보낸 동일 파일)

기존 원본/캐시/LLM 결과 폴더는 삭제하지 않는다. 다른 구조화 실행을 중단한 뒤:

```bash
cd /home/genos/DEV
.venv/bin/python -u TRANSFER/genos_structure_optimized.py.txt --from-run external-nfs-001 --rebuild
```

한 문서 선택·측정 옵션은 원래 timing 명령과 같다. `--from-run`은 그 실행의 LLM 문서
계획이 하나일 때만 자동 선택한다. 모호하면 `--document` 또는 표시된 `--cache` 경로로
지정한다. 기존 코드/캐시 파일은 덮어쓰지 않고 새 `structure-timing-*` 폴더에 만든다.

추가로 `최적화 동일성 확인 (성능 측정과 별도)`가 나온다. 이는 측정이 끝난 뒤 기존
반복문으로 소속 조문과 필요한 구조 문맥을 독립적으로 재계산하는 검사다. 이 시간이
진단 총 시간에는 들어가므로 성능 비교는 아래 개별 구간을 사용한다.

- `한 문서 신규 구조화 전체`: 기존 사진 159.4초와 같은 범위
- `source SQLite·LLM 작업 생성`: 기존 사진 138.9초와 같은 범위
- `sqlite_bytes`: 기존 사진 약 3.98GB
- `job_json_characters`: 기존 사진 약 36억 문자
- `counts.equivalence.status`: PASSED 확인

기존 사진은 같은 호스트의 앞선 실행 기록이며 순서·OS 캐시·다른 작업 부하를 통제한
벤치마크가 아니다. 단일 실행의 관측으로만 해석한다. 현장 개선 시간/비율은 아직 모른다.

결과 `summary.json`에는 ADR-0344/optimized, 최적화 파일·소비 코드 지문이 들어간다.
실패한 동일성 검사는 전체 결과를 FAILED로 만들며 LLM을 호출하지 않는다.
`parser_identity_matches=false`는 원래 캐시와 최적화 실행의 지문이 다르다는 뜻이다.
신규 구조화에서는 예상된 차이이며 원래 캐시를 덮어쓰지 않는다.

## 변경 내용과 보존 조건

1. 노드 span과 첨부 블록을 범위 인덱스로 만들어 순서대로 처리한다. 조문 우선,
   가장 좁은 span, 같은 길이에서 원래 노드 순서를 택하는 규칙은 동일하다.
2. 전체 노드는 기존 source_unit 테이블에 유지한다. 각 작업 JSON에는 해당 작업의
   본문 span과 겹치는 노드만 원래 순서로 넣는다. 기존 queue.prepare가 이미 수행하던
   span 필터를 먼저 적용하는 것이다. 작업 내 필요한 상위 문맥은 남는다. 여러 작업에
   공통 조상 노드가 반복되는 것은 호환성을 위해 허용한다.
3. 한 번의 verify_structure 호출에서 계산한 파일 해시를 source.json 대조에도 쓴다.
   호출 사이의 해시 재사용은 하지 않으므로 파일 변경 검사는 유지한다.

첨부만으로 소속된 블록도 기존과 같은 조문에 배정한다. 소비자의 최종 문맥은 기존처럼
span으로 필터링하므로 attachment-only 노드를 새로 추가하지 않는다.
알 수 없는 설치본의 배정/소비 필터는 AST 호환 검사에서 중단한다. 설치본의 점수 정책은
변경하지 않는다. 이후 LLM 추출·재시도·독립 검토 횟수는 그대로다.

## 전체 파이프라인에서 사용

한 문서 결과와 동일성 확인 후, 새 run-id로 구조화 단계만 실행한다:

```bash
.venv/bin/python -u TRANSFER/genos_structure_optimized.py.txt --pipeline --run-id external-opt-001 --exclude-internal --stage structure --execute
```

이 명령은 모델 호출이 없다. 최적화 지문이 달라 기존 구조화는 새 세대에 한 번 재생성된다.
그다음 동일 최적화 파일과 run-id를 계속 사용하면 캐시를 재사용한다. 기존의 4GB 캐시를
직접 변환하거나 중단된 LLM 실행에 섞지 않는다.

LLM 재개 자체는 별도 실행 선택이다. 전체 시간 문제 중 LLM의 호출 수·출력 잘림은
이번 최적화로 해결됐다고 판단하면 안 된다. 모델 호출을 원할 때만:

```bash
.venv/bin/python -u TRANSFER/genos_structure_optimized.py.txt --pipeline --run-id external-opt-001 --exclude-internal --stage llm --execute
```

마지막 vector도 같은 실행기를 사용한다. 원래 실행기로 rollback하면 기존 지문의 캐시를
다시 사용하며 최적화 캐시와 혼합하지 않는다. 이미 존재하는 run-id에 코드 변경을 섞으면
기존 파이프라인의 계획/해시 일치 검사가 차단한다. 신규 설치/운영 MAIN 전환은 없다.
