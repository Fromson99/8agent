"""위키 생애 주기 — 적중 원장·4기준 보고서·규칙 전이 훅·triage 우선순위."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import wikiledger, wikilife                    # noqa: E402


def _wiki(tmp_path: Path) -> Path:
    """문답발 아티클 하나 + 해석례발 아티클 하나 + raw 파일들."""
    (tmp_path / "raw" / "expc").mkdir(parents=True)
    (tmp_path / "raw" / "conversations").mkdir(parents=True)
    (tmp_path / "raw" / "expc" / "2014-07-07-14-0342.md").write_text("원문", "utf-8")
    (tmp_path / "raw" / "conversations" / "2026-08-13-문답.md").write_text("문답", "utf-8")
    w = tmp_path / "wiki" / "갈래"
    w.mkdir(parents=True)
    (w / "해석례발.md").write_text(
        "# 해석례발\n\n> Raw: [14-0342](../../raw/expc/2014-07-07-14-0342.md)\n\n본문\n",
        "utf-8")
    (w / "문답발.md").write_text(
        "# 문답발\n\n> Raw: [문답](../../raw/conversations/2026-08-13-문답.md)\n\n"
        "rule:r1 을 인용한다.\n\n> **Status: Disputed**\n> 다툼 있음\n", "utf-8")
    (tmp_path / "wiki" / "index.md").write_text(
        "| Article | Summary | Updated |\n|---|---|---|\n"
        "| [해석례발](갈래/해석례발.md) | a | 2026-08-13 |\n"
        "| [문답발](갈래/문답발.md) | b | 2026-08-13 |\n", "utf-8")
    return tmp_path


def test_원장은_주입과_그_질의의_부검만_센다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(tmp_path))
    wikiledger.record("q1", "질문", ["갈래/해석례발"], answerable=True)
    wikiledger.record("q2", "질문2", ["갈래/해석례발", "갈래/문답발"], answerable=True)
    assert wikiledger.feedback("q1", "정답") is True
    assert wikiledger.feedback("q2", "오답") is True
    assert wikiledger.feedback("q-위키없음", "오답") is False   # 주입 없던 질의
    s = wikiledger.stats()
    assert s["갈래/해석례발"] == {"주입": 2, "정답": 1, "오답": 1,
                              "last": s["갈래/해석례발"]["last"]}
    assert s["갈래/문답발"]["주입"] == 1 and s["갈래/문답발"]["오답"] == 1


def test_생애_보고서_성숙과_권고(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    rep = wikilife.report()
    good = rep["갈래/해석례발"]
    assert good["성숙"]["해석례"] == 1 and good["권고"] == "유지"
    prov = rep["갈래/문답발"]
    # Disputed 블록 → 분쟁 중이 문답발(재검증 필요)보다 먼저 선다
    assert prov["권고"] == "분쟁 중"
    assert prov["안정"]["disputed"] == 1


def test_오답이_쌓이면_재컴파일_후보(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    for i in range(3):
        wikiledger.record(f"q{i}", "질문", ["갈래/해석례발"], answerable=True)
        wikiledger.feedback(f"q{i}", "오답")
    assert wikilife.report()["갈래/해석례발"]["권고"] == "재컴파일 후보"


def test_규칙_전이가_위키_연대기에_남는다(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_STORE", str(_wiki(tmp_path)))
    assert wikilife.note_rule_transition("r9", "규칙", "정착",
                                         rationale="이유", by="사람") is True
    assert wikilife.note_rule_transition("r9", "정착", "강등", by="사람") is True
    assert wikilife.note_rule_transition("r9", "잠정", "규칙") is False  # 위키 밖 전이
    log_md = (tmp_path / "wiki" / "log.md").read_text("utf-8")
    assert "컴파일 대기: 정착 규칙 rule:r9" in log_md
    assert "재심: 정착 강등 rule:r9" in log_md


def test_triage_우선순위는_오답이_먼저다():
    from lawrag.pipeline import wiki_triage
    cands = [
        {"qid": "a", "ts": "3", "feedbacks": []},
        {"qid": "b", "ts": "2", "feedbacks": [{"verdict": "정답"}]},
        {"qid": "c", "ts": "1", "feedbacks": [{"verdict": "오답"}]},
        {"qid": "d", "ts": "0", "feedbacks": []},
    ]
    ordered = [c["qid"] for c in wiki_triage.prioritize(cands, flagged={"d"})]
    # 오답(c=3) > 감사 지문(d=1.5) > 피드백만(b=1) > 무신호(a=0, ts 최신)
    assert ordered == ["c", "d", "b", "a"]
