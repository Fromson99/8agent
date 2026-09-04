"""Tier 1 전사 — 정의·별칭 정규식과 등재 게이트의 계약을 시험한다.

정밀도가 계약이다: Tier 1 은 신뢰도 최고 층이어야 하므로, 애매한 것을
잡는 것보다 확실한 것만 잡는 것이 맞다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.index import DocView                              # noqa: E402
from lawrag.core.terms import transcribe                               # noqa: E402


def _view(blocks_text, titles=None):
    """블록 텍스트 목록 → DocView. titles 는 {노드 제목: span} 지정."""
    titles = titles or {"본문": [0, len(blocks_text)]}
    nodes = [{"id": i + 1, "parent": None, "level": 1, "surface": "",
              "title": t, "page": 1, "span": s}
             for i, (t, s) in enumerate(titles.items())]
    blocks = [{"idx": i, "page": 1, "text": t, "kind": "text"}
              for i, t in enumerate(blocks_text)]
    return DocView.build("d1", {"name": "시험.pdf"}, {"nodes": nodes, "blocks": blocks})


def _terms(rows, pattern=None):
    return sorted({r["용어"] for r in rows if pattern is None or r["패턴"] == pattern})


# ---------------------------------------------------------------- 패턴
def test_인용정의():
    v = _view(['"금융소비자"란 금융상품에 관한 계약의 체결에 관한 자를 말한다.',
               '"전문금융소비자"라 함은 위험감수능력이 있는 자를 말한다.'])
    rows = transcribe.extract_doc(v)
    assert _terms(rows, "인용정의") == ["금융소비자", "전문금융소비자"]
    assert all(r["confidence"] == "high" for r in rows)


def test_비인용_정의는_정의조항_안에서만_high():
    text = "1. 적립금이란 가입자가 낸 부담금을 말한다."
    안 = _view([text], {"제2조(정의)": [0, 1]})
    밖 = _view([text], {"제5조(운용)": [0, 1]})
    assert [r["confidence"] for r in transcribe.extract_doc(안)
            if r["패턴"] == "정의"] == ["high"]
    assert [r["confidence"] for r in transcribe.extract_doc(밖)
            if r["패턴"] == "정의"] == ["medium"]


def test_이하별칭은_별칭이_등재_대상이다():
    v = _view(['금융소비자 보호에 관한 법률(이하 "금소법"이라 한다)에 따라 처리한다.'])
    rows = [r for r in transcribe.extract_doc(v) if r["패턴"] == "이하별칭"]
    assert [r["용어"] for r in rows] == ["금소법"]      # 본용어 파편이 아니라 별칭


def test_이하별칭_지시표현은_버린다():
    v = _view(['거치식예금(이하 "이 예금"이라 한다)은 만기에 지급한다.'])
    assert not [r for r in transcribe.extract_doc(v) if r["패턴"] == "이하별칭"]


def test_괄호약어는_대문자만_그리고_신용등급_제외():
    v = _view(["개인형퇴직연금(IRP)과 아이엠뱅크(AAA), 선물(Futures)과 제2조(정의)를 봐라."])
    rows = [r for r in transcribe.extract_doc(v) if r["패턴"] == "괄호약어"]
    assert [(r["용어"], r["별칭"]) for r in rows] == [("개인형퇴직연금", "IRP")]
    assert rows[0]["confidence"] == "medium"            # 한글 캡처는 어절에서 잘릴 수 있다


# ---------------------------------------------------------------- 등재
def test_등재_생애주기와_표면형_충돌_게이트(tmp_path):
    gl = tmp_path / "glossary.json"
    # 기존 파일에 수기 용어가 있다 — 같은 표면형을 다른 용어가 뺏으면 안 된다
    gl.write_text(json.dumps({"terms": [
        {"term": "개인형퇴직연금", "key": "개인형퇴직연금", "source": "수기",
         "status": "활성", "surfaces": ["개인형퇴직연금", "IRP"], "occurrences": []},
    ]}, ensure_ascii=False), encoding="utf-8")

    v = _view(['"적립금"이란 부담금 누계를 말한다. 기업형(IRP)도 있다.',
               "타깃데이트펀드(TDF)에 투자한다."])
    rep = transcribe.register(transcribe.extract_doc(v), gl)

    data = {t["key"]: t for t in
            json.loads(gl.read_text(encoding="utf-8"))["terms"]}
    # 인용정의 → 활성/high, 괄호약어만 있는 것 → 잠정/medium
    assert data["적립금"]["status"] == "활성"
    assert data["적립금"]["source"] == "tier1"
    assert data["타깃데이트펀드"]["status"] == "잠정"
    assert "TDF" in data["타깃데이트펀드"]["surfaces"]
    # "IRP" 는 기존 용어의 표면형이다 — 새 용어(기업형)로 뺏기지 않는다
    assert any(c["surface"] == "IRP" for c in rep["conflicts"])
    assert "IRP" not in data.get("기업형", {}).get("surfaces", [])


def test_등재_같은_키는_증거가_늘어난다(tmp_path):
    gl = tmp_path / "glossary.json"
    v = _view(['"수익자"란 이익을 받는 자를 말한다.'])
    transcribe.register(transcribe.extract_doc(v), gl)
    transcribe.register(transcribe.extract_doc(v), gl)
    rows = json.loads(gl.read_text(encoding="utf-8"))["terms"]
    assert len(rows) == 1
    assert len(rows[0]["occurrences"]) == 1     # 같은 (문서, 블록) 은 한 번만
