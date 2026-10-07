# 원문 탐색·선택·게시 엣지케이스 원장

2026-09-21 · **현상 파악과 후속 확인 항목 정리 완료. 제품 수정·모델 재실행은 하지 않았다.**

후보 40개를 찾고도 읽기 0개로 끝난 CM018은 서버의 종료 제어 오류다. 모델에 오류를 돌려주고 다시 판단하게 하는 경로는 일부 있지만, 서버가 먼저 종료하거나 입력 생성에 실패하면 그 경로에 도달하지 못한다. 정상 ID에 잘못된 내용을 연결한 CM003은 오류로 감지되지 않아 수정 요청도 없었다.

아래 **40개 점검 항목은 모두 발생한 오류 40건을 뜻하지 않는다.** `관측`은 기존 실행 기록에서 확인한 현상, `코드`는 분기·계약은 확인했지만 해당 상황을 새로 실행하지 않은 항목이다. 정상적인 거부·보호 동작도 복구 경계를 확인하기 위해 포함했다. 이번 범위는 ADR-0488의 v3/v4 12회와 해당 실행 경로이며, 전체 시스템의 모든 엣지케이스를 발견했다고 보지 않는다.

## 확인 범위와 근거

- [기존 실험](../../../../04_EXPERIMENTS/ADR/ADR-0488-qwen-source-tiers-v4-paired/README.md): CM003·018·038 × v3/v4 × 2반복. 기존 공개 외부 Qwen 실행 기록을 읽었다.
- [추출 원장](evidence.json): 12회별 단계 수, 모델 입력의 오류·원문·도구 결과, 선택 시도, 이벤트 번호, 원본 파일 해시. 기존 수치를 재채점하거나 새 품질 지표를 만들지 않았다.
- 실행은 [run_probe.py](../../../../06_TOOLS/EXPERIMENTS/adr_0488/run_probe.py)의 `pin → run_one`이 선택한 `adr_0488/source-tiers-v4/revisions/rev-001/snapshot/02_BACKEND`다. v3와 v4가 같은 snapshot에서 서로 다른 Session을 선택한다.
- `RequestContext → Repository/Sources/ModelGateway → investigate → select → assemble → answer_and_review → publication.prepare/export`를 확인했다. 이 실험 runner는 세션을 직접 호출하며 실제 HTTP·브라우저 실행과 같다고 보지 않는다.
- 이번 원장에서 참조한 제품 코드 14개는 확인 시점의 작업 파일과 frozen 파일이 바이트 단위로 같았다. 경로·해시는 `evidence.json.code_comparison`에 남겼다.
- 기본 MAIN의 v2, 선택된 로컬 frozen release, GENOS 현장 실행은 이 v4 결과와 별개다. 이번 작업은 문서·진단 원장만 추가했다.

## 실제로 어디까지 갔는가

아래 수는 기존 `result.json.stages`의 **고유 source_id 수**다. READ 영수증 E 수·검색 카드 수·모델 호출 수와 혼용하지 않는다. 예를 들어 CM018 두 번째 v4는 READ 영수증 2개지만 같은 source_id이므로 읽기 열은 1이다.

| v4 실행 | 발견 | 읽기 | 모델 제시 | 저장된 선택 | bundle 출처 | 게시 출처 | 모델 호출 |
|---|---:|---:|---:|---:|---:|---:|---:|
| run-001 / CM003 | 76 | 2 | 2 | 1 | 1 | 0 | 6 |
| run-001 / CM018 | 40 | 0 | 0 | 0 | 0 | 0 | 2 |
| run-001 / CM038 | 82 | 3 | 0 | 0 | 0 | 0 | 2 |
| run-002 / CM003 | 60 | 1 | 1 | 1 | 1 | 0 | 6 |
| run-002 / CM018 | 27 | 1 | 1 | 0 | 0 | 0 | 8 |
| run-002 / CM038 | 108 | 6 | 4 | 0 | 0 | 0 | 3 |

