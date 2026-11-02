# 자유 온톨로지 작업공간

2026-10-30. 작업 코드에 연결한 기능이다. 선택 MAIN129·현장 GENOS의 활성화를 뜻하지 않는다.

## 사용 흐름

기존 Streamlit 온톨로지 관리의 **자유 작업공간**에서 기록을 저장한다. 제목·설명·보기·탐색 링크는 자유롭게 편집할 수 있다. 프로필·상위 법률 분류·용어집 없이 시작할 수 있으며, 원기록을 덮어쓰지 않는다.

항목의 **연결·주제 보기**에서 다른 항목으로 이동하고 탐색 연결을 추가·제거하거나 여러 주제 보기에 배치한다. 보기가 많으면 이름으로 검색한다. 이 편집은 문장의 판본과 승인된 의미를 바꾸지 않는다.

원기록과 실제 원문을 함께 제공해 변경안을 만들면 연결된 생성기가 새 항목·문장·관계를 제안한다. 변경안 적용은 초안 저장이다. 원문 근거가 없는 문장도 초안으로 보존되며, 표시 위치를 바꾸는 일은 문장의 판본이나 기존 게시본을 변경하지 않는다.

재사용할 문장을 선택하고 **재사용 준비·승인·게시**를 연다. 승인된 기존 프로필과 실제 원기록의 정규화를 사용해 원문만 독립 분석한 뒤 의미 구조를 제안한다. 기존 v1 컴파일러로 조립하며, 선택 문장과 다른 텍스트를 자동 채택하지 않는다. 다른 해석이 필요하면 새 문장으로 검토한다. 미확인·상충은 결과에 남고 법률 정답이나 충분성으로 인증되지 않는다.

검토자는 정확한 컴파일 판본을 승인한다. 승인→게시 준비→현재 원문·소비 경로 검증→활성화를 기존 포트로 수행한다. RAG는 원문이 도착했을 때 승인 게시본을 조회하고, 현재 evidence ID에 다시 연결해 기존 ASSESS에 전달한다. 요청 도중이나 재개 시 철회된 게시본은 사용하지 않는다. 해당 해석을 보고 이미 만든 후보 답변도 그대로 확정하지 않는다. 확보한 원문과 실패 이력은 보존한다.

## 설정

기존 `GENOS_RAG_ONTOLOGY_CONFIG`의 `ontology-connection-v1` 설정에 아래 항목을 추가한다. 이는 추가 필드 예시이며 독립 실행 설정이 아니다. 실제 operator ID·namespace·snapshot·ACL은 관리자가 정한다.

```json
{
  "workspace": {
    "namespace": "your-authorized-workspace",
    "source_snapshot": "your-selected-source-snapshot",
    "acl_ref": "your-workspace-access-policy"
  },
  "operators": {
    "your-authenticated-operator": {
      "document_ids": ["your-authorized-document"],
      "workspace_publish": true
    }
  },
  "workspace_runtime_scopes": [
    {
      "namespace": "your-authorized-workspace",
      "source_snapshot": "your-selected-source-snapshot",
      "acl_ref": "your-workspace-access-policy"
    }
  ]
}
```

`workspace`를 생략하면 기존 `domain_profile`의 namespace/snapshot/ACL을 사용한다. 축적에는 승인 프로필이 필요하지 않다. 컴파일 시에는 workspace와 domain_profile의 세 값이 같아야 하며, 기존 승인 프로필과 glossary 연결을 사용한다.

`workspace_publish`는 신규 workspace 게시 활성화·철회 권한이다. 편집 권한만 있는 사용자는 게시본을 철회할 수 없다. `workspace_runtime_scopes`는 **배포 관리자가 해당 소비자에 허용한 공유 작업공간 목록**이며, 사용자 요청에서 지정하지 않는다. 기본은 빈 목록이다. 개별 요청의 문서 권한 검사를 추가로 통과해야 한다. 같은 프로세스에 서로 다른 팀을 함께 서비스할 경우 이 공유 grant를 각 팀에 공통 허용되는 범위로 제한하거나, 인증된 요청별 repository에 workspace_scopes를 주입한다. 개인/다른 팀 자료를 공통 grant로 열지 않는다.

기존 온톨로지 ON/OFF 설정은 그대로다. `workspace_runtime_scopes`만 설정해 기존 OFF를 자동으로 ON으로 바꾸지 않는다. Gold의 별도 mapped repository를 주입하는 환경도 동일하게 명시적인 workspace_scopes를 부여해야 한다. `scope_key()`는 namespace/ACL/source snapshot의 결정적인 식별자다.

기존 로컬·Dataiku 관리 폴더와 WORK/EVT/PUB/HEAD/ANC를 재사용한다. 신규 물리 테이블은 필요하지 않다. 원격 Oracle authoring은 `configuration.workspace_workflow(actor=..., ports={"workflow": existing_authorized_workflow})`, `domain_workflow(..., ports={"workflow": ..., "glossary": authenticated_glossary_port})`로 기존 인증된 Gold/Silver 포트를 주입할 수 있다. 기본 원격 glossary factory는 자동 연결되지 않으므로 이 주입을 설치 환경에서 검증해야 한다. 로컬 SQLite fallback으로 대체하지 않는다.

## 같은 CLI에서 실행

모든 명령은 기존 `06_TOOLS/pipeline.py ontology-work` 아래에 있다.

