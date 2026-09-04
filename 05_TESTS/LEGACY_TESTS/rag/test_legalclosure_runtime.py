from types import SimpleNamespace

from lawrag.core.rag import legalclosure_runtime
from lawrag.core.rag.assertion_shortcuts import (
    ShortcutIndex,
    ShortcutLoadResult,
)


def test_runtime_조립은_shortcut_상태를_감사메타에_보존한다(monkeypatch, tmp_path):
    monkeypatch.setenv("RAG_MAIN_PIPELINE_MANIFEST", str(tmp_path / "main.json"))
    registry_path = tmp_path / "canonical.json"
    registry_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "registry_path",
                        lambda: registry_path)
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "load_registry",
                        lambda path: "registry")
    monkeypatch.setattr(legalclosure_runtime, "canonical_fingerprint", lambda path: "fp")
    monkeypatch.setattr(legalclosure_runtime, "load_runtime", lambda **kwargs:
                        ShortcutLoadResult(ShortcutIndex([]), "stale", "store",
                                           reasons=("fingerprint",)))
    seen = {}

    def retrieve(index, question, registry, **kwargs):
        seen.update(registry=registry, shortcut=kwargs["shortcut_index"])
        return [], {"assertion": {"shortcut": {"used": False}}}

    monkeypatch.setattr(legalclosure_runtime.legalclosure, "retrieve", retrieve)
    sections, meta = legalclosure_runtime.retrieve(
        SimpleNamespace(), "질문", llm=None, shortcut_enabled=True)

    assert sections == [] and seen["registry"] == "registry"
    assert not seen["shortcut"].entries
    assert meta["runtime"]["shortcut_status"] == "stale"
    assert meta["runtime"]["main_pipeline"]["pipeline_id"] == "legalclosure-v2"
    assert meta["runtime"]["main_pipeline"]["generation"] == 0
    assert meta["assertion"]["shortcut"]["store"]["status"] == "stale"


def test_runtime_스위치가_꺼지면_저장소를_읽지_않는다(monkeypatch, tmp_path):
    monkeypatch.setenv("RAG_MAIN_PIPELINE_MANIFEST", str(tmp_path / "main.json"))
    registry_path = tmp_path / "canonical.json"
    registry_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "registry_path",
                        lambda: registry_path)
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "load_registry",
                        lambda path: object())
    monkeypatch.setattr(legalclosure_runtime, "load_runtime",
                        lambda **kwargs: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(legalclosure_runtime.legalclosure, "retrieve",
                        lambda *args, **kwargs: ([], {"assertion": {}}))

    _, meta = legalclosure_runtime.retrieve(
        SimpleNamespace(), "질문", llm=None, shortcut_enabled=False)

    assert meta["runtime"]["shortcut_status"] == "disabled"
    assert meta["legal_graph"]["status"] == "disabled"
    assert meta["legal_graph"]["load"]["status"] == "not_read"


def test_runtime_graph_switch_on일_때만_조건부_폐쇄를_조립한다(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("RAG_MAIN_PIPELINE_MANIFEST", str(tmp_path / "main.json"))
    registry_path = tmp_path / "canonical.json"
    registry_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "registry_path",
                        lambda: registry_path)
    monkeypatch.setattr(legalclosure_runtime.conceptfirst, "load_registry",
                        lambda path: object())
    baseline = [SimpleNamespace(doc_id="d", node=1, legal_meta={})]
    monkeypatch.setattr(legalclosure_runtime.legalclosure, "retrieve",
                        lambda *args, **kwargs: (baseline, {
                            "assertion": {}, "selected": [],
                            "legal_annotations": {"rows": []},
                            "strategy": "baseline",
                        }))
    seen = {}

    def extend(index, question, sections, **kwargs):
        seen.update(question=question, sections=sections, cap=kwargs["cap"])
        return sections, {"enabled": True, "status": "expanded", "added_count": 0}

    monkeypatch.setattr(
        legalclosure_runtime.legal_graph_closure, "extend_sections", extend
    )
    sections, meta = legalclosure_runtime.retrieve(
        SimpleNamespace(), "질문", llm=None, graph_enabled=True
    )
    assert sections == baseline and seen == {
        "question": "질문", "sections": baseline, "cap": 20,
    }
    assert meta["legal_graph"]["status"] == "expanded"
    assert meta["runtime"]["legal_graph_status"] == "expanded"