출처: [기존 metrics.json](../../../../04_EXPERIMENTS/ADR/ADR-0488-qwen-source-tiers-v4-paired/artifacts/metrics.json), 각 실행의 `result.json`, `journal.sqlite`, `trace.json`. v4 모두 `publication_status=BLOCKED`이며 `execution_error=null`이다. 따라서 **실행 예외 0건을 정상 완료로 해석하면 안 된다.**

## “가이드가 있는가”의 정확한 구분

| 대상 | 실제 제공한 안내 | 없는 것·부족한 것 | 실제 결과 |
|---|---|---|---|
| R1을 READ | 시스템 프롬프트에 R/F 읽기 금지, 오류에 `locate(... target="R1", cursor=null)` 예시와 D/P/U/E 설명 | 사전 단계별 허용 행동 목록은 별도로 없음 | CM018 run-002는 다음 호출에서 locate로 수정했다. 안내와 재시도가 작동한 사례 |
| 후보 읽기 | 후보 카드에 문서명·좌표·미리보기·`read_action`이 있음 | 새 결과를 반드시 제시한 뒤 종료하도록 하는 제어 | CM018 run-001의 새 40개는 다음 탐색 호출 자체가 없어 전달되지 못함 |
| `REVIEWED` 거부 | `REVIEWED requires independent legal review`를 다음 입력 `errors`에 제공 | 현재 선택에서 허용되는 상태, 부족한 검토, 구체적 수정 항목 | CM018에서 같은 상태를 다시 제출. 이후 최종 선택에서 UNASSESSED로 바뀜 |
| 발췌량 초과 | 입력 limits에 1,600자. 오류는 `excerpt limit exceeded; select a smaller exact range` | 해당 선택의 실제 합계·초과량·오류 필드·수정 가능한 범위 | CM018은 12개 span·2,241자를 두 번 제출. 641자 초과를 그대로 반복 |
| JSON 스키마 오류 | 잘못된 응답·검증 오류·전체 객체 재작성 지시 | 복구 메시지가 커졌을 때 입력 재분할 | v4 run-002/CM003에서 1회 발생 후 수정 호출로 진행 |
| 새 후보 후 조기 종료 | 최종 limitations에 탐색 반복 문구 | 모델에 전달되는 종료 오류, 미열람 후보 수, 다음 READ 기회 | run-001/CM018은 오류 목록도 비어 있음 |
| 입력 구성 한도 초과 | 서버 예외·limitations. 일부 최종 선택 실패는 recovery 이벤트 | 더 작은 입력 생성 후 재전달 | run-001/CM038은 읽은 3개 모두 미제시 |
| 유효 ID의 잘못된 내용 선택 | span 소속·좌표·제시 여부 검사 | 설명의 항·호와 선택 본문 간 불일치 감지 | CM003 두 반복에서 3호 설명/2호 선택을 통과시킴 |
| 기능·자료 부재 | 서버 내부 capabilities, EMPTY/UNRESOLVED 등의 상태는 있음 | v4 view의 `tool_capabilities`, 일부 검색·범위 영수증, 실패별 사용자 문구 | **관련 안내가 전혀 없다는 설명도 틀리고, 충분하다는 설명도 틀림** |

`errors`에는 최근 2개 `{code, message}`만 들어간다. 일반적인 `stage`, `field_path`, `actual`, `expected`, `retryable`, `next_action`, `preserved_state` 계약은 **현재 없다**. 세부 도구·관계 안내가 따로 존재한다는 사실과 구분한다.

## 엣지케이스 40개

“필요 동작”은 이번에 정리한 후속 수정·검사 기준이며 구현 완료 표기가 아니다. 관련 조의 선택을 유지한다는 것은 **모델이 관련 있다고 선택한 조의 정체성과 원문 열기 경로를 보존**한다는 뜻이다. 검색 후보를 서버가 임의로 채택하거나 전체 조를 읽었다고 표시한다는 뜻이 아니다.

### 발견·종료 제어

