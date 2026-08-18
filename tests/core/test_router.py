"""라우터 자체의 회귀 — 등록부가 정말 **유일한 결정자**인가 (SPEC §00).

여기서 지키는 것: 등록부가 모순되면 **적재 시점에** 터진다. 중복 doc_type,
없는 파서, 형식·용어집과 어긋난 doc_type — 전부 조용히 굴러가면 엉뚱한 문서를
그럴듯하게 구조화한다. 미등록 doc_type 은 비슷한 이름을 제안하며 거부한다.

(자동 판별(detect)은 뺐다 — 유형은 호출자가 말하고, "그 유형이 맞긴 한가"는
fitness 게이트가 판정한다. 이 파일은 docling 을 부르지 않는다.)
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import router                                       # noqa: E402
from core import glossary as glossary_mod                     # noqa: E402


# ===========================================================================
# 임시 등록부 만들기 — 실제 registry.yaml 을 건드리지 않고 실패 상황을 만든다
# ===========================================================================

PARSERS = {"auto": "core.parse_adapter:parse"}


def _write_registry(tmp: Path, routes: list[dict], parsers=None) -> Path:
    p = tmp / "registry.yaml"
    p.write_text(yaml.safe_dump({"version": 1, "parsers": parsers or PARSERS,
                                 "routes": routes}, allow_unicode=True),
                 encoding="utf-8")
    return p


def _rel(path: Path) -> str:
    """Route.format/glossary 는 저장소 루트 기준 상대 경로다."""
    return os.path.relpath(path, ROOT)


def _write_glossary(tmp: Path, doc_type: str) -> Path:
    p = tmp / "t.glossary.yaml"
    p.write_text(yaml.safe_dump(
        {"version": 1, "doc_type": doc_type,
         "terms": {"신탁금액": {"kind": ["fact"], "value_type": "number"}}},
        allow_unicode=True), encoding="utf-8")
    return p


def _write_format(tmp: Path, doc_type: str) -> Path:
    p = tmp / "t.format.json"
    p.write_text(json.dumps(
        {"doc_type": doc_type, "format_version": 1,
         "regex_markers": [{"id": "조", "pattern": r"^제\s*(\d+)\s*조", "level": 0,
                            "groups": ["no"]}]}, ensure_ascii=False), encoding="utf-8")
    return p


# ===========================================================================
# 등록부 적재·검증
# ===========================================================================

def test_duplicate_doc_type_rejected():
    """같은 doc_type 이 두 번 등록되면 '같은 문서가 두 규칙을 갖는다' — 적재에서 막는다."""
    with pytest.raises(ValueError, match="두 번 등록"):
        router.Registry.model_validate({
            "parsers": PARSERS,
            "routes": [{"doc_type": "특정금전신탁"}, {"doc_type": "특정금전신탁"}]})


def test_unknown_parser_rejected():
    with pytest.raises(ValueError, match="parsers 에 없습니다"):
        router.Registry.model_validate({
            "parsers": PARSERS,
            "routes": [{"doc_type": "X", "parser": "없는파서"}]})


def test_parser_target_must_be_module_and_function():
    with pytest.raises(ValueError, match="모듈:함수"):
        router.Registry.model_validate({
            "parsers": {"auto": "core.parse_adapter"},
            "routes": [{"doc_type": "X"}]})


def test_threshold_out_of_range_rejected():
    with pytest.raises(ValueError, match="threshold"):
        router.Registry.model_validate({
            "parsers": PARSERS,
            "routes": [{"doc_type": "X", "threshold": 1.5}]})


def test_registry_file_is_loadable():
    reg = router.load()
    assert reg.routes and len(set(reg.doc_types())) == len(reg.doc_types())


# ===========================================================================
# 명시 모드
# ===========================================================================

def test_unregistered_doc_type_is_refused_with_a_suggestion():
    """오타·유사어를 조용히 삼키지 않는다. 대신 비슷한 이름을 알려 준다."""
    reg = router.load()
    with pytest.raises(router.UnregisteredDocType) as e:
        reg.get("금소법 시행령")
    msg = str(e.value)
    assert "금소법시행령" in msg and "혹시" in msg
    assert "registry.yaml" in msg          # 어떻게 고치는지까지 말한다


def test_unregistered_doc_type_lists_what_is_registered():
    reg = router.load()
    with pytest.raises(router.UnregisteredDocType) as e:
        reg.get("존재하지않는유형")
    for t in reg.doc_types():
        assert t in str(e.value)


def test_route_signature_has_no_asset_arguments():
    """이 시스템의 핵심 강제 — 호출자는 doc_type 만 말할 수 있다.

    route() 에 format/glossary 인자가 생기는 순간 에이전트가 자기 형식을 끼워 넣을
    수 있게 되고, 같은 doc_type 이 호출자마다 다르게 처리된다.
    """
    params = set(inspect.signature(router.route).parameters)
    assert not (params & {"format", "fmt", "glossary", "format_path", "glossary_path"})
    assert {"path", "doc_type"} <= params


# ===========================================================================
# 자산 — 형식·용어집·등록부 세 곳의 doc_type 이 같아야 한다
# ===========================================================================

def test_asset_doc_type_mismatch_is_refused(tmp_path):
    """형식이 다른 유형의 것이면 배차하지 않는다.

    어긋난 자산은 예외를 던지지 않고 **그럴듯하게** 굴러간다 — 마커가 하나도 안 맞는
    문서가 '부합률 낮음'으로만 나온다. 그래서 적재 시점에 막는다.
    """
    reg_path = _write_registry(tmp_path, [{
        "doc_type": "테스트유형",
        "glossary": _rel(_write_glossary(tmp_path, "테스트유형")),
        "format": _rel(_write_format(tmp_path, "엉뚱한유형")),      # ← 어긋남
    }])
    r = router.load(reg_path).get("테스트유형")
    with pytest.raises(router.RouteAssetMissing) as e:
        router.assets(r)
    assert "doc_type 이 다릅니다" in str(e.value) and "형식" in str(e.value)


def test_missing_asset_file_is_refused(tmp_path):
    reg_path = _write_registry(tmp_path, [{
        "doc_type": "테스트유형",
        "glossary": _rel(_write_glossary(tmp_path, "테스트유형")),
        "format": _rel(tmp_path / "없는파일.format.json"),
    }])
    with pytest.raises(router.RouteAssetMissing, match="형식 파일이 없습니다"):
        router.assets(router.load(reg_path).get("테스트유형"))


def test_route_without_assets_is_refused(tmp_path):
    """형식이 아예 없는 route 는 '등록됐지만 처리할 수 없는' 상태다 — 시끄럽게 말한다."""
    reg_path = _write_registry(tmp_path, [{"doc_type": "테스트유형"}])
    with pytest.raises(router.RouteAssetMissing, match="구조화할 수 없습니다"):
        router.assets(router.load(reg_path).get("테스트유형"))


@pytest.mark.parametrize("doc_type", router.load().doc_types())
def test_registered_route_assets_are_present_and_consistent(doc_type):
    """실제 등록부의 그물 — 자산이 사라지거나 doc_type 이 어긋나면 여기서 걸린다.

    등록만 해 두고 자산을 넣지 않은 route 는 런타임에야 RouteAssetMissing 으로
    드러난다. 그때는 이미 사용자가 문서를 넣은 뒤다. 여기서 먼저 잡는다.
    """
    r = router.load().get(doc_type)
    try:
        g, fmt = router.assets(r)         # 없거나 어긋나면 RouteAssetMissing
    except router.RouteAssetMissing as exc:
        pytest.fail(f"route '{doc_type}' (owner={r.owner or '?'}) 의 자산이 없습니다.\n"
                    f"  {exc}\n"
                    f"  등록부에 route 만 올리고 자산을 넣지 않으면 이 유형은 "
                    f"배차되지 않습니다 — 등록을 되돌리거나 자산을 넣으세요.")
    # 세 곳(등록부·용어집·형식)의 doc_type 이 같아야 "같은 문서를 같게 처리한다"가 선다.
    # 용어가 하나도 없는 용어집은 여기서 막지 않는다 — 마커만으로 잘리는 문서(전사)가
    # 실제로 있고, 억지 fact 용어는 게이트 경고만 늘린다.
    assert g.doc_type == fmt.doc_type == doc_type


@pytest.mark.parametrize("doc_type", router.load().doc_types())
def test_registered_parser_plugin_resolves(doc_type):
    """parsers 표의 '모듈:함수' 가 실제로 import 되는가 — 등록부의 거짓말을 잡는다."""
    reg = router.load()
    r = reg.get(doc_type)
    try:
        assert callable(reg.parser_for(r))
    except router.RoutingError as exc:
        pytest.fail(f"route '{doc_type}' (owner={r.owner or '?'}) 의 파서를 풀지 "
                    f"못했습니다.\n  {exc}")


def test_glossary_load_is_not_how_agents_get_assets():
    """참고 — 자산 적재의 유일한 경로는 route 다.

    (에이전트 코드가 glossary.load 를 직접 부르지 않는다는 강제는
     tests/architecture/test_no_bypass.py 가 한다. 여기서는 route 가 실제로
     같은 파일을 준다는 것만 확인한다.)
    """
    r = router.load().get("금소법")
    g, _fmt = router.assets(r)
    assert g.doc_type == "금소법"
    assert glossary_mod.load(ROOT / r.glossary).terms.keys() == g.terms.keys()
