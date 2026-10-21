"""UI session semantics and the inherited SELECT-only Oracle boundary; no LLM."""
from pathlib import Path
import sys
import types
import pytest

pytest.importorskip("streamlit")
from streamlit import config
from streamlit.testing.v1 import AppTest
import pandas as pd

config.set_option("global.developmentMode", False)
config.set_option("logger.level", "error")
APP = Path(__file__).resolve().parents[3] / "03_FRONTEND/APPS/legal-knowledge-streamlit/app.py"


def button(app, label):
    return next(x for x in app.button if x.label == label)


def field(app, kind, label):
    return next(x for x in getattr(app, kind) if x.label == label)


def start():
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    return app


def oracle(app):
    app.button(key="nav_배치 모니터").click().run()


def test_all_six_pages_render_without_backend_calls():
    app = start()
    for page in ["구조화 누락 승인", "숏컷 승인", "Legal Wiki", "온톨로지 관리", "시뮬레이션", "배치 모니터"]:
        app.button(key="nav_" + page).click().run()
        assert not app.exception
    assert app.session_state.studio["simulation"] is None
    assert app.session_state.studio["events"] == []


def test_structure_requires_review_and_preserves_source_session_isolation():
    app = start()
    app.button(key="nav_구조화 누락 승인").click().run()
    original = app.session_state.studio["structures"][0]["source"]
    button(app, "승인").click().run()
    assert app.error and app.session_state.studio["structures"][0]["status"] == "승인 대기"
    app.text_area(key="reason_ST-001").set_value("각주를 원문과 대조했습니다.")
    app.checkbox(key="checked_ST-001").check()
    button(app, "승인").click().run()
    item = app.session_state.studio["structures"][0]
    assert item["status"] == "승인" and item["source"] == original
    assert len(app.session_state.studio["events"]) == 1
    app.run()
    assert len(app.session_state.studio["events"]) == 1
    assert start().session_state.studio["structures"][0]["status"] == "승인 대기"


def test_incomplete_shortcut_can_be_held_but_not_approved():
    app = start()
    app.button(key="nav_숏컷 승인").click().run()
    app.button(key="select_SC-022").click().run()
    assert button(app, "승인").disabled
    app.text_area(key="reason_SC-022").set_value("누락 근거를 확보한 뒤 재검토합니다.")
    button(app, "보류").click().run()
    assert app.session_state.studio["shortcuts"][1]["status"] == "보류"
    assert button(app, "승인").disabled
    assert app.session_state.studio["shortcuts"][1]["state"] == "부분 완료"


def test_wiki_edit_does_not_replace_published_version():
    app = start()
    app.button(key="nav_Legal Wiki").click().run()
    published = app.session_state.studio["wikis"][0]["body"]
    field(app, "text_area", "위키 본문").set_value("새 검토 초안")
    field(app, "text_input", "변경 사유").set_value("근거 범위 보완")
    button(app, "초안 저장").click().run()
    button(app, "초안을 검토 요청").click().run()
    assert app.session_state.studio["wikis"][0]["body"] == published
    assert app.session_state.studio["wiki_drafts"]["WK-01"]["body"] == "새 검토 초안"
    assert app.session_state.studio["wikis"][0]["status"] == "검토 대기"
    assert button(app, "실제 게시 · 관리 API 연결 필요").disabled


def test_simulation_preview_binds_version_and_invalidates_after_edit():
    app = start()
    app.button(key="nav_온톨로지 관리").click().run()
    button(app, "이 버전으로 시뮬레이션 →").click().run()
    assert app.session_state.studio["simulation"] is None
    button(app, "결과 화면 미리보기").click().run()
    frozen = app.session_state.studio["simulation"]["binding"]
    assert len(app.session_state.studio["simulations"]) == 1
    assert len(app.session_state.studio["simulation"]["cases"]) == 6
    button(app, "연결된 조건 수정하기 →").click().run()
    assert app.selectbox(key="node_ON-01").value == "미확인 처리"
    field(app, "text_area", "수정 사유").set_value("누락 처리 검토")
    button(app, "새 초안 버전 저장").click().run()
    assert app.session_state.studio["ontologies"][0]["revision"] == 4
    button(app, "이 버전으로 시뮬레이션 →").click().run()
    assert any("이전 버전" in x.value for x in app.warning)
    assert app.session_state.studio["simulation"]["binding"] == frozen
    assert len(app.session_state.studio["simulations"]) == 1
    assert button(app, "실제 시뮬레이션 · 실행 API 연결 필요").disabled


def test_oracle_no_automatic_query_bounded_projection_and_scope_reset(monkeypatch):
    calls = []
    class Executor:
        def __init__(self, connection):
            assert connection == "AIDP"
        def query_to_df(self, sql, **kw):
            calls.append(sql)
            if "ALL_TABLES" in sql:
                return pd.DataFrame([{"OWNER": "AIDP", "TABLE_NAME": 'TEST"DOC'}])
            if "ALL_TAB_COLUMNS" in sql:
                return pd.DataFrame([{"COLUMN_NAME": "BODY", "DATA_TYPE": "CLOB"}, {"COLUMN_NAME": "BINARY", "DATA_TYPE": "BLOB"}])
            return pd.DataFrame([{"BODY": "synthetic test row"}])
    monkeypatch.setitem(sys.modules, "dataiku", types.SimpleNamespace(SQLExecutor2=Executor))
    app = start()
    oracle(app)
    assert calls == []
    button(app, "테이블 목록 조회").click().run()
    button(app, "선택 테이블 미리보기").click().run()
    assert not app.exception
    assert len(calls) == 3
    assert all(sql.startswith("SELECT ") for sql in calls)
    assert 'DBMS_LOB.SUBSTR("BODY",300,1)' in calls[-1]
    assert '"AIDP"."TEST""DOC"' in calls[-1]
    assert "ROWNUM<=10" in calls[-1] and "BINARY" not in calls[-1]
    field(app, "text_input", "Oracle 스키마").set_value("OTHER").run()
    assert "oracle_rows" not in app.session_state
    assert "oracle_catalog" not in app.session_state
    assert len(calls) == 3


def test_oracle_failed_refresh_drops_stale_results_and_never_retries(monkeypatch):
    calls = []
    class Executor:
        def __init__(self, connection):
            pass
        def query_to_df(self, sql, **kw):
            calls.append(sql)
            if len(calls) > 1:
                raise RuntimeError("ORA-01031: sensitive server detail")
            return pd.DataFrame([{"OWNER": "AIDP", "TABLE_NAME": "TEST"}])
    monkeypatch.setitem(sys.modules, "dataiku", types.SimpleNamespace(SQLExecutor2=Executor))
    app = start()
    oracle(app)
    button(app, "테이블 목록 조회").click().run()
    assert "oracle_catalog" in app.session_state
    button(app, "테이블 목록 조회").click().run()
    assert len(calls) == 2
    assert "oracle_catalog" not in app.session_state
    assert "ORA-01031" in app.error[0].value
    assert "sensitive" not in app.error[0].value
    assert not app.exception