| ID / 확인 | 조건·현재 동작 | 필요한 안내·복구 및 확인 기준 | 근거 |
|---|---|---|---|
| E01 관측 | EMPTY 검색 뒤 새 후보 40개가 나와도 진전으로 세지 않아 종료 | 새 후보·미제시 결과·읽기 대기 여부를 확인. 예산이 남으면 결과 제시와 READ 판단까지 진행. 중단 시 미열람 40건을 명시 | CM018 run-001 v4; C1 |
| E02 관측 | 제목 검색 EMPTY. 해당 검색에서 못 찾은 것과 자료 자체 부재를 구분해야 함 | 검색 방식·범위·검색어를 명시하고 가능한 locate/다른 검색을 제안. “자료 없음”으로 확정하지 않음 | 같은 실행의 첫 observation; C4 |
| E03 관측 | `상증세법 시행령 제49조 제1항` locate가 서로 다른 문서의 후보 28개와 UNRESOLVED 반환 | 정확 문서 식별 여부·모호성 이유를 표시. 문서명을 좁힌 뒤 좌표 확인. 사용자가 지정한 법령과 다른 문서를 확정하지 않음 | CM018 run-002 v4; C4 `locate` |
| E04 코드 | 기능 가용성은 서버에 있으나 v4 view가 `tool_capabilities`를 넣지 않음 | 선택 세대에 없는 기능은 “현재 이용 불가”와 실행 가능한 대안을 선제 제공 | C2, C3 생성자 |
| E05 코드 | 범위 밖·다른 요청의 target은 거부 | 범위 제한/오래된 ID와 검색 0건을 구분. 현재 범위에서 새 핸들 조회. 권한 확대 없이 복구 | C3 `resolve/validate_action`, C5 |
| E06 코드 | 용어·정의·관계 검색이 빈 목록이어도 미구축·미수록·선택 범위 내 0건일 수 있음 | 이용 가능성·대상 세대·검색 완결성을 함께 보고. 이 경로들에서 부재 사유를 일관되게 구분하는지 추가 검사 필요 | C3 capabilities·관계 조회, C4 정의/용어 조회 |
| E07 관측 | 다른 도구/인자에 cursor 재사용하여 거부. cursor와 후보가 모두 P 접두어를 사용 | 원래 도구·인자와 결속된 실행 가능한 계속 요청을 반환. 새 작업은 cursor=null. 반복해도 정상 수정 후 진행되는지 확인 | CM018 run-002 v3 오류 2회; C5 |
| E08 코드 | 새 정보 없이 같은 READ·설명 수정 반복. 반대로 새로운 페이지 전달은 진전이어야 함 | 동일 범위 재조회와 새 범위/새 후보를 구분. 반복 사유와 가능한 미수행 작업을 알린 후 제한. 문자열만 바꿔 무한 반복하지 않음 | C1 `progress_key`, C3 READ 재사용 |

### 원문 읽기·도구 실행

| ID / 확인 | 조건·현재 동작 | 필요한 안내·복구 및 확인 기준 | 근거 |
|---|---|---|---|
| E09 관측 | R1/F 폴더를 READ하여 거부 | 현행 예시 안내 유지. locate/search로 수정 후 READ까지 연결되는지 확인 | CM018 run-002 v4에서 실제 수정; C3 |
| E10 코드 | 모양이 정상인 미제공·오래된·다른 종류 ID 사용 | 유효한 현재 선택지와 종류를 재제시. ID 추측을 요구하지 않음 | C1 `validate_selection`, C3 `validate_action`, C5 |
| E11 코드 | 긴 조문 READ가 PARTIAL이고 다음 페이지가 남음 | 읽은 범위·남은 범위·다음 READ를 함께 제공. 한 페이지만 읽고 조 전체 확인으로 처리하지 않음 | C3 `read`, C2 결과 축약 |
| E12 코드 | READ 뒤 6종 관계 자동 작업이 모델과 같은 도구/시간 예산 사용 | 모델 READ 예산과 자동 작업 소모를 표시. 새 원문 전달·오류 수정에 필요한 자원을 자동 작업이 소진하는지 검사 | C3 `execute/drain`, profile |
| E13 코드 | 관계 스캔 시간 초과는 PARTIAL인데 next cursor가 없을 수 있음 | “관계 없음/완료”가 아니라 “스캔 미완료”. 재시작·범위 축소 또는 현재 경로로 재개 불가를 명시 | C6 `relation_page`: SCAN_STALLED |
| E14 코드 | 도구 내부 오류가 예외 대신 `status=ERROR, server_reason` observation으로 반환 | 다음 입력에 해당 오류와 수정 행동이 확실히 전달되어야 함. 도구 거부와 예외 catch 경로 모두 검사 | C3 `execute`; C2 최근 결과 선택 |