| 명령 | 입력·결과 |
|---|---|
| `workspace-ingest --input FILE` | 실제 export envelope 또는 기존 import_payload 명세 → 불변 RAW |
| `workspace-propose --input FILE` | change_id/raw_ids, 선택 item_ids, query, originals → 변경안; 아직 미반영 |
| `workspace-apply --input FILE` | change_id/operations/expected/raw_ids/proposal_receipt → 원자적 초안 commit |
| `workspace-list --kind ENTRY --query TEXT` | 권한을 검사한 metadata 목록. 다음 목록은 반환 cursor를 파일에 저장해 `--cursor FILE` |
| `workspace-status --bundle ID [--revision N]` | 정확 항목·이전 판본 |
| `workspace-lint --bundle ID` | 현재 출처·참조·미확인 검사; 법률 정답 판정 아님 |
| `workspace-compile --input FILE` | statement_ids/purpose/profile_id/profile_work_hash → 기존 v1 컴파일 묶음 |
| `workspace-preview --bundle ID` | 현재 선택 문장·원문을 재검증한 조립 결과 |
| `workspace-reconcile --work-hash HASH` | SAVE_UNCONFIRMED의 같은 객체를 확인·반영; 모델 재전송 없음 |

기존 `domain-review`, `stage-publication`, `verify-publication`, `activate-publication`이 workspace 컴파일 묶음에도 연결된다. 일반 `publish` 또는 저수준 `activate_staged`로 workspace 의존 등록을 우회할 수 없다. 생성·검토·게시의 성공 상태는 서로 다르다.

변경 연산은 CREATE_ENTRY/REVISE_ENTRY, ADD_STATEMENT/REVISE_STATEMENT, CREATE_VIEW/REVISE_VIEW, LINK/UNLINK, MOVE_MEMBERSHIP, MARK_DISPUTED/RETRACT다. 새 객체는 `@local_name`으로 참조하고 서버가 change_id와 scope에 결속한 ID를 만든다. 기존 객체를 수정하거나 참조할 때는 `expected`에 해당 revision/work_hash를 제시한다. 의미 없는 자동 재시도나 latest 덮어쓰기는 하지 않는다.

실제 입력 모양과 정상·반례는 [계약 검사](../../../05_TESTS/CONTRACTS/test_wiki_workspace.py)에 있다. [설계용 합성 예시](../ARCHITECTURE/ONTOLOGY_V4/WIKI_GROWTH_COMPILATION_20261030/CONTRACT_EXAMPLES.json)는 설명용이며 현재 CLI 입력으로 직접 실행하지 않는다.

## 저장·복구·철회

- 내용주소 JSON을 먼저 저장한 후 namespace catalog·항목·변경 영수증·역의존·필요한 철회를 같은 SQL transaction으로 확정한다. S3와 SQL의 분산 트랜잭션은 전제하지 않는다.
- SQL 실패 후 남은 미참조 객체는 성공한 지식 갱신이 아니다. commit 응답이 유실된 경우 같은 operation/hash를 조회하며, UNKNOWN 모델 요청을 다시 보내지 않는다.
- 제목·설명 수정은 문장을 자동으로 고치지 않는다. 문장 편집은 새 판본이며 기존 승인본은 유지한다. 명시적인 DISPUTED/RETRACTED는 해당 문장 판본들을 사용한 게시본의 활성 포인터를 함께 중지한다.
- 현재 선택 문장이 바뀌었으면 이전 projection을 새로 활성화하지 않는다. 새 선택을 컴파일·검토한다. 철회된 문장을 복원하려면 새 문장과 새 검토를 만든다.
- metadata는 16개 고정 shard, shard당 최대 1,024항목, 객체당 기존 2,000,000바이트 한도를 사용한다. 초과 시 명시적인 분할 이행이 필요하며 자동 절삭하지 않는다. 목록 cursor는 catalog 판본과 권한에 결속된다.
- 생성 단계는 기존 `_job`의 최초+보완1회, 결과불명 보존·재개 정책을 사용한다. 한 projection은 실제 raw 최대16개와 문장 최대32개, 새 물리 호출에 대한 전체600초 기한을 갖는다. 부분 완료 후 재개해도 기한이 초기화되지 않는다. 형식 검사는 의미 품질을 보장하지 않는다.
- DP=oracle에서 신규 workspace 생성기의 전체 wire 자료는 상세 NFS 정책을 따른다. 구조화 결과·상태는 작업 정본에 보존한다. NFS 미설정·QUEUED는 내구 기록 성공으로 표시하지 않으며, 진단 저장 실패로 모델을 다시 보내지 않는다.

## Dataiku 수집과 운영 경계

기존 `ingest_agent_events.py`에 `ingest_journal_page`와 `ingest_workspace`를 추가했다. 기존 ONTOLOGY_WORK_INPUT 경로는 유지한다. `ontology_ingest_mode=workspace`이면 인증된 raw export envelope dataset을 기존 recipe로 가져온다. 전체 journal 페이지 수집은 모든 event의 저장 성공 뒤에만 다음 checkpoint를 반환한다. 반복 반입은 같은 원본으로 결속된다. 이 단계는 자동 내용 승인·Gold 게시를 하지 않는다.

현재 공유 workspace grant, 실제 Oracle writer·glossary 주입, Dataiku 관리 폴더·NFS mount는 현장 연결 검증이 필요하다. 코드와 합성 계약 검사를 실제 법률 정확성·현장 성능·전체 데이터 이행 완료로 해석하지 않는다. 선택 MAIN의 전환은 저장소의 별도 승격 절차를 따른다.

되돌릴 때 workspace 메뉴/authoring 설정과 runtime grant를 중지할 수 있지만, 이미 생성한 게시본의 철회 확인 기능과 기록은 유지해야 한다. MAIN129 v3 BODY 작성 뒤 v2 전용 reader로 되돌리지 않는 기존 제약도 유지한다.
