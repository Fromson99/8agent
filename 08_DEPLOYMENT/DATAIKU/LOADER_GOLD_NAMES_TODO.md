# 적재기 고칠 때 볼 것 — 개발계 표 이름이 운영 Gold와 같아짐 (2026-11-10)

> **2026-11-12 진행:** 수신 파이프라인(S3 원문 ZIP → GENOS → SIDDA → Gold)은 **R7로 Gold 이름 적재 완료(로컬 검증)** —
> [pipeline_gold_owner_20261112_r1/GUIDE.txt](pipeline_gold_owner_20261112_r1/GUIDE.txt). 소유자는 Dataiku 프로젝트 변수
> `LGL_GOLD_OWNER`(개발계 SIDDS, 운영 SIDDG), 시험 복사본은 `LGL_GOLD_TABLE_PREFIX=TST_B003_LGL_`. DEV_1(옛 이름) 경로 삭제.
> 증분 셀 R2도 같은 변수(TARGET 없음), main 채널 SQL은 `MAIN_CHANNEL_SIDDS_R1.txt`(CHAN_NO). 표 확인 `CHECK_TABLES_SIDDS/SIDDG_R1.txt`.
> 아래 목록 중 `gold_fresh_1_*`·`gold_vector_*`·`vector_head_*`(개발계 전용 옛 이름 적재기)는 R7로 대체 — 고치지 않는다.
> 현장 설치·실행은 아직.

사용자 결정(2026-11-10): 개발계 스키마를 운영 Gold와 **표 이름까지 똑같이** 맞춘다. 새 표를 만들지 않고 기존 표 이름·컬럼만 바꾼다.
소유자는 그대로(Gold 13표 `SIDDS`, Agent 4표 `SIDDA`). 운영은 `SIDDG`(Gold) / `SIDDA`(Agent). 운영 표는 파티션 아님.
**개발계 표 변경은 2026-11-10 20:31 현장 적용 완료(결과 17/0/0) — 개발계 DB는 이제 새 이름뿐이다.** 적재기는 이 변경과 따로, **나중에** 고친다(사용자 지시). 고치기 전에는 개발계 적재 셀을 돌리지 않는다(옛 이름을 찾아 실패). 고칠 때 아래를 기준으로 한다.

변경 SQL·안내: [dev_gold_align_20261110_r1/GUIDE.txt](dev_gold_align_20261110_r1/GUIDE.txt) · 기준 매핑 `00_SYSTEM/ORACLE/gold_b003_r5.json`

## 이름 대응

| 옛 개발계 | 새 이름(운영과 같음) |
|---|---|
| `SIDDS.LGL_G19_DOC_VER_S_1` | `SIDDS.IDD_B003_LGL_DOC_VER` |
| `SIDDS.LGL_G19_DOC_UNIT_S_1` | `SIDDS.IDD_B003_LGL_DOC_UNIT` |
| `SIDDS.LGL_G19_DOC_BLK_S_1` | `SIDDS.IDD_B003_LGL_DOC_BLK` |
| `SIDDS.LGL_G19_SRC_POST_S_1` | `SIDDS.IDD_B003_LGL_SRC_POST` |
| `SIDDS.LGL_G19_SRCH_POST_S_1` | `SIDDS.IDD_B003_LGL_SRCH_POST` |
| `SIDDS.LGL_G19_SRCH_ROW_S_1` | `SIDDS.IDD_B003_LGL_SRCH_ROW` |
| `SIDDS.LGL_G19_SRCH_CHNL_S_1` | `SIDDS.IDD_B003_LGL_SRCH_CHNL` |
| `SIDDS.LGL_G19_ONTL_POST` / `_HEAD` / `_ANC` | `SIDDS.IDD_B003_LGL_ONTL_POST` / `_HEAD` / `_ANC` |
| `SIDDS.LGL_G19_VCTR_POST_S_1` / `_ITEM_S_1` / `_HEAD_S_1` | `SIDDS.IDD_B003_LGL_VCTR_POST` / `_ITEM` / `_HEAD` |
| `SIDDA.LGL_AGT_RUN` / `_REC` / `_BODY`, `SIDDA.LGL_EXEC_ST` | `SIDDA.LGL_AGT_RUN_A` / `_REC_A` / `_BODY_A`, `SIDDA.LGL_EXEC_ST_A` |
| (옛 11-02 이전 표) `SIDDA.LGL_AGT_*_A`, `LGL_EXEC_ST_A` | `SIDDA.*_A_OLD` 로 비켜 둠(삭제 안 함) |