### 서버 읽기 → 모델 입력 전달

| ID / 확인 | 조건·현재 동작 | 필요한 안내·복구 및 확인 기준 | 근거 |
|---|---|---|---|
| E15 관측 | 본문 배치 후 offered_handles 등 메타데이터를 붙이니 입력 한도 초과 | 최종 전송 객체 크기를 기준으로 다시 줄이고 분할. 서버에서 재구성한 뒤 원문이 실제 제시됐는지 확인 | CM038 두 반복 v4; C2 |
| E16 관측 | 서버가 읽었어도 성공한 모델 제시 기록이 없으면 최종 선택에서 제외 | 미제시 원문을 먼저 작은 입력으로 전달하고 선택 재진입. 전달 실패를 “선택할 근거 없음”으로 처리하지 않음 | CM038 run-001: 읽기3/제시0, select_sources 모델 호출 없음; C1/C2 |
| E17 코드 | exact_evidence 항목 하나가 너무 크면 통째로 생략. view_page도 같은 한 항목을 반환 | 한 항목 내부를 정확 범위로 분할. 같은 oversized 항목을 페이지로 반복 반환하는지 검사 | C2 `build`, C3 `view_page` |
| E18 코드 | 최종 선택은 원문 최대4개이고 continuations·도구가 없음 | 이미 읽고 제시한 원문이 5개 이상일 때 누락분 선택 방법 마련. 적합한 기존 선택 유지, 미선택 원문 처리 상태 기록 | C2 final 분기, profile |
| E19 관측 | `last_action_results`는 전체 observation 중 최근2개라 모델 READ 결과 대신 자동 관계 결과가 차지 | 마지막 모델 요청의 결과와 오류를 우선 고정. 자동 작업은 별도 요약. READ 완료·부분읽기 영수증을 잃지 않음 | CM018/CM003 v4 입력; C2 |
| E20 코드 | 결과 shell에서 search_receipt·coverage·scan_status 등의 필드가 빠짐 | 검색 범위·실제 total·완료 여부·스캔 실패를 축약 입력에도 보존. `item_total`을 전체 검색 적중 수로 혼동하지 않음 | C2 shell whitelist, C3/C4 영수증 |
| E21 코드 | 오류 최근2개만 재전달. 해결된 오류와 미해결 오류 상태가 없음 | 미해결 오류 우선, 해결 여부와 현재 수정 대상 명시. 이전 오류가 새 안내를 밀어내지 않음 | C1/C2, C7 |
| E22 코드 | JSON 수정 메시지는 이전 응답·오류를 추가하므로 원래 입력보다 커짐 | 수정 호출도 최종 wire 크기로 검증·축소. 형식 복구 요청이 입력 한도 오류로 바뀌는 경계 검사 | C8 `generate` |

### 모델 선택·상태·저장

