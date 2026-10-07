# 실행·이행·검토 경로

현재는 격리 후보다. 아래 경로가 구현됐다는 사실과 MAIN/GENOS에서 켜졌다는 사실을 구분한다. 활성 릴리스 전환이나 운영 DB 이행은 실행하지 않았다.

## 후보 검증

WSL 저장소 `/home/jin/8-AGENT`에서 다음 명령은 동결 후보만 명시적으로 불러온다.

```bash
SHORTCUT_CANDIDATE_SNAPSHOT=revisions/rev-001/snapshot PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q 06_TOOLS/EXPERIMENTS/adr_0644 05_TESTS/CONTRACTS/test_unified_legal_agent.py 05_TESTS/CONTRACTS/test_unified_memory_recovery.py
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0644/integrated
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations --final
```

완료된 실제 모델 실행은 다시 실행하지 않는다. 실험 실행기는 기존 출력 디렉터리가 있으면 중단한다. 추가 모델 호출·후속 수정·재채점은 새 ADR에서 기록한다.

## 온라인 기록·조회·조직

- 기존 `/v1/rag/ask`: 모델·분류 전 수신 저장, 안정된 session/request ID, 같은 키의 다른 본문 충돌. 명시 investigation/branch 참조도 신뢰된 인증 필드에 포함한다.
- `/v1/rag/memory/query`: investigation/events/artifacts/facts/issues/relations/knowledge/legal-wiki 조회. 모든 조회는 현재 사용자·팀·문서 범위를 다시 검사한다.
- `/v1/rag/memory/command`: issue/assign/fact/relate/detach/publish/retire. expected revision과 명령 멱등 키를 검사한다. 일반 사용자가 검증 영수증을 만들 수 없다.

`PUBLISHED`는 조회 가능한 상태이며 법률 정답 승인 상태가 아니다. HINT/PROCEDURE/JUDGMENT의 조건·근거·검증 gate는 요청 시 별도로 적용한다.

## 야간 처리

기존 `pipeline.py action-memory build --mode shortcut-v4` 진입점을 확장했다. 선택 코드의 CLI에 명시 runtime/generation/model-profile/principal을 전달한다. 운영 활성화 후 해당 선택 코드에서 실행해야 하며, 저장소 루트의 기존 활성 코드로 실행하면 아직 이 후보 기능이 선택되지 않는다.

`--manual` 없는 작업은 한국시간00–06시만 동작한다. batch와 시간 예산, 단일 worker lock, lease 만료, 재시도3회와 격리 큐를 적용한다. 내부 데이터는 내부 transport만 사용하며, 외부 연구는 별도의 ExperimentClient 경로다.

한 사건에서 이미 처리된 불변 발언·도구 결과는 다시 모델에 보내지 않는다. 현재 사실·원문과 이전 지식의 비교용 요약 참조를 제공한다. 명시 CONTINUES/SAME_TOPIC 관계만 최대3개 사건 묶음으로 구성하며 각각의 사실은 분리한다. 관계 철회·원문 변경·새 정정은 커밋 전에 다시 확인한다.

페이지로 나눈 맥락에서는 완결된 법률 판단을 승인하지 않는다. 단일 기록이 예산을 넘으면 원본을 잘라 버리지 않고 명시 실패·격리 상태로 남긴다. 필요할 때 정확한 원기록을 조회해 분절한다.

## 명시적 이행·복구

기존 `pipeline.py unified-memory ... --store-version 4`에 다음 기능이 있다.

| 명령 | 입력·효과 |
|---|---|
| migrate | v3/native/corrected-memory/action-memory/query-shortcut의 명시 원본 snapshot → 새 v4 저장소. 원본은 보존 |
| migrate + artifact-manifest | 절대 경로·SHA256·문서 범위를 명시한 외부 artifact → scope별 내구 복사·ID mapping |
| backup | SQLite 일관 snapshot+참조 artifact+행 수/해시 manifest |
| restore | 검증된 백업 → 존재하지 않는 새 세대. 기존 정본 덮어쓰기 금지 |
| reconcile | DB 무결성·FK·artifact·trace·consumer cursor 대조 |
| store-plan | 새 세대 DB·artifact·현재 pointer 해시를 고정한 계획 |
| store-apply | 계획 및 `--confirm-store`로 선택 pointer 전환. 적용 전 drift 재확인 |
| store-rollback | 정확한 receipt+신규 기록 백업 보존 후 이전 pointer로 원복 |
| wiki-rebuild | DB에서 현재 권한·의존 확인 후 Markdown/JSON 재생성 |
| review-import | 별도 검토 파일+principal+`--confirm-review`. 현재 revision/hash에 결속. 법률 해석 검토 전 유효 SOURCE 검증 필수 |
| retention-inventory | 명시 승인 정책+등록된 백업 manifest → 원기록·artifact·trace·import·백업 연결 목록. 파괴적 삭제는 수행하지 않음 |

이행된 과거 기록은 `LEGACY_UNBOUND`다. 새 구조·원문·해석 검증을 자동 통과하지 않는다. v3 delta에서 빠진 사실은 이전 사실을 삭제하지 않고 미확인 revision으로 남긴다. native 도구·판단은 원기록과 첨부 해시를 보존해 조회할 수 있게 한다.

보존 일수와 법적 보존 의무는 이 구현이 임의 결정하지 않는다. 운영자가 승인한 정책, 백업 전체 위치, 실제 데이터 소유자의 삭제 지시가 있어야 파괴적 처리를 설계·실행할 수 있다. 현재 산출물에는 실제 사용자 데이터가 없으며 모든 예제는 공개 합성 사건이다.

## MAIN과 GENOS

ADR-0643의 실제 비교는 품질·지연·비용/사용량 기준을 통과하지 못했다. 따라서 후보 flags를 활성 MAIN에 복사하거나, 품질 예외 승인으로 우회하지 않는다. 정상 승격을 하려면 새 독립 평가와 기존 MAIN에 대한 정확한 코드 delta/provenance 및 정상 품질 gate를 갖춘 승격 계획이 필요하다.

GENOS 현장에는 접속하지 않았다. 내부 모델, 로컬 내구 디스크와 writer 운영, 실제 워크플로우 검증은 미확인이다. 배포 가능한 상태가 되면 GENOS.md 절차에 따라 별도 검증 ZIP·인계 TXT·세대/코드 receipt를 만든다. 현장 명령은 `python3`, 질의 검증은 워크플로우 테스트 화면을 사용한다. 코드 적용·저장소 이행·Git push·서빙 리비전 배포·질의 성공은 각각 별도 상태다.
