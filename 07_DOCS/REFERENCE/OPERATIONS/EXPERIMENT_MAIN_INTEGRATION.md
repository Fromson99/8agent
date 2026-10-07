# 실험 후보를 로컬 MAIN에 통합할 때의 보존 검사

로컬 RAG 릴리스 준비 진입점은 `rag_main_promotion.py prepare` →
`semantic_runtime.control.prepare`다. 현재 활성 릴리스가 있는 경우 이 명령은
`validation.json`의 `integration` 선언을 필수로 검사한다. 검사에 실패하면 새
릴리스 디렉터리를 지우고 manifest를 발행하지 않는다. `apply`는 기존처럼
준비 당시 활성 포인터의 해시가 그대로일 때만 실행된다. 이미 발행된 과거
릴리스와 롤백은 이 새 규칙으로 다시 쓰지 않는다.

## 실험 코드의 출발점

`adr_candidate.py snapshot`/`import-present`는 지정한 **현재 작업 트리 파일만**
`02_BACKEND/lawrag/research/candidates/`의 연구 후보로 복사한다. 전체 MAIN
릴리스를 복사하는 명령은 아니다. `register --upstream-state absent`는 신규
파일을 등록한다. 후보 수정 후 `freeze`는 복사 당시 작업 파일의 해시와
스냅샷 재고를 확인하고 불변 revision을 만든다. 이 검사는 실험의 재현성을
위한 것으로, 실험이 끝난 뒤 바뀐 활성 MAIN과의 호환성을 뜻하지 않는다.

## 승격 준비

1. 현재 `ACTIVE_RELEASE.json`과 그 `release.json`을 읽어 기준 릴리스를 정한다.
   활성 릴리스의 `code_root`를 **별도 stage**에 복사하고, 채택할 후보의
   `revisions/<rev>/snapshot/`에서 필요한 파일만 해당 경로에 이식한다.
   실험 snapshot 디렉터리 전체를 `--code-root`로 사용하지 않는다.
2. 새 파일에 맞는 엔진 pin과 `PIPELINE.json`을 갱신하고, 변경 범위에 맞는
   계약·회귀 검사를 수행한다. 서로 다른 시점에 같은 파일을 바꿨다면 먼저
   현재 MAIN을 기준으로 후보를 다시 만들고 검증한다.
3. `prepare`에 `--integration-preview <path>`를 붙이면 릴리스를 발행하지 않고
   활성 릴리스와 stage의 파일별 차이 템플릿을 쓴다. 각 변경의 `reason`을
   검토해 채운 뒤 `validation.json`에 `integration`으로 넣는다. 빈 이유는
   통과하지 않는다. 후보에서 온 변경은 `candidate`에 `candidate.json`의
   SHA-256, revision ID와 revision SHA-256을 묶는다.
4. 같은 stage로 `prepare`를 다시 실행한다. 후보에 등록되지 않은 파일의 변경도
   각각 선언해야 한다. 누락·추가·해시 차이·활성 MAIN 변경은 실패한다.
   통과 결과는 새 `release.json`의 `integration`에 들어간다.

preview와 실제 준비는 같은 인자를 쓰며, 첫 실행에만 `--integration-preview`를
붙인다. 기존 실행 명령의 `--code-root`는 격리 stage, `--generation`은 명시한
데이터 세대여야 한다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py \
  --root /home/jin/8-AGENT prepare \
  --code-root /path/to/isolated-stage --generation /path/to/selected-generation \
  --release-id reviewed-release-id --authorization /path/to/authorization.json \
  --validation /path/to/validation.json \
  --integration-preview /path/to/integration-draft.json
```

선언 형식은 다음과 같다. `changes`는 preview가 산출한 **실제 변경 전체**다.

```json
{
  "schema_version": "local-release-integration-v1",
  "base_release_manifest_sha256": "<ACTIVE release.json SHA-256>",
  "changes": [
    {"path": "02_BACKEND/semantic_runtime/legal_agent/example.py",
     "before": "<현재 MAIN 파일 SHA-256 또는 null>",
     "after": "<stage 파일 SHA-256 또는 null>",
     "reason": "채택할 실험 변경과 필요한 배선"}
  ],
  "candidate": {
    "manifest_path": "02_BACKEND/lawrag/research/candidates/adr_NNNN/name/candidate.json",
    "manifest_sha256": "<candidate.json SHA-256>",
    "revision_id": "rev-001",
    "revision_sha256": "<candidate revision SHA-256>"
  }
}
```

실험 후보가 아닌 사용자 지시 릴리스라면 `candidate`는 `null`이다. 그래도 활성
릴리스 대비 모든 파일 변경을 선언해야 한다. 후보가 있으면 등록된 각 파일의
`upstream_sha256`이 **현재** MAIN 파일과 같아야 하고, stage의 결과도 해당
frozen revision의 SHA와 같아야 한다. 그래서 오래된 후보가 이후의 같은 파일
수정을 덮어쓸 수 없다. 변경하지 않은 파일은 자동으로 보존 검사한다.

예를 들어 ADR-0590 rev-002의 두 파일은 검사 당시 generation 37과 원본 해시가
맞아 코드 통합 검사만 통과했다. 이 ADR은 `decision_eligible=false`이고 실제
검색·모델·지연 검증이 없으므로 이 사실은 승격 가능 판정이 아니다. 이 검사는
파일·계보·범위의 손실을 막는 장치이며 법률 답변 품질, 병행 변경의 의미 충돌,
GENOS 배포까지 보증하지 않는다.