| ID / 확인 | 조건·현재 동작 | 필요한 안내·복구 및 확인 기준 | 근거 |
|---|---|---|---|
| E23 관측 | CM003은 3호·4호라고 설명하지만 실제 유효 ID는 2호·4호. 형식·원문 무결성 통과 | 조·항·호 라벨/정확 본문/선택 ID를 한 항목에 제시. 설명과 선택 범위 불일치를 수정 대상으로 알림. 의미 일치는 hash 검사로 보장되지 않음 | CM003 두 반복의 기존 원문 대조; C1/C2 |
| E24 관측 | 독립 검토 없이 REVIEWED 제출 → 동일 오류 반복 | 현재 허용 상태 UNASSESSED/UNCERTAIN 안내 또는 검토 상태를 서버가 결정. 관련성 선택이 검토 완료 오표기 때문에 전부 사라지지 않도록 계약 분리 | CM018 run-002, CM003 두 반복; C1 |
| E25 관측 | 1,600자 제한에 2,241자(12 span)를 두 번 제출 | 해당 선택과 실제 합계·한도·641자 초과를 반환. 서버가 조 선택을 보존하고 표시 분량·강조를 조절하는 경로 마련 | CM018 run-002 최종 선택2회; C1/C2 |
| E26 코드 | 한 선택의 오류로 validate_selection 전체가 실패. 같은 Turn의 도구 행동도 실행 전 차단 가능 | 유효한 조 선택·잘못된 강조·실패 행동을 구분하는 저장 계약 필요. 혼합 배치에서 무엇이 저장/미실행인지 알림 | C1 `apply_turn/validate_selection/persist_selection` |
| E27 코드 | 세부 span 선택 실패 시 조 전체의 선택으로 보존하는 경로 없음 | 모델이 관련 조로 선택한 사실을 먼저 보존. 강조 실패는 강조 미확정. 원문 열기·읽은 범위 표시는 유지. 미열람 전체 조를 읽음 처리하지 않음 | C1/C2/C9 |
| E28 코드 | 동일 범위의 양 tier 중복, tier 상한, SELECTED/PENDING 충돌을 거부 | 현재 사용량·충돌 선택·명시 교체 방법을 제공. 기존 유효 선택이 단순 빈 응답으로 지워지지 않는 보호는 유지 | C1; 기존 T03 검사 |
| E29 코드 | 선택과 함께 잘못된 법적/관계 평가를 내면 상위 apply_turn 검증도 실패 | 관련 원문 선택과 법적 주장 검토의 실패 영향 분리. 메뉴만 보고 관계 확정하지 않는 보호는 유지 | C1 `apply_turn`, C10 |
| E30 코드 | 읽기만 했거나 현재 view에 없는 span은 선택 거부 | 작은 입력으로 실제 전달 후 새 view에서 재선택. 출처를 보지 않고 채택하는 우회는 금지 | C1, 기존 T04 검사 |

### 오류 재시도·완료 표시

| ID / 확인 | 조건·현재 동작 | 필요한 안내·복구 및 확인 기준 | 근거 |
|---|---|---|---|
| E31 관측 | JSON 추가 필드 등 출력 schema 위반 | 현행 잘못된 응답+검증 오류 전달과 bounded repair 유지. 형식 복구 성공 뒤 의미·실행 조건 검사를 별도로 수행 | run-002/CM003 v4 OUTPUT_SCHEMA_INVALID 1회; C8 |
| E32 관측 | 오류가 돌아가도 같은 잘못된 상태·범위를 반복 제출 | 같은 오류에는 더 구체적 수정 안내/작은 수정 과제를 제공. 재시도 횟수만 늘리지 않음. 실패 시 보존 상태와 남은 오류 공개 | CM018 run-002 v4; C1/C7 |
| E33 코드 | 탐색은 동일 오류 1회 수정 후 재발하면 종료. 최종 선택은 별도2회. 예산은 공유 | 단계별·전체 재시도 사용량과 남은 행동을 함께 기록. 최종 선택으로 옮겨도 해결 불가능한 동일 입력을 반복하지 않음 | C1 `investigate`, C7, profile |
| E34 코드 | 무진전·입력 초과·전송 오류·시간/호출 소진이 limitations로 종료되지만 공통 구조화 종료 사유는 없음 | 서버 복구 가능한 오류와 모델 수정 가능 오류를 분리. 한도 도달 시 원인·미완료 단계·보존 결과를 최종 반환 | C7/C8, 기존 실행 limitations |
| E35 코드 | bundle NO_SELECTION은 미발견·미열람·미전달·선택 거부·검토 후 미채택을 구분하지 않음 | 아래 부재/미완료 표에 따라 상세 원인을 표시. 기존 limitations와 후보 수는 보조 정보로 유지 | C1 `build_bundle`, C11/C12 |

### 저장 → 게시 → 열기·재개

