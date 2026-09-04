# 운영 런타임과 ADR 연구 후보 경계

## 원칙

운영 API는 `lawrag.runtime.registry`에 등록된 production component만 실행한다. ADR 후보는
`lawrag.research` 아래에서만 불러오며 운영 코드가 후보 ID나 모듈 경로를 문자열로 선택하지
않는다.

```text
운영 요청
  → lawrag.runtime.registry
  → lawrag.runtime.components.<production-profile>
  → core RAG

ADR 실행기
  → lawrag.research.profiles 또는 ADR snapshot
  → core runtime에 research_profile 객체를 명시적으로 주입
```

`legalclosure_runtime.retrieve(..., integrated_research_enabled=True)`는
`research_profile` 객체가 없으면 fail-closed한다. API와 내규 비교 운영 경로는 이 인자를
전달하지 않는다.

## ADR에서 코드 변경하기

1. `scripts/adr_structure.py new`로 ADR을 먼저 선점한다.
2. 바꿀 운영 파일만 snapshot한다.

```bash
.venv/bin/python scripts/adr_candidate.py snapshot \
  --adr docs/adr/ADR-NNNN-slug \
  --candidate-id my-candidate \
  --source lawrag/core/rag/legalclosure.py \
  --source lawrag/core/rag/legalclosure_runtime.py
```

3. `lawrag/research/candidates/adr_NNNN/my-candidate/snapshot/` 복사본을 수정한다.
   production에 아직 없는 신규 파일은 최종 상대경로에 만든 뒤 명시적으로 등록한다.

```bash
.venv/bin/python scripts/adr_candidate.py register \
  lawrag/research/candidates/adr_NNNN/my-candidate \
  --target lawrag/runtime/components/new_component.py \
  --upstream-state absent
```

   `absent` 등록은 canonical target이 실제로 없을 때만 가능하고 upstream path/hash를 null로
   남긴다. 이미 있는 파일을 뒤늦게 추가할 때는 `--upstream-state present`를 사용한다.
4. 수정이 끝난 시점에 `adr_candidate.py freeze <candidate-directory>`로 수정본 hash와
   append-only revision을 고정하고, `adr_candidate.py validate <candidate-directory>`로 검사한다.
5. 실험 runner는 research candidate를 명시적으로 import한다. 운영 registry에는 등록하지 않는다.
6. Accepted·out-of-sample·decision-eligible 결과만 필요한 코드를
   `lawrag/runtime/components/`로 복사·정리하고 production profile을 등록한다.
7. `rag_main_promotion.py prepare --runtime-profile <id>`와 명시 승인 `apply`로 교체한다.

운영 rollback은 기존 MAIN generation과 append-only receipt를 그대로 사용한다.

## GitLab이 필요한가

이 경계에는 GitLab 서버가 필요하지 않다. 현재 단일 Git 저장소가 source hash, ADR 계보,
review, branch와 rollback을 이미 제공한다. GitLab은 다수 사용자의 Merge Request 승인,
보호 브랜치, CI runner, 대용량 artifact/object storage가 실제로 필요할 때 원격 중앙 서비스로
붙이는 선택지다. 애플리케이션 내부에 GitLab을 설치하거나 후보 로더와 결합하지 않는다.

현재 `.gitignore`는 대용량 로컬 원장인 `docs/adr/` 전체를 제외한다. 따라서 GitLab을 설치해도
ADR 원문·artifact가 자동으로 원격 보존되지는 않는다. 후보 코드와 `candidate.json`은
`lawrag/research/candidates/` 아래라 일반 Git 관리 대상이다. ADR까지 중앙 보존하려면 작은
manifest/README만 선별 추적하고 대용량 artifact는 Git LFS 또는 object storage로 보내는 별도
저장 정책을 먼저 정해야 한다.
