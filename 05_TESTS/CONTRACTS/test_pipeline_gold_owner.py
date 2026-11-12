"""수신 파이프라인 R7·증분 R2 — Gold 소유자·표 앞부분을 Dataiku 프로젝트 변수로 정한다.

개발계(SIDDS)와 운영(SIDDG)은 같은 IDD_B003 이름을 쓰고 소유자만 다르다.
레시피 코드에 소유자를 넣지 않고 LGL_GOLD_OWNER / LGL_GOLD_TABLE_PREFIX를 실행 때 읽는다.
"""
import importlib
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1"


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("r7")
    with zipfile.ZipFile(PKG / "DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip") as z:
        z.extractall(root)
    sys.path[:0] = [str(root), str(root / "engine")]
    for name in ("gold_owner", "prod_config", "flow_install", "flow_runtime"):
        sys.modules.pop(name, None)
    yield root
    for p in (str(root), str(root / "engine")):
        sys.path.remove(p)


def test_owner_required_and_validated(flow):
    from gold_owner import resolve
    with pytest.raises(ValueError, match="LGL_GOLD_OWNER_REQUIRED"):
        resolve({})
    with pytest.raises(ValueError, match="LGL_GOLD_OWNER_REQUIRED"):
        resolve({"LGL_GOLD_OWNER": "sidds"})
    assert resolve({"LGL_GOLD_OWNER": " SIDDS "}) == {"GOLD_OWNER": "SIDDS", "TABLE_PREFIX": "IDD_B003_LGL_"}
    assert resolve({"LGL_GOLD_OWNER": "SIDDG", "LGL_GOLD_TABLE_PREFIX": "TST_B003_LGL_"})["TABLE_PREFIX"] == "TST_B003_LGL_"
    for bad in ("TST_B003_LGL", "tst_", "A_VERY_LONG_PREFIX_X_"):
        with pytest.raises(ValueError, match="LGL_GOLD_TABLE_PREFIX_INVALID"):
            resolve({"LGL_GOLD_OWNER": "SIDDS", "LGL_GOLD_TABLE_PREFIX": bad})


def test_target_names_follow_variables(flow):
    from gold_owner import resolve
    from prod_config import target
    for owner in ("SIDDS", "SIDDG"):
        t = target({"TARGET_MODE": "GOLD", **resolve({"LGL_GOLD_OWNER": owner})})
        assert {v["owner"] for v in t["tables"].values()} == {owner}
        assert t["tables"]["SRCH_CHNL"]["name"] == "IDD_B003_LGL_SRCH_CHNL"
        assert t["tables"]["SRCH_CHNL"]["columns"]["CHAN_NO"]["name"] == "CHAN_NO"
    t = target({"TARGET_MODE": "GOLD", **resolve({"LGL_GOLD_OWNER": "SIDDS", "LGL_GOLD_TABLE_PREFIX": "TST_B003_LGL_"})})
    assert t["tables"]["VCTR_ITEM"]["name"] == "TST_B003_LGL_VCTR_ITEM"
    # 가장 긴 인덱스 이름도 Oracle 30자 안
    assert max(len("X4_TST_B003_LGL_" + k) for k in t["tables"]) <= 30


def test_old_development_names_removed(flow):
    runtime = (flow / "flow_runtime.py").read_text()
    assert "DEV_1" not in runtime and "agent-layer-zip-r6" not in runtime
    assert "TARGET_MODE='GOLD'" in runtime and "resolve(variables)" in runtime
    install = (flow / "flow_install.py").read_text()
    assert "LGL_AGENT_R7_" in install and "GOLD_OWNER'] if" not in install
    from flow_install import validate
    cfg = dict(INPUT_MODE="ZIP", DATA_ZIP_NAME="RAW.zip", SUPPORT_ZIP_NAME="SUP.zip", ENVIRONMENT="PROD",
               CODE_FOLDER_ID="c", INPUT_FOLDER_ID="c", TARGET_CONNECTION="AIDP", AGENT_CONNECTION="AIDP",
               EMBED_MODEL="m", WORK_DIR="/tmp/w", EMBED_DIMENSIONS=1024, EXPECTED_DB_USER="PIDD2APP")
    validate(cfg)                                   # GOLD_OWNER 없이 설치 가능
    setup = (PKG / "DATAIKU_SETUP_R7.txt").read_text()
    assert "GOLD_OWNER" not in setup.split("BOOTSTRAP = ")[0].split("PARAMS = ")[1]


def _fake_dataiku(variables, recipe_code):
    recipe = types.SimpleNamespace(get_settings=lambda: types.SimpleNamespace(get_code=lambda: recipe_code))
    project = types.SimpleNamespace(project_key="P", get_recipe=lambda name: recipe)
    dku = types.ModuleType("dataiku")
    dku.api_client = lambda: types.SimpleNamespace(get_default_project=lambda: project)
    dku.get_custom_variables = lambda: variables
    dku.Folder = lambda fid: types.SimpleNamespace(id=fid)
    dku.SQLExecutor2 = lambda connection: types.SimpleNamespace(connection=connection)
    return dku


def test_increment_cell_uses_same_variables(flow, monkeypatch):
    sys.path.insert(0, str(ROOT / "02_BACKEND"))
    cell = importlib.import_module("lawrag.increment.dataiku_cell")
    cfg = {"project": "P", "folders": {}, "INPUT_FOLDER_ID": "in", "SUPPORT_FOLDER_ID": "sup", "WORK_DIR": "/tmp/w",
           "TARGET_CONNECTION": "AIDP", "AGENT_CONNECTION": "AIDP", "ENVIRONMENT": "PROD"}
    code = "PARAMS={}\nfrom flow_runtime import run\nrun('wait', " + repr(cfg) + ")\n"
    params = {"DROP_FOLDER_ID": "drop", "STATE_FOLDER_ID": "state"}
    monkeypatch.setitem(sys.modules, "dataiku", _fake_dataiku({}, code))
    with pytest.raises(ValueError, match="LGL_GOLD_OWNER_REQUIRED"):
        cell.build(params)
    monkeypatch.setitem(sys.modules, "dataiku", _fake_dataiku({"LGL_GOLD_OWNER": "SIDDS"}, code))
    with pytest.raises(ValueError, match="TARGET"):
        cell.build(dict(params, TARGET="DEV_1"))
    flow_obj = cell.build(params)
    assert flow_obj.n.t("SRCH_CHNL") == "SIDDS.IDD_B003_LGL_SRCH_CHNL"
    assert flow_obj.n.c("SRCH_CHNL", "CHAN_NO") == "CHAN_NO"
    monkeypatch.setitem(sys.modules, "dataiku", _fake_dataiku(
        {"LGL_GOLD_OWNER": "SIDDG", "LGL_GOLD_TABLE_PREFIX": "TST_B003_LGL_"}, code))
    assert cell.build(params).n.t("DOC_VER") == "SIDDG.TST_B003_LGL_DOC_VER"


def test_increment_accepts_r7_load_status():
    """R7 03_LOAD의 결과 상태는 GOLD_LOADED — 증분 게시가 이것을 적재 완료로 받아야 한다 (11-12 실험에서 발견)."""
    flow_src = (ROOT / "02_BACKEND/lawrag/increment/dataiku_flow.py").read_text()
    assert '("GOLD_LOADED", "DEV_LOADED", "PROD_LOADED")' in flow_src
    with zipfile.ZipFile(PKG / "DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip") as z:
        assert "'status':'GOLD_LOADED'" in z.read("flow_runtime.py").decode()