| ID / 확인 | 조건·현재 동작 | 필요한 안내·복구 및 확인 기준 | 근거 |
|---|---|---|---|
| E36 관측 | 요청의 외부 승인 export_allowed=true와 원본 manifest=false를 동일성 비교하여 게시 차단 | 원본 속성·요청 승인 계약을 구분하고 실행 전 연결 검사. 모델 재호출 대신 설정 연결을 수정할 대상임을 표시. 원본 플래그는 보존 | v4 6/6; runner binding, C9 |
| E37 코드 | 선택이 바뀐 뒤 옛 bundle을 게시하면 거부 | 최신 선택으로 bundle 재생성 후 검증. stale 결과를 게시하지 않음. 재생성/게시 재시도 상태를 기록 | C9 `validate_saved`, 기존 T08 검사 |
| E38 코드 | 실제 원문 hash·세대·접근 범위 변경 시 게시/열기를 차단 | 정상적인 보호. 변경 사유를 알려주고 현재 허용 원문으로 재검증. 단순 재시도로 통과시키지 않음 | C9 `validate_current`, 기존 T08 검사 |
| E39 코드 | COMMIT_READY는 현재 guard가 있어야 복구, 소유자 잃은 RUNNING은 INTERRUPTED | 저장된 선택·미완료 작업·실행 소유권을 구분해 재개 가능 여부 안내. LLM 자동 재호출은 현재 없음 | C13 `recover`, 기존 T08 검사 |
| E40 코드 | 내부 bundle/offline 화면은 존재해도 실제 게시·링크 열기 성공은 별도 | 게시 실패/링크 미설정/접근 거부를 빈 출처와 구분. 카드 유지와 실제 열기를 따로 검사 | C12/C13, 기존 offline payload 및 운영 안내 |

## 오류를 돌려준 다음 어디서 다시 실행해야 하는가

모델이 고칠 수 있는 오류는 **실패 지점·잘못된 값·허용되는 값·수정 행동·보존 결과를 받고 재시도**해야 한다. 다음처럼 재시도 주체를 나눠야 한다.

| 상황 | 다시 수행할 곳 | 종료/복구 원칙 |
|---|---|---|
| 잘못된 도구 종류·cursor·상태·schema | 모델의 해당 행동/선택 | 새 입력에서 구체적 오류와 실행 가능한 선택지 제공. 정상 수정 후 다음 단계로 진행 |
| 입력 크기 초과·후보 제시 누락 | 서버 입력 구성·전달 | 서버가 분할/축소 후 전송. 모델이 받지도 못한 자료를 판단하길 요구하지 않음 |
| 유효 ID의 내용 오연결 | 선택 UI/입력 결속 + 모델 수정 | 정확 텍스트·구조 라벨과 선택 결과를 대조. 항·호 강조 실패와 조의 관련성 선택 분리 |
| 게시 설정 연결 오류 | 실행 설정·게시 검증 | 원문·승인을 재검증. 선택을 다시 생성하는 모델 호출로 해결하려 하지 않음 |
| 권한 거부·실제 자료 부재·총예산 소진 | 현재 처리 종료 또는 명시 가능한 후속 경로 | 원인을 그대로 알림. 같은 요청의 무한 반복 금지. 이미 유효한 결과·미완료 상태 보존 |

공통 오류 응답의 **후속 요구안**은 다음 정보를 포함한다. 현재 구현된 schema가 아니다.

```json
{
  "code": "EXCERPT_LIMIT_EXCEEDED",
  "stage": "source_selection",
  "field_path": "selections[0].basis_span_ids",
  "actual_chars": 2241,
  "limit_chars": 1600,
  "excess_chars": 641,
  "retryable": true,
  "retry_owner": "MODEL",
  "message": "선택한 범위가 641자 초과했습니다. 이 선택의 표시 범위를 줄이세요.",
  "allowed_next_actions": ["REVISE_THIS_SELECTION"],
  "preserved_state": "PREVIOUS_VALID_SELECTIONS"
}
```

