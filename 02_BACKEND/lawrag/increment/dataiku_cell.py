"""Dataiku Python 노트북·레시피 한 셀에서 부르는 진입점 — PARAMS → 실행기 → ACTION.

수신 파이프라인 코드(flow_runtime 등)는 셀의 BOOTSTRAP이 먼저 불러 둔다. 설정(GENOS 주소·Agent 연결·입력/지원
폴더·WORK_DIR)은 설치된 레시피 코드에서 읽어 같은 값을 쓴다.
대상 Gold는 03_LOAD와 같은 프로젝트 변수로 정한다(개발계·운영 표 이름이 같고 소유자만 다름):
  LGL_GOLD_OWNER         필수. 개발계 SIDDS, 운영 SIDDG
  LGL_GOLD_TABLE_PREFIX  선택. 기본 IDD_B003_LGL_. 시험 복사본(TST_B003_LGL_ 등)에서 실험할 때만
"""
from __future__ import annotations

import json

ACTIONS = ("check", "status", "decide", "publish", "activate", "run", "rollback", "cleanup")


def _latest_run(store) -> str:
    runs = sorted({p.split("/")[1] for p in store.list("runs/") if p.endswith("/decide.json")})
    if not runs:
        raise ValueError("RUN_REQUIRED: 판단(decide) 기록이 없음")
    return runs[-1]


def build(params: dict):
    import dataiku
    from gold_owner import resolve
    from prod_config import target

    from .dataiku_flow import Flow, Params, R6Runner, r6_cfg_from_recipe
    from .history import DataikuStore
    from .release_ops import DataikuSql, Names

    project = dataiku.api_client().get_default_project()
    cfg = r6_cfg_from_recipe(project, params.get("R6_RECIPE") or "LGL_AGENT_R7_PROD_02_WAIT_AGENT")
    if params.get("TARGET") or params.get("GOLD_OWNER"):
        raise ValueError("TARGET·GOLD_OWNER는 더 쓰지 않는다 — 프로젝트 변수 LGL_GOLD_OWNER(개발계 SIDDS, 운영 SIDDG)로 정한다")
    gold = resolve(dataiku.get_custom_variables())
    print("GOLD_TARGET", gold["GOLD_OWNER"] + "." + gold["TABLE_PREFIX"] + "*", flush=True)
    overrides = {}
    if params.get("SUPPORT_ZIP_NAME"):
        overrides["SUPPORT_ZIP_NAME"] = params["SUPPORT_ZIP_NAME"]
    names = Names(target({"TARGET_MODE": "GOLD", **gold}))
    for key in ("DROP_FOLDER_ID", "STATE_FOLDER_ID"):
        if not params.get(key):
            raise ValueError(key + "_REQUIRED")
    flow = Flow(store=DataikuStore(dataiku.Folder(params["STATE_FOLDER_ID"])),
                drop=DataikuStore(dataiku.Folder(params["DROP_FOLDER_ID"])),
                inputs=DataikuStore(dataiku.Folder(cfg["INPUT_FOLDER_ID"])),
                db=DataikuSql(dataiku.SQLExecutor2(connection=cfg["TARGET_CONNECTION"])),
                agent_db=DataikuSql(dataiku.SQLExecutor2(connection=cfg["AGENT_CONNECTION"])),
                names=names, r6=R6Runner(cfg, overrides),
                params=Params(channel=params.get("CHANNEL") or "main",
                              base_zip_name=params.get("BASE_DATA_ZIP_NAME") or "",
                              base_prefix=params.get("BASE_DOCUMENT_PREFIX") or "",
                              hold_on_strong=bool(params.get("HOLD_ON_STRONG", True)),
                              retry_hold=bool(params.get("RETRY_HOLD", False)),
                              prune_batch=int(params.get("PRUNE_BATCH", 50000)),
                              today=params.get("TODAY") or ""))
    return flow


def main(params: dict) -> dict:
    from .dataiku_flow import run_id
    action = params.get("ACTION", "status")
    if action not in ACTIONS:
        raise ValueError(f"ACTION은 {ACTIONS} 중 하나")
    flow = build(params)
    run = params.get("RUN") or ""
    if action in ("publish", "activate") and not run:
        run = _latest_run(flow.store)
    if action in ("decide", "run", "rollback") and not run:
        run = run_id()
    result = {"check": lambda: flow.check(), "status": lambda: flow.status(),
              "decide": lambda: flow.decide(run), "publish": lambda: flow.publish(run),
              "activate": lambda: flow.activate(run), "run": lambda: flow.run(run),
              "rollback": lambda: flow.rollback(run), "cleanup": lambda: flow.cleanup()}[action]()
    print("INCREMENT_" + action.upper() + "_DONE", run)
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str)[:20000])
    return result
