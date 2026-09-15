# GENOS

현재 통합 패키지의 코드 서빙 배포는 [코드 서빙 배포 내부 지식](../../07_DOCS/REFERENCE/OPERATIONS/GENOS_CODE_SERVING_CURRENT.md)을 먼저 읽는다. 저장소 URL·Git 인증·코드 API 키·모델키, 코드 push와 영속 데이터 경로를 구분한다. 아래는 기존 release-bound 활성화 계약이며 standalone 인계본에 자동 적용됐다고 가정하지 않는다.

GENOS는 다음 포인터만 활성화한다.

```text
ACTIVE_RELEASE
  ├─ code revision/profile
  ├─ active source-set ID/hash
  ├─ semantic/authority generation
  ├─ lexical/vector index fingerprint
  └─ promotion/apply/rollback receipt
```

활성화 후보는 `release-manifest-v1`으로 검증한다. 코드 ZIP hash,
MAIN generation/state/receipt, SourceSet ID/generation/hash/반출 정책, semantic·authority
generation, lexical/vector index fingerprint, schema/hash/ACL/smoke/provenance receipt가
하나라도 다르면 fail-closed한다. vector index는 embedding model fingerprint가
없으면 활성화할 수 없다.

schema/hash/ACL/smoke/provenance 검증 영수증은 릴리스 manifest에 넣지
않고 `release-activation-plan-v1`에 넣는다. 그래야 영수증이 릴리스
manifest hash를 검증해도 순환 hash가 생기지 않는다. plan은 현재 active
pointer의 generation/hash와 이전 release ID를 고정하여 stale 활성화를 차단한다.

반입물은 `QUARANTINE → hash/schema/ACL/code 검증 → immutable install → smoke →
pointer swap`을 거친다. `service.py`는 GENOS 계약상 루트에 유지한다.

`lawrag.platform.release`는 후보와 활성화 plan을 검증만 한다. `ACTIVE_RELEASE`
쓰기는 GENOS 영속 볼륨의 별도 deployment adapter가 compare-and-swap과
append-only apply/rollback receipt를 갖춘 뒤 구현한다.
