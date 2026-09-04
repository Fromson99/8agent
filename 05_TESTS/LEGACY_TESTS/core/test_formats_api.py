"""형식(구조화 틀) API — UI 컴파일·등재·바인딩, 그리고 바인딩된 문서의 해석 경로.

여기서 지키는 것 셋:
  (1) 등록부에 route 를 올리되 **주석을 태우지 않는다** (실측 기록이 주석에 산다).
  (2) 사람이 손으로 등록한 route 는 UI 가 덮어쓰지 않는다.
  (3) 바인딩된 문서는 유도가 아니라 **형식 마커**로 잘린다 (stats.source 가 증거).

docling 을 부르지 않도록 마크다운 문서로 돈다 — 파싱 경로는 이미 다른 파일이 지킨다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="FastAPI 필요")

SAMPLE = """# 제1장 총칙

제1조(목적) 이 규정은 시험을 위한 것이다.

① 첫째 항이다.

② 둘째 항이다.

1. 첫째 호이다.

2. 둘째 호이다.

제2조(정의) 이 규정에서 쓰는 말의 뜻은 다음과 같다.

① 정의의 첫째 항이다.

제3조(적용) 이 규정은 시험에만 쓴다.
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """스토어·바인딩·형식 저장소를 tmp 로 갈아끼운 앱. 등록부는 사본을 쓴다."""
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("STRUCTURE_STORE", str(store))
    monkeypatch.setenv("STRUCTURE_LEDGER", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("FORMAT_BINDINGS", str(tmp_path / "bindings.json"))
    monkeypatch.setenv("FORMAT_CANVAS", str(tmp_path / "canvas.json"))
    monkeypatch.setenv("FORMATS_DIR", str(tmp_path / "formats"))

    for mod in [m for m in list(sys.modules)
                if m.startswith(("lawrag.api.routers", "lawrag.api.structure_app"))]:
        del sys.modules[mod]

    from fastapi.testclient import TestClient

    from lawrag.api.structure_app import app

    # 등록부는 **사본**을 고치게 한다 — 시험이 저장소의 registry.yaml 을 건드리면 안 된다.
    reg_copy = tmp_path / "registry.yaml"
    reg_copy.write_text((ROOT / "lawrag" / "core" / "registry.yaml").read_text(encoding="utf-8"),
                        encoding="utf-8")

    from lawrag.core import router as core_router
    monkeypatch.setattr(core_router, "DEFAULT_REGISTRY", reg_copy)
    core_router.load.cache_clear()

    c = TestClient(app)
    c._store = store                       # 시험이 스토어를 직접 들여다볼 수 있게
    c._registry = reg_copy
    yield c
    core_router.load.cache_clear()


def _put_doc(client, doc_id: str, name: str, folder: str, body: str = SAMPLE) -> None:
    """스토어에 문서 하나를 손으로 놓는다 — 업로드는 docling/합성 PDF 를 부른다."""
    from lawrag.core import parse_adapter
    from lawrag.core.structure import synthpdf

    d = client._store / doc_id
    d.mkdir(parents=True, exist_ok=True)
    md = d / "source.md"
    md.write_text(body, encoding="utf-8")
    parsed = parse_adapter.parse(md)
    (d / "source.pdf").write_bytes(synthpdf.paginate(parsed.elements))
    (d / "parse.json").write_text(
        json.dumps(parse_adapter.result_to_dump(parsed), ensure_ascii=False),
        encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({"doc_id": doc_id, "name": name, "folder": folder},
                   ensure_ascii=False), encoding="utf-8")


def _compile(client, **kw):
    body = {"doc_type": "시험규정", "folder": "시험폴더", "threshold": 0.5}
    body.update(kw)
    return client.post("/v1/formats/compile", json=body)


def test_compile_needs_two_samples(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    r = _compile(client)
    assert r.status_code == 400 and "2개 이상" in r.json()["detail"]


def test_compile_registers_and_binds(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    r = _compile(client)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["doc_type"] == "시험규정"
    assert any(m["id"] == "조" for m in j["markers"])       # 조 마커를 찾아냈다
    assert all(a["passed"] for a in j["applied"])
    assert j["bound_folder"] == "시험폴더"

    # 등록부에 올랐고, 바인딩이 남았다
    assert "시험규정" in [x["doc_type"] for x in client.get("/v1/formats").json()["routes"]]
    assert client.get("/v1/formats/bindings").json()["folders"]["시험폴더"] == "시험규정"


def test_registry_comments_survive(client):
    """route 를 올리며 파일을 통째로 재직렬화하면 실측 기록(주석)이 날아간다."""
    before = client._registry.read_text(encoding="utf-8")
    n_comments = sum(1 for ln in before.splitlines() if ln.lstrip().startswith("#"))
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    after = client._registry.read_text(encoding="utf-8")
    assert sum(1 for ln in after.splitlines()
               if ln.lstrip().startswith("#")) >= n_comments


def test_recompile_needs_overwrite_and_replaces_block(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    assert _compile(client).status_code == 409                 # 말없이 갈아끼우지 않는다
    assert _compile(client, overwrite=True).status_code == 200
    # route 가 두 벌이 되면 등록부 적재가 "두 번 등록"으로 터진다
    assert client._registry.read_text(encoding="utf-8").count("doc_type: 시험규정") == 1


def test_human_route_is_not_overwritten(client):
    """사람이 손으로 등록한 route 는 UI 가 덮어쓰지 않는다 — 자산이 딸려 있다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    r = _compile(client, doc_type="금소법", overwrite=True)
    assert r.status_code == 409 and "사람이 등록한" in r.json()["detail"]


def test_binding_requires_registered_type(client):
    r = client.put("/v1/formats/bindings",
                   json={"scope": "folder", "key": "아무폴더", "doc_type": "없는유형"})
    assert r.status_code == 404


def test_bound_document_is_cut_by_the_format(client):
    """바인딩된 폴더의 문서는 유도가 아니라 형식 마커로 잘린다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200

    r = client.post(f"/v1/structure/{'a' * 16}/reinterpret")
    assert r.status_code == 200, r.text
    payload = client.get(f"/v1/structure/{'a' * 16}").json()
    assert payload["bound_doc_type"] == "시험규정"
    assert payload["stats"]["source"] == "format:시험규정"
    fams = {n["family"] for n in payload["nodes"]}
    assert "조" in fams and "항" in fams
    # 형식 경로에도 좌표가 실린다 — 검수 화면이 원본 위에 겹쳐 그릴 수 있어야 한다
    assert any(b.get("rect") for b in payload["blocks"])


def test_unbinding_returns_to_induction(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    client.put("/v1/formats/bindings",
               json={"scope": "folder", "key": "시험폴더", "doc_type": None})
    client.post(f"/v1/structure/{'a' * 16}/reinterpret")
    payload = client.get(f"/v1/structure/{'a' * 16}").json()
    assert not payload.get("bound_doc_type")
    assert payload["stats"].get("source") != "format:시험규정"


def _put_lawxml_doc(client, doc_id: str, name: str, folder: str) -> None:
    """법령 XML 인제스트분의 모양 — source.xml + 검수용 **합성** source.pdf, parse.json 없음."""
    d = client._store / doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.xml").write_text("<법령/>", encoding="utf-8")
    (d / "source.pdf").write_bytes(b"%PDF-1.7 synthetic")
    (d / "meta.json").write_text(
        json.dumps({"doc_id": doc_id, "name": name, "folder": folder,
                    "source_kind": "lawxml"}, ensure_ascii=False), encoding="utf-8")


def test_source_kind_is_reported_per_document(client):
    """원본 형식이 흐름을 가른다 — 목록이 그것을 말하지 않으면 화면이 알 수 없다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_lawxml_doc(client, "c" * 16, "법률.xml", "시험폴더")
    kinds = {d["name"]: d.get("source_kind")
             for d in client.get("/v1/structure/documents").json()["documents"]}
    assert kinds["법률.xml"] == "lawxml"
    assert kinds["하나.md"] == "pdf"       # 합성 지면을 얹은 문서는 pdf 로 보인다


def test_lawxml_is_skipped_as_a_sample(client):
    """법령 XML 을 샘플로 쓰면 원문이 아니라 **합성 지면**을 배운다 — 이름을 대고 뺀다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    _put_lawxml_doc(client, "c" * 16, "법률.xml", "시험폴더")
    r = _compile(client)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [s["doc_id"] for s in j["skipped"]] == ["c" * 16]
    assert "법령 XML" in j["skipped"][0]["reason"]
    assert {a["doc_id"] for a in j["applied"]} == {"a" * 16, "b" * 16}
    assert j["kinds"] == ["pdf"]


def test_lawxml_cannot_be_bound(client):
    _put_lawxml_doc(client, "c" * 16, "법률.xml", "시험폴더")
    _put_doc(client, "a" * 16, "하나.md", "다른폴더")
    _put_doc(client, "b" * 16, "둘.md", "다른폴더")
    assert _compile(client, folder="다른폴더").status_code == 200
    r = client.put("/v1/formats/bindings",
                   json={"scope": "doc", "key": "c" * 16, "doc_type": "시험규정"})
    assert r.status_code == 400 and "태그 계층" in r.json()["detail"]


def test_mixed_source_kinds_warn_and_are_reported(client):
    """pdf 와 hwp 를 섞어 유도하면 한쪽에서만 도는 규칙이 될 수 있다 — 막지 말고 말한다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    # 두 번째 문서를 hwp 원본에서 온 것으로 만든다(합성 지면은 그대로)
    d = client._store / ("b" * 16)
    (d / "source.hwp").write_bytes(b"\xd0\xcf\x11\xe0dummy")
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta["source_kind"] = "hwp"
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    j = _compile(client).json()
    assert j["kinds"] == ["hwp", "pdf"]
    assert {a["kind"] for a in j["applied"]} == {"hwp", "pdf"}
    assert any("형식이 섞였습니다" in w for w in j["warnings"])


def test_canvas_round_trips(client):
    """캔버스는 **화면의 기억**이다 — 이어 놓은 초안이 새로고침에 날아가면 못 쓴다."""
    assert client.get("/v1/formats/canvas").json() == {"pos": {}, "drafts": [],
                                                       "open": [], "rev": 0}
    body = {"pos": {"folder:시험폴더": [60, 30]},
            "drafts": [{"id": "d1", "name": "새 구조화 1",
                        "folders": ["시험폴더"], "docs": []}],
            "rev": 0}
    assert client.put("/v1/formats/canvas", json=body).status_code == 200
    back = client.get("/v1/formats/canvas").json()
    assert back["pos"]["folder:시험폴더"] == [60, 30]
    assert back["drafts"][0]["folders"] == ["시험폴더"]
    assert back["rev"] == 1


def test_canvas_detects_a_concurrent_save(client):
    """탭 두 개 — 나중 저장이 앞의 것을 말없이 지우면 안 된다."""
    first = {"pos": {"folder:A": [10, 10]}, "drafts": [], "rev": 0}
    assert client.put("/v1/formats/canvas", json=first).status_code == 200
    stale = {"pos": {"folder:B": [20, 20]}, "drafts": [], "rev": 0}   # 옛 rev
    r = client.put("/v1/formats/canvas", json=stale)
    assert r.status_code == 409 and "먼저 저장" in r.json()["detail"]
    assert client.get("/v1/formats/canvas").json()["pos"] == {"folder:A": [10, 10]}


def test_compile_from_folders_and_loose_docs(client):
    """캔버스가 보내는 모양 — 폴더 여럿 + 낱개 문서. 낱개는 **예외 바인딩**이 된다."""
    _put_doc(client, "a" * 16, "하나.md", "폴더A")
    _put_doc(client, "b" * 16, "둘.md", "폴더B")
    _put_doc(client, "c" * 16, "셋.md", "")            # 미분류 — 낱개로 이은 것
    r = client.post("/v1/formats/compile", json={
        "doc_type": "여럿규정", "folders": ["폴더A", "폴더B"], "doc_ids": ["c" * 16],
        "threshold": 0.5})
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j["bound_folders"]) == {"폴더A", "폴더B"}
    assert j["bound_docs"] == ["c" * 16]              # 폴더가 덮지 않는 것만 예외로
    b = client.get("/v1/formats/bindings").json()
    assert b["folders"] == {"폴더A": "여럿규정", "폴더B": "여럿규정"}
    assert b["docs"] == {"c" * 16: "여럿규정"}


def test_folder_docs_are_not_bound_individually(client):
    """폴더로 이어진 문서까지 낱개로 걸면, 폴더 연결을 풀어도 예외가 남아 안 풀린다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    r = client.post("/v1/formats/compile", json={
        "doc_type": "시험규정", "folders": ["시험폴더"],
        "doc_ids": ["a" * 16], "threshold": 0.5})
    assert r.status_code == 200
    assert client.get("/v1/formats/bindings").json()["docs"] == {}


def test_deleting_a_document_forgets_its_binding(client):
    """죽은 doc_id 가 표에 남으면, 같은 파일을 다시 올릴 때(같은 sha) 옛 연결이 되살아난다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client, bind=False).status_code == 200
    client.put("/v1/formats/bindings",
               json={"scope": "doc", "key": "a" * 16, "doc_type": "시험규정"})
    client.put("/v1/formats/canvas",
               json={"pos": {f"doc:{'a' * 16}": [1, 2]},
                     "drafts": [{"id": "d1", "name": "x", "folders": [],
                                 "docs": ["a" * 16]}], "rev": 0})
    assert client.delete(f"/v1/structure/{'a' * 16}").status_code == 200
    assert client.get("/v1/formats/bindings").json()["docs"] == {}
    c = client.get("/v1/formats/canvas").json()
    assert c["pos"] == {} and c["drafts"][0]["docs"] == []


def test_renaming_a_folder_carries_the_binding(client):
    """연결은 폴더 **이름**으로 걸린다 — 따라가지 않으면 조용히 끊긴다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    r = client.patch("/v1/structure/folders/시험폴더", json={"name": "새이름"})
    assert r.status_code == 200
    assert client.get("/v1/formats/bindings").json()["folders"] == {"새이름": "시험규정"}


def test_deleting_a_folder_forgets_the_binding(client):
    """남기면 같은 이름으로 폴더를 다시 만들 때 죽은 줄 알았던 틀이 되살아난다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    assert client.delete("/v1/structure/folders/시험폴더").status_code == 200
    assert client.get("/v1/formats/bindings").json()["folders"] == {}


def test_stale_result_is_flagged(client):
    """연결을 바꾸면 저장된 결과는 낡는다 — 다시 해석하기 전까지 그렇다고 말해야 한다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200          # 폴더가 틀에 묶인다

    docs = {d["doc_id"]: d for d in client.get("/v1/structure/documents").json()["documents"]}
    assert docs["a" * 16]["stale"] is True              # 아직 유도 결과가 저장돼 있다
    assert docs["a" * 16]["expected_structured_by"] == "format:시험규정@v1"

    client.post(f"/v1/structure/{'a' * 16}/reinterpret")
    docs = {d["doc_id"]: d for d in client.get("/v1/structure/documents").json()["documents"]}
    assert not docs["a" * 16].get("stale")
    assert docs["a" * 16]["structured_by"] == "format:시험규정@v1"


def test_recompiling_bumps_the_version_and_stales_results(client):
    """틀을 다시 만들면 이미 잘린 문서는 옛 틀 결과다 — 버전으로 그것을 잡는다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    client.post(f"/v1/structure/{'a' * 16}/reinterpret")
    assert _compile(client, overwrite=True).status_code == 200      # v2
    docs = {d["doc_id"]: d for d in client.get("/v1/structure/documents").json()["documents"]}
    assert docs["a" * 16]["stale"] is True
    assert docs["a" * 16]["expected_structured_by"] == "format:시험규정@v2"


def test_format_delete_refuses_while_bound_then_cleans_up(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    r = client.delete("/v1/formats/시험규정")
    assert r.status_code == 409 and "연결된 것이 있습니다" in r.json()["detail"]
    r = client.delete("/v1/formats/시험규정?force=true")
    assert r.status_code == 200
    assert client.get("/v1/formats/bindings").json()["folders"] == {}
    assert "시험규정" not in [x["doc_type"]
                           for x in client.get("/v1/formats").json()["routes"]]


def test_human_format_is_not_deletable(client):
    r = client.delete("/v1/formats/금소법")
    assert r.status_code == 409 and "사람이 등록한" in r.json()["detail"]


def test_orphan_bindings_are_reported_not_hidden(client):
    """틀이 사라졌는데 연결이 남으면 — 지우면 '왜 풀렸지', 두면 '왜 안 잘리지'. 말해 준다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    # 등록부에서만 지운다(연결은 그대로) — 사람이 registry.yaml 을 고친 상황
    text = client._registry.read_text(encoding="utf-8")
    import re as _re
    client._registry.write_text(
        _re.sub(r"[ \t]*# --- ui-compiled: 시험규정 ---\n(?:.*\n)*?[ \t]*# --- /ui-compiled: 시험규정 ---\n?",
                "", text), encoding="utf-8")
    from lawrag.core import router as core_router
    core_router.load.cache_clear()
    j = client.get("/v1/formats").json()
    assert j["orphans"] == [{"scope": "folder", "key": "시험폴더", "doc_type": "시험규정"}]


def test_format_rules_are_readable(client):
    """틀을 눌렀을 때 **무엇을 보고 자르는지**가 안 보이면 결과를 의심할 수밖에 없다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    j = client.get("/v1/formats/시험규정/rules").json()
    assert j["doc_type"] == "시험규정" and j["owner"] == "ui"
    ids = [m["id"] for m in j["regex_markers"]]
    assert "조" in ids
    assert all({"id", "level", "pattern"} <= set(m) for m in j["regex_markers"])
    assert j["bound_folders"] == ["시험폴더"]
    assert j["format_version"] == 1
    assert client.get("/v1/formats/없는틀/rules").status_code == 404


def test_editing_a_marker_bumps_version_and_stales_docs(client):
    """규칙 한 줄을 고치는 길 — 다시 컴파일하지 않고. 고치면 결과가 낡아야 한다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    client.post(f"/v1/structure/{'a' * 16}/reinterpret")

    r = client.patch("/v1/formats/시험규정/rules", json={
        "markers": [{"id": "조", "pattern": r"^제\s*(\d+)\s*조", "level": 1}],
        "note": "괄호 없는 조도 잡게"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["format_version"] == 2 and j["changed"] == ["수정 조"]
    assert j["affected"] == ["시험폴더"]

    docs = {d["doc_id"]: d for d in client.get("/v1/structure/documents").json()["documents"]}
    assert docs["a" * 16]["stale"] is True          # 고친 규칙은 다시 해석해야 반영된다
    rules = client.get("/v1/formats/시험규정/rules").json()
    assert next(m for m in rules["regex_markers"] if m["id"] == "조")["pattern"] \
        == r"^제\s*(\d+)\s*조"


def test_broken_regex_is_refused(client):
    """깨진 패턴이 들어가면 그 유형의 **모든** 문서가 구조화에서 터진다 — 입구에서 막는다."""
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    r = client.patch("/v1/formats/시험규정/rules",
                     json={"markers": [{"id": "조", "pattern": "^제(\\d+"}]})
    assert r.status_code == 422 and "정규식이 깨졌습니다" in r.json()["detail"]
    r = client.patch("/v1/formats/시험규정/rules",
                     json={"markers": [{"id": "조", "pattern": "제(\\d+)조"}]})
    assert r.status_code == 422 and "^ 로 시작" in r.json()["detail"]


def test_cannot_empty_a_format(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    ids = [m["id"] for m in client.get("/v1/formats/시험규정/rules").json()["regex_markers"]]
    r = client.patch("/v1/formats/시험규정/rules",
                     json={"markers": [{"id": i, "delete": True} for i in ids]})
    assert r.status_code == 422 and "아무것도 자르지 못합니다" in r.json()["detail"]


def test_human_format_rules_are_not_editable(client):
    r = client.patch("/v1/formats/금소법/rules",
                     json={"markers": [{"id": "조", "level": 2}]})
    assert r.status_code == 409 and "사람이 관리하는" in r.json()["detail"]


def test_builtin_rules_are_readable(client):
    """법령 XML 도 규칙이 있다 — 정규식이 아니라 태그라는 것만 다르다."""
    j = client.get("/v1/formats/builtin/lawxml").json()
    assert j["order"][:3] == ["편", "장", "절"] and j["deterministic"] is True
    assert any("합성 지면" in n for n in j["notes"])
    assert client.get("/v1/formats/builtin/없는것").status_code == 404


def test_canvas_remembers_open_folders(client):
    body = {"pos": {}, "drafts": [], "open": ["시험폴더"], "rev": 0}
    assert client.put("/v1/formats/canvas", json=body).status_code == 200
    assert client.get("/v1/formats/canvas").json()["open"] == ["시험폴더"]


def test_warm_parse_is_idempotent(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    r = client.post(f"/v1/structure/{'a' * 16}/parse")
    assert r.status_code == 200 and r.json()["cached"] is True   # _put_doc 이 이미 만든다


def test_doc_binding_beats_folder_binding(client):
    _put_doc(client, "a" * 16, "하나.md", "시험폴더")
    _put_doc(client, "b" * 16, "둘.md", "시험폴더")
    assert _compile(client).status_code == 200
    # 문서 하나만 연결을 풀면(null) 폴더 바인딩이 여전히 적용된다 —
    # 해제는 doc 표에 남지 않으므로, 여기서는 다른 유형으로 덮어써 우선순위를 본다
    assert _compile(client, doc_type="시험규정2", folder="시험폴더",
                    bind=False).status_code == 200
    client.put("/v1/formats/bindings",
               json={"scope": "doc", "key": "a" * 16, "doc_type": "시험규정2"})
    client.post(f"/v1/structure/{'a' * 16}/reinterpret")
    assert client.get(f"/v1/structure/{'a' * 16}").json()["bound_doc_type"] == "시험규정2"
    client.post(f"/v1/structure/{'b' * 16}/reinterpret")
    assert client.get(f"/v1/structure/{'b' * 16}").json()["bound_doc_type"] == "시험규정"