예시는 현재 span 계약을 유지할 때의 최소 개선이다. **조 선택을 단순화하면 표시 발췌량 초과는 서버가 분량을 조절하는 문제로 옮기는 것이 목표**다. 실제 계약에서는 추상 행동명만 주지 말고 현재 view에 유효한 ID·범위·실행 인자를 함께 제공해야 한다. `REVIEWED`는 “독립 검토 없음, 현재 허용 상태 UNASSESSED/UNCERTAIN”까지 알려야 한다.

## “없으면 없다”라고 말할 때 구분할 상태

아래 문구·상태 이름은 요구사항이며 현재 통합 구현된 상태 enum이 아니다. `EMPTY` 한 번으로 전 데이터에 대한 부재를 확정하지 않는다.

| 확인 상태 | 표시할 내용 예시 | 하면 안 되는 설명 |
|---|---|---|
| 기능/가이드 미제공 | “현재 선택 세대에는 이 조회 기능이 없습니다.” / “이 오류의 구체적 수정 안내는 현재 없습니다.” | 가이드가 있다고 추정하거나 계속 같은 도구 호출 요구 |
| 선택 범위에 문서 미수록 확인 | “현재 자료 목록에는 해당 문서가 없습니다. 다른 판본·범위는 확인하지 못했습니다.” | 법령/규정 자체가 존재하지 않음 |
| 특정 검색 0건 | “현재 범위에서 이 검색어·방식으로 찾지 못했습니다.” | 관련 근거 없음 |
| 대상 모호 | “여러 문서에서 같은 조 번호를 찾았습니다. 문서 식별이 필요합니다.” | 첫 후보가 지정한 법령이라고 확정 |
| 발견했지만 미열람 | “후보 40개를 찾았지만 원문 읽기를 완료하지 못했습니다. 서버가 조기 종료했습니다.” | 자료 없음, 검토 결과 없음 |
| 읽었지만 미전달 | “원문 3개를 읽었지만 입력 크기 문제로 모델 검토에 전달하지 못했습니다.” | 모델이 읽고도 관련 없다고 판단 |
| 일부만 읽음/전달 | “다음 원문 범위가 남아 있어 전체 확인은 미완료입니다.” | 조 전체 검토 완료 |
| 선택 검증 실패 | “원문은 확인했으나 선택 범위/상태 오류를 수정하지 못했습니다.” | 관련 원문 없음 |
| 검토 후 미채택 | “검토한 원문을 다음 이유로 채택하지 않았습니다.” + 실제 사유 | 미열람 원문까지 무관하다고 판정 |
| 게시 차단 | “선택 결과는 저장됐지만 게시 검증에 실패했습니다.” | 선택이 없었다거나 게시 성공 |
| 접근 제한/예산 소진 | 허용되는 범위에서 접근 제한·남은 작업·소진 한도를 명시 | 부재와 실패를 구분하지 않은 빈 응답 |

## 먼저 확인할 수정 순서와 통과 기준

1. **E01·E15·E16: 결과를 다음 단계에 전달하기.** EMPTY → 후보40 조건에서 원문 선택/읽기 기회가 생겨야 한다. 원문을 읽은 뒤 입력이 커지면 축소한 입력으로 전달되어야 한다. 새 후보를 모두 읽도록 강제하는 것이 아니라, 읽을 기회도 없이 종료하는 결함을 막는 기준이다.
2. **E24·E25·E26·E32: 오류를 수정 가능한 형태로 반환하기.** 2,241자/1,600자 초과, REVIEWED 미검토, 유효/무효 혼합 선택을 넣고 다음 입력·저장 상태를 확인한다. 거부 assert만으로 복구 성공으로 판정하지 않는다.
3. **E23·E27: 내용과 ID를 함께 보여주고 조 선택 보존하기.** 정상 ID이지만 다른 호를 선택하는 사례를 검사한다. 조 관련성 선택이 유지되는지, 강조 상태가 미확정으로 남는지, 실제 원문 열기가 가능한지 확인한다.
4. **E02~E06·E11·E20·E35: 부재와 미완료를 표시하기.** EMPTY/UNRESOLVED/PARTIAL/미전달/미채택의 최종 문구가 서로 달라야 한다.
5. **E36~E40: 저장 이후 복구 경계를 확인하기.** 원본 속성과 요청 승인을 구분해 검증하고, 권한/hash 불일치 차단은 유지한다. 선택 저장·bundle 생성·게시·열기 각각의 성공을 따로 기록한다.

