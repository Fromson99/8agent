from types import SimpleNamespace

from scripts import rag_legalclosure_stage_ablation as ablation


def _row(name, *, mandatory=False):
    return SimpleNamespace(coordinate=("d", name), mandatory=mandatory)


def test_stage_ablation은_D_제거와_verifier_우선순서를_독립비교한다(monkeypatch):
    a, b, c = _row("a"), _row("b"), _row("c")
    mandatory, optional, verifier = (
        _row("mandatory", mandatory=True), _row("optional"), _row("verifier"))
    monkeypatch.setattr(
        ablation, "_rescue",
        lambda *args, **kwargs: ([verifier], {"selected": [{"node": "verifier"}]}))
    monkeypatch.setattr(
        ablation.legal_conditional_closure, "select",
        lambda *args, **kwargs: ([mandatory], {"selected": [{"node": "mandatory"}]}))

    variants, _ = ablation._select(
        object(), "질문", (), [a], [b], [c], [mandatory, optional])

    coords = {name: [row.coordinate[1] for row in selected]
              for name, (selected, _audit) in variants.items()}
    assert coords["control_d_then_verifier"] == [
        "a", "b", "c", "mandatory", "optional", "verifier"]
    assert coords["abc_only"] == ["a", "b", "c"]
    assert coords["abc_then_verifier"] == ["a", "b", "c", "verifier"]
    assert coords["mandatory_d_then_verifier"] == [
        "a", "b", "c", "mandatory", "verifier"]
    assert coords["verifier_then_d"] == [
        "a", "b", "c", "verifier", "mandatory", "optional"]
    assert coords["verifier_then_conditional_d"] == [
        "a", "b", "c", "verifier", "mandatory"]
