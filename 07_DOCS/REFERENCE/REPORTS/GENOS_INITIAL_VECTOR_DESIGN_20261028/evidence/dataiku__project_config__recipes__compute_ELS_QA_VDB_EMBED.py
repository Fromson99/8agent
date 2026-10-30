# -*- coding: utf-8 -*-
"""임베딩 — ELS_QA_VDB_INPUT(벡터 행) → LLM Mesh 임베딩 → ELS_QA_VDB_CHUNK(벡터 표) · ELS_QA_VDB_EMBED_LOG.

벡터 표가 없으면 만들고(els_dku/vdb.py), 문서마다 RDB 와 대조한 뒤 지우고 다시 넣는다. 입력의
ELS_QA_LOAD_LOG 는 읽지 않는다 — Flow 가 RDB 적재를 먼저 빌드하게 하는 순서용이다.
임베딩 모델은 프로젝트 변수 ELS_EMBED_LLM_ID 로 바꿀 수 있다(비우면 KURE-v1).

끝에서 RDB 와 대조해 **active 가 아닌 문서의 벡터를 지운다**(vdb.reconcile). 프로젝트 변수
ELS_PRUNE_MAX_RATIO(기본 0.5, 0 이면 끔)가 한 번에 지울 수 있는 비율의 상한이다.
동시 실행은 따로 잠그지 않는다 — 같은 레시피 둘은 DSS 가 막고('already being built'), 한 상품에
active 문서가 둘 생기는 것은 RDB 유일 인덱스(UX_ELSQA_DOC_ACTIVE)가, 남은 옛 벡터는 질의의 active 필터와
다음 임베딩의 대조(vdb.reconcile)가 막는다.

**어디서 막혀도 로그를 먼저 쓴다.** 하나라도 FAIL 이면 작업을 실패로 끝낸다.
"""
import datetime

import dataiku
import pandas as pd

from els_dku import load, preprocess, sql, vdb

inputs = dataiku.Dataset("ELS_QA_VDB_INPUT")
log_ds = dataiku.Dataset("ELS_QA_VDB_EMBED_LOG")
run_at = datetime.datetime.now().isoformat(timespec="seconds")

rows = []
try:
    model = (dataiku.get_custom_variables().get("ELS_EMBED_LLM_ID") or "").strip() or vdb.LLM_ID
    print("임베딩 모델 %s" % model)
    vdb_tables, vdb_exec = vdb.locate()
    rdb_tables, rdb_exec = load.locate()
    records = inputs.get_dataframe().to_dict("records")
    print("문서 %d건" % len(records))
    rows = vdb.run_embed(sql.Runner(vdb_exec), vdb_tables, sql.Runner(rdb_exec), rdb_tables, records,
                         vdb.mesh_embedder(model), model=model, run_at=run_at)
    rows += vdb.reconcile(sql.Runner(vdb_exec), vdb_tables, sql.Runner(rdb_exec), rdb_tables,
                          max_ratio=preprocess.prune_max_ratio(dataiku.get_custom_variables().get("ELS_PRUNE_MAX_RATIO")),
                          run_at=run_at)
except Exception as exc:                      # noqa: BLE001 — 표 준비 등에서 막혀도 로그는 남긴다
    row = dict.fromkeys(vdb.LOG_COLUMNS, "")
    row.update(RUN_AT=run_at, OUTCOME="FAIL", DETAIL="%s: %s" % (type(exc).__name__, vdb._first_line(exc)))
    rows.append(row)

log_ds.write_with_schema(pd.DataFrame(rows, columns=vdb.LOG_COLUMNS).astype(str))

failed = [r["BUNDLE_ID"] or r["DETAIL"] for r in rows if r["OUTCOME"] == "FAIL"]
if failed:
    raise RuntimeError("임베딩 · 벡터 쓰기 실패 %d건: %s — ELS_QA_VDB_EMBED_LOG 의 DETAIL 을 볼 것"
                       % (len(failed), ", ".join(failed[:5])))