기존 [v4 계약 검사](../../../../05_TESTS/CONTRACTS/test_source_tiers_v4.py)는 미제시 선택 거부, REVIEWED 거부, tier cap, 일부 bounded recovery, outbox·변경 검증 등을 검사한다. 그러나 `test_T03_unread_discoveries_in_tier3_not_sources`는 미열람 후보 표시를 검사할 뿐 **새 후보40 → 다음 모델 입력 → READ** 연속 실행을 검사하지 않는다. oversized relation 검사는 **원문+메타데이터 전체 wire 초과 복구**와 다르다. 이번에는 테스트를 실행하거나 수정하지 않았으며, 기존 24개 통과를 이 40개 항목의 통과로 재사용하지 않는다.

## 코드 참조

아래 링크는 확인 당시 frozen 코드와 같았던 작업 파일이다. 이후 변경 시 `evidence.json`의 frozen 경로·해시로 당시 상태를 확인한다.

- C1: [tiers_session.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_session.py) — `progress_key`, `investigate`, `validate_selection`, `apply_turn`, `build_bundle`.
- C2: [tiers_views.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_views.py) — `span_choices`, `build`: 원문/ID 분리, 결과 축약, 최종 wire 검사, final 제시 필터.
- C3: [relations_tools.py](../../../../02_BACKEND/semantic_runtime/legal_agent/relations_tools.py) — `validate_action`, `candidate`, `read`, `execute`, `drain`.
- C4: [exploration_tools.py](../../../../02_BACKEND/semantic_runtime/legal_agent/exploration_tools.py) — `search`, `locate`, 용어/정의 조회.
- C5: [source_tools.py](../../../../02_BACKEND/semantic_runtime/legal_agent/source_tools.py) — `cursor_position`, cursor의 operation/binding 검사.
- C6: [tiers_tools.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_tools.py) — `relation_page`의 PARTIAL/시간 한도.
- C7: [tools_session.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tools_session.py) — `investigate`, `generate_checked`, 오류 반복·종료.
- C8: [gateway.py](../../../../02_BACKEND/semantic_runtime/legal_agent/gateway.py) — JSON 수정·전송 재시도·wire 크기.
- C9: [source_bundle.py](../../../../02_BACKEND/semantic_runtime/legal_agent/source_bundle.py) — `validate_saved`, `validate_current`.
- C10: [relations_session.py](../../../../02_BACKEND/semantic_runtime/legal_agent/relations_session.py) — 평가·관계·DRAFT 조건 검사.
- C11: [source_candidates.py](../../../../02_BACKEND/semantic_runtime/legal_agent/source_candidates.py) — 후보/미채택 상태 투영.
- C12: [source_tiers_ui.py](../../../../02_BACKEND/semantic_runtime/legal_agent/source_tiers_ui.py) — NO_SELECTION·출처 카드 표시.
- C13: [publication.py](../../../../02_BACKEND/semantic_runtime/legal_agent/publication.py) — prepare/export/recover.
- profile: [profile-tools-v4.json](../../../../00_SYSTEM/LEGAL_AGENT/profile-tools-v4.json). 안내: [tiers_policy.py](../../../../02_BACKEND/semantic_runtime/legal_agent/tiers_policy.py), [relations_policy.py](../../../../02_BACKEND/semantic_runtime/legal_agent/relations_policy.py). 스키마: [source-tiers-v4.schema.json](../../../../00_SYSTEM/SCHEMAS/source-tiers-v4.schema.json).

확인 방식: 저장된 JSON을 읽고 SQLite를 `mode=ro`로 열어 event/model_view/model_attempt를 대조했다. 원본 해시와 frozen/작업 코드 동일성을 확인했다. 원본 ADR·실행 결과·선택·원문은 수정하지 않았다. 모델 재호출·재채점·MAIN 전환·배포는 수행하지 않았다.