컬럼:
- `SRC_POST.RGSN_AITM` → `RGSN_ASTM`
- `SRCH_ROW.SRCH_DATA_HASH_VALU` / `SRCH_DATA_CTNT` → `RFRN_DTA_HASH_VALU` / `RFRN_DTA_CTNT` (로컬 옛 이름 `RFRN_DATA_*`도 이제 `RFRN_DTA_*`)
- `SRCH_CHNL` · `ONTL_HEAD` · `VCTR_HEAD` 의 `CHAN_ORD` → `CHAN_NO`
- `RGLT_DOC_ID` 50 → 100 BYTE (6표), `VCTR_ITEM.BODY_UNIT_ID` 50 → 100, `DOC_BLK.ADDN_IFMN_UN_APPN_YN` CHAR(1) → VARCHAR2(1)

제약·인덱스: PK `X0_IDD_B003_LGL_<표>`, 추가 인덱스 `X1~X4_IDD_B003_LGL_<표>`(컬럼 구성은 전과 같음), Agent `LGL_AR01_PK_A`·`LGL_AR01_I1_A` 등.
적재기가 표를 새로 만들 때(DDL)도 이 이름을 쓴다.

## 고칠 때 원칙

- **개발계도 운영과 같은 적재기를 쓰고 소유자만 바꾸는 것을 먼저 검토한다.** 운영 적재기(`gold_oneclick_prod_20261105_r5`, `gold_zip_flow_20261104_r1`, 판본 선택 보완 `gold_selection_flow_20261109_r7` R7f)는 이미 Gold 이름을 쓴다.
  개발계 전용 이름 표(`contract.json`, `TABLES.csv`, `RENAME_MAP.json`)를 또 만들지 않는다.
- 운영 Dataiku 전달은 플로우 레시피 형태, 운영 버킷 쓰기 금지(기존 규칙 그대로).
- 고친 뒤 개발계에서 [DEV_GOLD_ALIGN_R1.txt](dev_gold_align_20261110_r1/DEV_GOLD_ALIGN_R1.txt)의 V01~V03을 다시 실행해 0행인지 본다.

## 옛 이름을 쓰는 곳 (2026-11-10 기준 검색)

개발계에 지금 쓰는 것:
- 개발계 전체 재적재: `gold_fresh_1_*` 계열(`gold_fresh_1_20261102_r1`, `_batch_r2`, `_transport_r3`, `_reduced_r4`, `_native_bind_r5`, `_jdbc_fast_r6`, `_jdbc_seek_r7`) — `contract.json`·`01_CREATE_FRESH_1_REVIEW.sql`·`RENAME_MAP.json`에 `_S_1` 이름과 `CHAN_ORD`·`SRCH_DATA_*`·`RGSN_AITM`·DOC_ID 50.
- 벡터: `gold_vector_fast_20261103_r1`·`20261104_r2`, `gold_vector_structure_20261104_r3`·`r4`, `vector_head_check/activate/sql_20261106`.
- 증분: `increment_dev_20261109_r1` — `TARGET='DEV_1'`(개발계 실버 `_S_1`)을 Gold 대상+소유자 `SIDDS`로. `DEV_MAIN_CHANNEL_R1.txt`(개발계 채널 `main` 전환 SQL)도 `LGL_G19_SRCH_CHNL_S_1`/`CHAN_ORD`를 쓰므로 새 이름으로 다시 만들어야 한다.
- 표 생성 SQL: `dev_e2e_tables_20261106_r1`·`r2` (권한 GRANT 문장의 표 이름 포함 — 이름을 바꿔도 이미 준 권한은 유지된다).
- Agent 파이프라인: `agent_layer_*_20261105_*`, `agent_gold_layer_20261105_r1`, `agent_a_unified_20261105_r1`.
- 점검·진단: `g19_split_rowcounts_20261105_r1`, `fts_ora22806_notebook_20261106_r1`, `oracle_capacity_followup_20261103_r1`, `nfs_table_capacity_20261103_r1`, `index_join_temp_check_20261103_*`.

코드·로컬:
- `00_SYSTEM/ORACLE/development_g19_1.json`: 개발계 서빙이 `GENOS_ORACLE_TABLE_MAPPING=gold` + `GENOS_ORACLE_GOLD_OWNER=SIDDS`로 바뀌면 쓰지 않는다. 지우는 것은 개발계 전환 확인 뒤 따로 결정.
- 로컬 Gold(`A8_GR12_CM1208`)는 2026-11-10에 이미 `IDD_B003_*`·`RFRN_DTA_*`로 바꿨다. 로컬 연결기 `ACTIVE_MAPPING.json → mapping_local_b003_current.json`.
  로컬 이름을 직접 쓰는 실험 도구(예: `06_TOOLS/EXPERIMENTS/adr_1482/oracle_local.py`, `live_hybrid.py`의 `IDD_B03_LGL_VCTR_ITEM`)는 다시 돌릴 때 새 이름으로 고쳐야 한다.
- `06_TOOLS/maintenance/gold_*_rename.py`는 과거 로컬 변경 기록이라 고치지 않는다.
