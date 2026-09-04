"""검토 파이프라인 — 사실·쟁점·규범·포섭·결론 (docs/REVIEW.md).

지키는 것 다섯:
  (1) 다섯 타입이 도메인 무관하고, '불명'이 되먹임의 씨앗으로 조회된다.
  (2) 결론 규칙은 보수적이다 — 불충족>불명>충족 순으로 강하게 접힌다.
  (3) 얇은 관통이 상태 하나를 갱신하며 다섯 단계를 지난다(LLM 대역으로).
  (4) 원장은 자산명이 있을 때만 적재하고, 같은 자리는 갱신한다(이력 아님).
  (5) 역인덱스가 조문 → 자산을 되짚는다 (트랙 A 의 입구).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.index import Index                              # noqa: E402
from lawrag.core.casereview import binding as binding_mod                # noqa: E402
from lawrag.core.casereview import pipeline as rp                        # noqa: E402
from lawrag.core.casereview.model import (Fact, Issue, Norm, Req,        # noqa: E402
                               ReviewState, Sub, req_leaves)


class _FakeLLM:
    """kind 별로 정해진 응답을 내는 대역 — 검토는 LLM 콜이 셋이다."""

    def __init__(self, by_kind: dict):
        self.by_kind = by_kind
        self.calls: list = []

    def structured(self, kind, system, user, schema, **kw):
        self.calls.append({"kind": kind, "user": user})
        out = self.by_kind.get(kind)
        return out(user) if callable(out) else out


def _doc():
    return ("L1", {"name": "개인정보 보호법"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제18조",
         "title": "목적 외 이용·제공 제한", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text",
         "text": "제18조(목적 외 이용·제공 제한) 개인정보처리자는 개인정보를 "
                 "목적 외로 제공하여서는 아니 된다. 다만, 다른 법률에 특별한 "
                 "규정이 있는 경우에는 그러하지 아니하다."},
    ]})


def _wiki(tmp_path, monkeypatch):
    w = tmp_path / "wiki"
    (w / "쟁점").mkdir(parents=True)
    (w / "쟁점" / "목적외-제공.md").write_text(
        "# 목적 외 제공\n\n> 트리거: 제공 · 목적 외 · 개인정보\n"
        "> 판단 축: 다른 법률이 종류·범위·요건을 명시하는가\n"
        "> 조문 후보: 개인정보 보호법\n\n본문.\n", "utf-8")
    (w / "index.md").write_text(
        "# 인덱스\n\n| Article | Summary | Updated |\n|---|---|---|\n"
        "| [목적 외 제공](쟁점/목적외-제공.md) | 목적 외 | 2026-08-14 |\n", "utf-8")
    monkeypatch.setenv("WIKI_STORE", str(tmp_path))


# ---------------------------------------------------------------- 타입
def test_불명이_되먹임의_씨앗으로_조회된다():
    st = ReviewState(question="q")
    st.subs = [Sub(issue_id="i1", norm_id="n1", req_id="r1", judgment="충족"),
               Sub(issue_id="i1", norm_id="n1", req_id="r2", judgment="불명"),
               Sub(issue_id="i1", norm_id="n1", req_id="r3", judgment="해당없음")]
    assert [s.req_id for s in st.unresolved()] == ["r2"]


def test_요건_트리는_재귀로_잎만_평평해진다():
    tree = [Req(text="A", op="OR", children=[Req(text="a1"), Req(text="a2")]),
            Req(text="B")]
    assert [r.text for r in req_leaves(tree)] == ["a1", "a2", "B"]


# ---------------------------------------------------------------- 결론
def test_결론은_보수적으로_접힌다():
    i = Issue(question="q")
    def subs(*js):
        return [Sub(issue_id=i.id, norm_id="n", req_id=f"r{k}", judgment=j)
                for k, j in enumerate(js)]
    assert rp.conclude(i, subs("충족", "충족")).conclusion == "가능"
    assert rp.conclude(i, subs("충족", "불명")).conclusion == "조건부"
    assert rp.conclude(i, subs("불명", "불충족")).conclusion == "불가"   # 불충족이 이긴다
    assert rp.conclude(i, subs("해당없음")).conclusion == "판단보류"
    assert rp.conclude(i, []).conclusion == "판단보류"
    v = rp.conclude(i, subs("충족", "불명"))
    assert v.unmet and v.actions                     # 불명이면 보완 액션이 선다


# ---------------------------------------------------------------- 관통
def test_얇은_관통이_다섯_단계를_지난다(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    idx = Index.from_docs([_doc()])

    def subsume_out(user):
        # 요건 id 는 프롬프트에 실린 것을 그대로 쓴다 — 지어낸 id 는 버려진다
        import re
        ids = re.findall(r"\[(r[^\]]+)\]", user)      # 좌표 id (rL1-3 꼴)
        return {"subs": [
            {"req_id": ids[0], "judgment": "충족", "facts": [], "reason": "명시"},
            {"req_id": "r000000", "judgment": "충족", "facts": [], "reason": "환각"},
        ] + ([{"req_id": ids[1], "judgment": "불명", "facts": [],
               "reason": "사실 부족"}] if len(ids) > 1 else [])}

    llm = _FakeLLM({
        "review.facts": {"facts": [
            {"text": "A사가 고객 정보를 B사에 제공한다", "subject": "A사",
             "action": "제공", "object": "고객 개인정보", "tense": "계획"}]},
        "review.issues": {"issues": [
            {"question": "목적 외 제공이 허용되는가?", "gate": "개인정보를 다루는가",
             "card": "쟁점/목적외-제공", "regulation": "수평"}]},
        "review.subsume": subsume_out,
    })
    st = rp.run(llm, idx, "A사가 고객 개인정보를 B사에 제공하려 한다.",
                track="적법성")

    assert [f.tense for f in st.facts] == ["계획"]           # ① 시제가 산다
    assert st.issues[0].card == "쟁점/목적외-제공"            # ② 카드가 붙는다
    assert st.issues[0].axis.startswith("다른 법률")         # 판단 축을 카드에서 가져온다
    assert st.norms and st.norms[0].doc == "개인정보 보호법"   # ③ 회수가 규범이 된다
    assert st.subs and all(s.req_id != "r000000" for s in st.subs)  # ④ 환각 id 는 버린다
    assert st.verdicts[0].conclusion in ("가능", "조건부")    # ⑤ 결론이 선다
    # 2026-08-18 재구조화 — 회수가 쟁점보다 앞이다 (회수 1회 → 조문을 보고 쟁점 판정)
    assert [t["stage"] for t in st.trail] == [
        "사실 확정", "용어집", "회수", "쟁점 판정", "규범 조립", "포섭", "결론"]
    assert st.to_dict()["rid"] == st.rid                     # 직렬화가 돈다


# ---------------------------------------------------------------- ③ 규범 조립
def _two_docs():
    """배경 법(자본시장법)과 쟁점이 지목한 법(개인정보 보호법) + 삭제 조문."""
    cap = ("L1", {"name": "자본시장과 금융투자업에 관한 법률"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제6조",
         "title": "금융투자업", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text",
         "text": "제6조(금융투자업) 이 법에서 금융투자업이란 투자매매업을 말한다."},
    ]})
    priv = ("L2", {"name": "개인정보 보호법"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제17조",
         "title": "개인정보의 제공", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제32조",
         "title": "", "page": 1, "span": [1, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text",
         "text": "제17조(개인정보의 제공) 개인정보처리자는 정보주체의 동의를 받은 "
                 "경우 개인정보를 제3자에게 제공할 수 있다."},
        {"idx": 1, "page": 1, "kind": "text", "text": "제32조 삭제 <2016.7.28>"},
    ]})
    return cap, priv


def test_삭제된_조문은_규범이_되지_않는다():
    assert rp._is_deleted("제32조 삭제 <2016.7.28>")
    assert rp._is_deleted("  삭제  ")
    assert not rp._is_deleted("제17조(개인정보의 제공) 개인정보처리자는 …")


def test_카드_조문_후보는_좌표로_열리지_않는다_검색이_찾는다(tmp_path, monkeypatch):
    """카드의 소임은 문체 번역이지 좌표 연결이 아니다 (2026-08-18 결정).

    옛 판은 카드 조문 후보(개보법 제17조)를 좌표로 열어 앞자리에 세웠다. 이제
    그 길이 없고, 개보법은 **검색이 스스로** 찾아야 한다 — 쟁점 문장에 그 법의
    조 제목 낱말('개인정보', '제공')이 있으니 어휘 사다리가 문다. 카드가 좌표를
    밀어 넣던 실측 오탐(18-0124: 후보 제81조의13이 정답 제84조를 밀어냄)이 이
    바뀜의 이유다."""
    w = tmp_path / "wiki"
    (w / "쟁점").mkdir(parents=True)
    (w / "쟁점" / "동의와-정보이용.md").write_text(
        "# 동의와 정보이용\n\n> 트리거: 동의 · 제공\n"
        "> 판단 축: 동의를 받았는가\n"
        "> 조문 후보: 「개인정보 보호법」 제17조제1항\n\n본문.\n", "utf-8")
    (w / "index.md").write_text(
        "# 인덱스\n\n| Article | Summary | Updated |\n|---|---|---|\n"
        "| [동의와 정보이용](쟁점/동의와-정보이용.md) | 동의 | 2026-08-14 |\n", "utf-8")
    monkeypatch.setenv("WIKI_STORE", str(tmp_path))
    idx = Index.from_docs([*_two_docs()])
    st = ReviewState(question="q")
    # 질문은 증권사 배경이라 트리거("동의"·"제공")가 안 물지만, 카드가 지목돼 있고
    # 쟁점 문장이 개인정보 보호법을 언급한다 — 카드 조문 후보는 쟁점·질문이 그 법을
    # 말할 때만 열린다(15-0720 실측: 안 그러면 카드 컴파일 사례의 조문이 무관하게 딸려 온다)
    # ① 쟁점 문장에 조 제목 낱말이 없고 벡터도 없는 픽스처 — 카드가 지목돼
    #    있어도 개보법은 **오지 않는다**. 카드 좌표 직행이 사라졌다는 증거다.
    issue = Issue(question="증권사가 투자성향 정보를 제휴사에 넘기는 것이 허용되는가",
                  gate="금융투자업 관련 정보인가", card="쟁점/동의와-정보이용")
    norms = rp.build_norms(idx, issue, st)
    assert norms and all(n.doc != "개인정보 보호법" for n in norms)
    # ② 쟁점 문장이 조 제목 낱말("개인정보의 제공")을 품으면 어휘 사다리가 문다 —
    #    개보법은 카드가 아니라 **검색**이 데려온다. (실전에선 벡터가 이 자리를
    #    맡는다 — 쟁점기의 probe 가 조문 문체라 코사인이 문다.)
    st2 = ReviewState(question="q")
    issue2 = Issue(question="증권사의 제휴사에 대한 개인정보의 제공이 허용되는가",
                   gate="금융투자업 관련 정보인가", card="쟁점/동의와-정보이용")
    norms2 = rp.build_norms(idx, issue2, st2)
    assert any(n.doc == "개인정보 보호법" and "제17조" in n.path for n in norms2)
    assert all("삭제" not in n.reqs[0].text for n in norms2)   # 삭제 조문은 빠진다


def test_카드가_있으면_트리거_재발견_없이_그대로_쓴다(tmp_path, monkeypatch):
    w = tmp_path / "wiki"
    (w / "쟁점").mkdir(parents=True)
    (w / "쟁점" / "카드A.md").write_text(
        "# 카드A\n\n> 트리거: 절대안맞는낱말\n> 판단 축: 축A\n"
        "> 조문 후보: 「개인정보 보호법」 제17조\n\n본문.\n", "utf-8")
    (w / "index.md").write_text(
        "# 인덱스\n\n| Article | Summary | Updated |\n|---|---|---|\n"
        "| [카드A](쟁점/카드A.md) | A | 2026-08-14 |\n", "utf-8")
    monkeypatch.setenv("WIKI_STORE", str(tmp_path))
    picks = rp._spot_for(Issue(question="아무 말", card="쟁점/카드A"), "아무 말")
    assert [p["slug"] for p in picks] == ["쟁점/카드A"]      # 트리거 무매칭이어도 선다


def test_쟁점이_없으면_거기서_멈춘다(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    llm = _FakeLLM({"review.facts": {"facts": [
        {"text": "날씨 이야기", "subject": "", "action": "", "object": "",
         "tense": "과거"}]},
        "review.issues": {"issues": []}})
    st = rp.run(llm, Index.from_docs([_doc()]), "오늘 날씨가 좋다")
    assert st.issues == [] and st.subs == [] and st.verdicts == []
    assert st.trail[-1]["note"] == "걸린 쟁점 없음"


# ---------------------------------------------------------------- 원장
def _state_with_binding():
    st = ReviewState(question="q", track="적법성")
    i = Issue(question="망분리 대상인가")
    n = Norm(doc="전자금융감독규정", doc_id="D1", node=15, path="제15조 ▸ ①")
    st.issues, st.norms = [i], [n]
    st.subs = [Sub(issue_id=i.id, norm_id=n.id, req_id="r1",
                   req_text="내부망 분리", judgment="불명")]
    st.verdicts = [rp.conclude(i, st.subs)]
    return st


def test_원장은_자산명이_있을_때만_적재하고_같은_자리는_갱신한다(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_BINDINGS", str(tmp_path / "b.json"))
    st = _state_with_binding()
    assert binding_mod.record(st, "") == 0                  # 자산 없으면 안 남긴다
    assert binding_mod.record(st, "간편결제") == 1
    assert binding_mod.record(st, "간편결제") == 1          # 재검토는 갱신
    assert len(binding_mod.load()) == 1                     # 이력이 아니라 현재 상태
    rows = binding_mod.assets()
    assert rows[0]["asset"] == "간편결제" and rows[0]["불명"] == 1


def test_해당없음은_원장에_남지_않는다(tmp_path, monkeypatch):
    """원장은 '매임'의 기록이다 — 해당 없는 조문은 의존이 아니다 (실측에서 드러남)."""
    monkeypatch.setenv("REVIEW_BINDINGS", str(tmp_path / "b.json"))
    st = _state_with_binding()
    n = st.norms[0]
    st.subs.append(Sub(issue_id=st.issues[0].id, norm_id=n.id, req_id="r9",
                       req_text="제32조 삭제", judgment="해당없음"))
    assert binding_mod.record(st, "간편결제") == 1          # 불명 1건만
    assert all(b["judgment"] != "해당없음" for b in binding_mod.load())


def test_역인덱스가_조문에서_자산을_되짚는다(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_BINDINGS", str(tmp_path / "b.json"))
    binding_mod.record(_state_with_binding(), "간편결제")
    hit = binding_mod.impacted("전자금융감독규정", 15)
    assert [b["asset"] for b in hit] == ["간편결제"]
    assert binding_mod.impacted("전자금융감독규정", 99) == []
    assert binding_mod.impacted("상법") == []


def test_요건이_많아도_포섭_콜은_상한을_지킨다(tmp_path, monkeypatch):
    """실측: 요건 27개에서 출력이 잘려 판정 전체가 버려졌다 — 앞에서 자른다."""
    captured = {}

    def grab(user):
        # 사실 목록도 "- [" 로 시작하므로 요건 목록 뒤만 센다
        captured["n"] = user.split("[요건 목록]")[1].count("- [")
        return {"subs": []}

    llm = _FakeLLM({"review.subsume": grab})
    issue = Issue(question="q")
    norms = [Norm(doc="D", path=f"제{k}조",
                  reqs=[Req(text=f"요건 {k}-{j} 입니다 충분히 길게") for j in range(6)])
             for k in range(8)]                      # 48개 요건
    rp.subsume(llm, issue, norms, [Fact(text="f")])
    assert captured["n"] <= rp.SUB_REQ_CAP


def test_LLM이_빈손이면_카드_트리거가_쟁점을_받는다(tmp_path, monkeypatch):
    """쟁점 도출이 무너지면 검토가 통째로 없어진다 — 결정론 안전망 (실측: 4→4→0)."""
    _wiki(tmp_path, monkeypatch)                     # 트리거: 제공 · 목적 외 · 개인정보
    facts = [Fact(text="증권사가 고객 개인정보를 제휴사에 제공한다",
                  subject="증권사", action="제공", object="개인정보", tense="계획")]
    llm = _FakeLLM({"review.issues": {"issues": []}})
    got = rp.spot_issues(llm, facts)
    assert got and got[0].card == "쟁점/목적외-제공"   # 카드가 사실에 반응했다
    assert got[0].axis.startswith("다른 법률")
    # 콜 자체가 죽어도(None) 같은 안전망이 선다
    assert rp.spot_issues(_FakeLLM({"review.issues": None}), facts)


def test_안전망도_무관한_사실에는_서지_않는다(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    facts = [Fact(text="오늘 날씨가 좋다", subject="", action="", object="")]
    assert rp.spot_issues(_FakeLLM({"review.issues": {"issues": []}}), facts) == []


# ---------------------------------------------------------------- 요건 단위
def _hierarchy_doc():
    """조 → 항 → 호 — 실제 법령의 계층 (개보법 제18조 축소판)."""
    return ("D1", {"name": "시험법"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제18조",
         "title": "목적 외 제공", "page": 1, "span": [0, 5]},
        {"id": 2, "parent": 1, "level": 2, "surface": "①", "span": [0, 1]},
        {"id": 3, "parent": 1, "level": 2, "surface": "②", "span": [1, 5]},
        {"id": 4, "parent": 3, "level": 3, "surface": "1.", "span": [2, 3]},
        {"id": 5, "parent": 3, "level": 3, "surface": "2.", "span": [3, 4]},
        {"id": 6, "parent": 3, "level": 3, "surface": "3.", "span": [4, 5]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text", "text": "① 목적 외로 제공해서는 아니 된다."},
        {"idx": 1, "page": 1, "kind": "text",
         "text": "② 제1항에도 불구하고 다음 각 호의 어느 하나에 해당하는 경우에는 제공할 수 있다."},
        {"idx": 2, "page": 1, "kind": "text", "text": "1. 정보주체로부터 별도의 동의를 받은 경우"},
        {"idx": 3, "page": 1, "kind": "text", "text": "2. 다른 법률에 특별한 규정이 있는 경우"},
        {"idx": 4, "page": 1, "kind": "text", "text": "3. 급박한 생명의 이익을 위하여 필요한 경우"},
    ]})


def test_요건은_마디에서_나오고_호가_잎이_된다():
    idx = Index.from_docs([_hierarchy_doc()])
    v = idx.docs["D1"]
    reqs = rp._reqs_from_nodes(v, "D1", 1)
    assert [r.node for r in reqs] == [2, 3]                   # 항 둘
    assert not reqs[0].children                               # ①은 호가 없어 잎
    assert [c.node for c in reqs[1].children] == [4, 5, 6]    # ②의 호 셋이 잎
    leaves = req_leaves(reqs)
    assert [r.node for r in leaves] == [2, 4, 5, 6]           # 판정 단위 = 항·호
    assert "동의를 받은 경우" in leaves[1].text


def test_항의_줄기는_호를_삼키지_않는다():
    """'각 호 외의 부분'만 항의 몫이다 — 안 빼면 요건이 통째로 중복된다."""
    idx = Index.from_docs([_hierarchy_doc()])
    v = idx.docs["D1"]
    stem = rp._reqs_from_nodes(v, "D1", 1)[1].text
    assert "각 호의 어느 하나" in stem
    assert "별도의 동의" not in stem                          # 호 본문은 안 들어온다


def test_요건_id는_좌표에서_나와_실행마다_같다():
    idx = Index.from_docs([_hierarchy_doc()])
    v = idx.docs["D1"]
    a = [r.id for r in req_leaves(rp._reqs_from_nodes(v, "D1", 1))]
    b = [r.id for r in req_leaves(rp._reqs_from_nodes(v, "D1", 1))]
    assert a == b and a[0] == "rD1-2"        # 재검토해도 같은 요건은 같은 id


def test_삭제된_호도_요건에서_빠진다():
    """실측: 개보법 제18조제2항 제4호가 "삭제<2020.2.4>" 인데 잎으로 남았다."""
    assert rp._is_deleted("4. 삭제<2020.2.4>")
    assert rp._is_deleted("② 삭제 <2011.3.29>")
    assert not rp._is_deleted("4. 삭제된 정보를 복구한 경우")


# ---------------------------------------------------------------- 논리 표지
def _or_doc():
    """"각 호의 어느 하나" — 호가 선택지인 조문 (개보법 제18조제2항 꼴)."""
    return ("D2", {"name": "시험법"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제9조", "span": [0, 4]},
        {"id": 2, "parent": 1, "level": 2, "surface": "①", "span": [0, 4]},
        {"id": 3, "parent": 2, "level": 3, "surface": "1.", "span": [1, 2]},
        {"id": 4, "parent": 2, "level": 3, "surface": "2.", "span": [2, 3]},
        {"id": 5, "parent": 2, "level": 3, "surface": "3.", "span": [3, 4]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text",
         "text": "① 다음 각 호의 어느 하나에 해당하는 경우에는 제공할 수 있다. "
                 "다만, 공공기관의 경우로 한정한다."},
        {"idx": 1, "page": 1, "kind": "text", "text": "1. 동의를 받은 경우"},
        {"idx": 2, "page": 1, "kind": "text", "text": "2. 다른 법률에 규정이 있는 경우"},
        {"idx": 3, "page": 1, "kind": "text", "text": "3. 급박한 경우"},
    ]})


def test_어느_하나는_OR로_읽힌다():
    idx = Index.from_docs([_or_doc()])
    reqs = rp._reqs_from_nodes(idx.docs["D2"], "D2", 1)
    assert reqs[0].op == "OR" and len(reqs[0].children) == 3


def test_모두_갖춘은_AND로_읽히고_표지가_없으면_비운다():
    assert rp._mark_logic(Req(text="다음 각 호를 모두 갖춘 경우",
                              children=[Req(text="a")])).op == "AND"
    assert rp._mark_logic(Req(text="다음 각 호의 사항을 알려야 한다",
                              children=[Req(text="a")])).op == "AND"
    # 관계를 모르면 비워 둔다 — 추정으로 채우지 않는다
    assert rp._mark_logic(Req(text="다음과 같다", children=[Req(text="a")])).op is None


def test_단서는_별도_요건으로_떨어진다():
    out = rp._split_proviso(Req(text="본문은 이러하다. 다만, 예외는 저러하다.",
                                id="r1", node=3))
    assert len(out) == 2
    assert out[0].text == "본문은 이러하다." and not out[0].proviso
    assert out[1].proviso and out[1].text.startswith("예외는")
    assert out[1].id == "r1-단서"


def test_OR는_하나만_충족되면_접힌다():
    """핵심 이득 — 10개 호 중 하나가 충족되면 형제 아홉의 불명은 묻지 않는다."""
    tree = Req(text="어느 하나", op="OR", id="b",
               children=[Req(text="1", id="c1"), Req(text="2", id="c2"),
                         Req(text="3", id="c3")])
    assert rp.fold(tree, {"c1": "충족", "c2": "불명", "c3": "불명"}) == "충족"
    assert rp.fold(tree, {"c1": "불충족", "c2": "불충족", "c3": "불충족"}) == "불충족"
    assert rp.fold(tree, {"c1": "불명", "c2": "불충족", "c3": "불명"}) == "불명"


def test_AND와_미상은_다르게_접힌다():
    kids = [Req(text="1", id="c1"), Req(text="2", id="c2")]
    a = Req(text="모두", op="AND", id="a", children=kids)
    u = Req(text="미상", id="u", children=kids)
    assert rp.fold(a, {"c1": "충족", "c2": "불충족"}) == "불충족"
    assert rp.fold(a, {"c1": "충족", "c2": "충족"}) == "충족"
    # 미상은 관계를 모르므로 불충족으로 단정하지 않는다
    assert rp.fold(u, {"c1": "충족", "c2": "불충족"}) == "불명"
    assert rp.fold(u, {"c1": "충족", "c2": "충족"}) == "충족"


def test_결론이_트리를_알면_OR_형제의_불명에_흔들리지_않는다():
    i = Issue(question="q")
    tree = Req(text="어느 하나", op="OR", id="b",
               children=[Req(text="1", id="c1"), Req(text="2", id="c2")])
    n = Norm(doc="D", path="제9조", reqs=[tree])
    subs = [Sub(issue_id=i.id, norm_id=n.id, req_id="c1", judgment="충족"),
            Sub(issue_id=i.id, norm_id=n.id, req_id="c2", judgment="불명")]
    assert rp.conclude(i, subs).conclusion == "조건부"          # 평평하게 보면 불명이 남고
    assert rp.conclude(i, subs, [n]).conclusion == "가능"       # 트리를 알면 접힌다


def test_표지가_둘이면_먼저_나온_것이_이긴다():
    """실측 오독: 개보법 제18조제3항이 AND 인데 뒤 문장의 '어느 하나'로 OR 이 됐다."""
    r = rp._mark_logic(Req(
        text="다음 각 호의 사항을 정보주체에게 알려야 한다. "
             "다음 각 호의 어느 하나의 사항을 변경하는 경우에도 알려야 한다.",
        children=[Req(text="a")]))
    assert r.op == "AND"
    r2 = rp._mark_logic(Req(
        text="다음 각 호의 어느 하나에 해당하면 다음 각 호의 사항을 알려야 한다.",
        children=[Req(text="a")]))
    assert r2.op == "OR"


def test_판정_안_된_요건은_미해결로_세지_않는다():
    """상한에 잘려 포섭에 못 올라간 요건을 '다툼의 자리'로 세면 신호가 묻힌다."""
    i = Issue(question="q")
    judged = Req(text="본 요건", id="j1")
    never = Req(text="상한에 잘린 요건", id="x1")
    n = Norm(doc="D", path="제1조", reqs=[judged, never])
    subs = [Sub(issue_id=i.id, norm_id=n.id, req_id="j1", judgment="충족")]
    v = rp.conclude(i, subs, [n])
    assert v.conclusion == "가능" and v.unmet == []


# ---------------------------------------------------------------- 안전망 조이기
def test_약한_트리거_매칭으로는_안전망이_서지_않는다(tmp_path, monkeypatch):
    """골든 25-0653: '열람 경로' 사안에 트리거 하나가 물어 남의 쟁점이 섰다.
    틀린 쟁점은 빈손보다 나쁘다 — 빈손은 눈에 띄고 틀린 쟁점은 원인을 숨긴다."""
    _wiki(tmp_path, monkeypatch)              # 트리거: 제공 · 목적 외 · 개인정보
    weak = [Fact(text="정보주체가 열람을 요구한다", subject="정보주체",
                 action="열람 요구", object="개인정보")]      # '개인정보' 하나만 물린다
    assert rp.spot_issues(_FakeLLM({"review.issues": {"issues": []}}), weak) == []
    strong = [Fact(text="개인정보를 제3자에게 제공한다", subject="A",
                   action="제공", object="개인정보")]          # 제공 + 개인정보 = 2
    got = rp.spot_issues(_FakeLLM({"review.issues": {"issues": []}}), strong)
    assert got and got[0].by_net is True      # 안전망이 세운 쟁점은 표시가 남는다


def test_쟁점이_빈손이면_안전망보다_재시도가_먼저다(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    facts = [Fact(text="개인정보를 제공한다", subject="A", action="제공",
                  object="개인정보")]
    seq = {"n": 0}

    def twice(user):
        seq["n"] += 1
        if seq["n"] == 1:
            return {"issues": []}                              # 첫 콜 빈손
        assert "[재시도]" in user
        return {"issues": [{"question": "제공이 허용되는가?", "gate": "개인정보",
                            "card": "쟁점/목적외-제공", "regulation": "수평"}]}

    got = rp.spot_issues(_FakeLLM({"review.issues": twice}), facts)
    assert seq["n"] == 2                                       # 재시도했다
    assert got[0].question == "제공이 허용되는가?" and not got[0].by_net


# ------------------------------------- 회수 배선 (2026-08-16 골든 67건 실측 후)

def _law_and_decree():
    """법 + 시행령 — 법 제35조가 시행령 제41조로 위임하는 모양."""
    law = ("L2", {"name": "개인정보 보호법"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제35조",
         "title": "개인정보의 열람", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text",
         "text": "제35조(개인정보의 열람) 정보주체는 열람을 요구할 수 있다. "
                 "열람의 절차는 대통령령으로 정한다."},
    ]})
    dec = ("D2", {"name": "개인정보 보호법 시행령"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제41조",
         "title": "개인정보의 열람절차 등", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "kind": "text",
         "text": "제41조(개인정보의 열람절차 등) 열람 요구 방법과 절차를 "
                 "마련하여야 한다."},
    ]})
    return law, dec


def test_입력_문면_인용을_좌표로_직행_회수한다(tmp_path, monkeypatch):
    """질의요지가 "같은 법 시행령 제41조"라 써 놨으면 검색 없이 그 조를 편다
    — 골든 26-0271 실패의 교정. 실측: 인용 직행만으로 근거 조문 91% 회수."""
    _wiki(tmp_path, monkeypatch)
    idx = Index.from_docs(list(_law_and_decree()))
    st = ReviewState(question="「개인정보 보호법」 제35조제1항에서는 열람을 "
                              "규정하고, 같은 법 시행령 제41조제2항에서는 "
                              "절차를 규정하는바, 어떠한가?")
    issue = Issue(question="열람 방법의 범위는?", gate="")
    norms = rp.build_norms(idx, issue, st)
    docs = {n.doc for n in norms}
    paths = " ".join(n.path for n in norms)
    assert "개인정보 보호법" in docs and "개인정보 보호법 시행령" in docs
    assert "제35조" in paths and "제41조" in paths


def test_대용어는_낫표_인용이_없으면_풀지_않는다(tmp_path, monkeypatch):
    """"같은 법"의 선행 인용이 없으면 발명하지 않는다."""
    idx = Index.from_docs(list(_law_and_decree()))
    assert rp._cite_coords(idx, "같은 법 시행령 제41조는 어떠한가?") == []


def test_해석_판정이_사안_방향을_세우고_불충족은_프롬프트에_실린다(tmp_path, monkeypatch):
    """해석 트랙: overall 이 서고, 포섭의 불충족이 판정 입력에 보인다."""
    _wiki(tmp_path, monkeypatch)
    idx = Index.from_docs([_doc()])
    seen = {}

    def interp(user):
        seen["user"] = user
        return {"direction": "긍정", "reason": "문언상 가능하다",
                "basis": ["개인정보 보호법 ▸ 제18조"]}

    llm = _FakeLLM({
        "review.facts": {"facts": [{"text": "개인정보를 제공한다", "subject": "처리자",
                                    "action": "제공", "object": "개인정보",
                                    "tense": "계획"}]},
        "review.issues": {"issues": [{"question": "목적 외 제공이 가능한가?",
                                      "gate": "제공인가", "card": "쟁점/목적외-제공",
                                      "regulation": ""}]},
        "review.subsume": lambda u: {"subs": [
            {"req_id": u[u.index("[rL1-"):u.index("]", u.index("[rL1-"))][1:],
             "judgment": "불충족", "facts": [], "reason": "근거 없음"}]},
        "review.interpret": interp,
    })
    st = rp.run(llm, idx, "개인정보를 목적 외로 제공하려 한다", track="해석")
    assert st.overall and st.overall["direction"] == "긍정"
    assert "포섭 관측 — 불충족 요건" in seen["user"]     # 관측이 판정 입력에 실린다 (규율 ⑤)
    assert any(s["stage"] == "해석 판정" for s in st.trail)


def test_적법성_트랙은_해석_판정을_얹지_않는다(tmp_path, monkeypatch):
    """B트랙은 요건 충족표가 답이다 — overall 없음."""
    _wiki(tmp_path, monkeypatch)
    idx = Index.from_docs([_doc()])
    llm = _FakeLLM({
        "review.facts": {"facts": []},
        "review.issues": {"issues": [{"question": "가능한가?", "gate": "",
                                      "card": "", "regulation": ""}]},
        "review.subsume": {"subs": []},
    })
    st = rp.run(llm, idx, "서비스 설계 검토", track="적법성")
    assert st.overall is None


# ------------------------------------------- 판정 표결 (2026-08-16 2차)

def _interp_llm(directions, extra=None):
    """interpret 호출마다 directions 를 차례로 내는 대역."""
    it = iter(directions)
    # 쟁점 문장이 법을 말한다 — 검색 질의는 쟁점 문장(+probe)뿐이고 카드 조문 후보
    # 텍스트는 더 이상 질의에 실리지 않는다(build_norms ④ · 2026-08-17). 쟁점이
    # 법을 말하지 않으면 벡터가 찾을 몫인데 이 가짜 색인에는 벡터가 없다.
    by = {
        "review.facts": {"facts": []},
        "review.issues": {"issues": [{"question": "개인정보 보호법상 목적 외 제공이 가능한가?",
                                      "gate": "", "card": "쟁점/목적외-제공",
                                      "regulation": ""}]},
        "review.subsume": {"subs": []},
        "review.interpret": lambda u: {"direction": next(it),
                                       "reason": "r", "basis": []},
    }
    by.update(extra or {})
    return _FakeLLM(by)


def test_판정은_기본_단일콜이고_k를_올리면_다수결이다(tmp_path, monkeypatch):
    """기본 k=1 — 안정 모델 단일 콜(2026-08-16 실측: 흔들리는 모델을 세 번 묻는
    것보다 안 흔들리는 모델을 한 번). k 는 실험용으로 남아 있고, 올리면 다수결·
    과반 없으면 조건부(아는 척하지 않는다)."""
    _wiki(tmp_path, monkeypatch)
    idx = Index.from_docs([_doc()])
    st = rp.run(_interp_llm(["부정"]), idx, "제공 검토", track="해석")
    assert st.overall["direction"] == "부정" and st.overall["votes"] == ["부정"]
    monkeypatch.setattr(rp, "_INTERP_K", 3)
    st = rp.run(_interp_llm(["긍정", "긍정", "부정"]), idx, "제공 검토", track="해석")
    assert st.overall["direction"] == "긍정" and st.overall["votes"] == ["긍정", "긍정", "부정"]
    st = rp.run(_interp_llm(["긍정", "부정", "조건부"]), idx, "제공 검토", track="해석")
    assert st.overall["direction"] == "조건부"      # 과반 없음 — 아는 척하지 않는다


def test_판정_콜에_카드_판단_기준이_배경으로_실린다(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    idx = Index.from_docs([_doc()])
    seen = []
    llm = _interp_llm(["긍정"] * 3)
    orig = llm.by_kind["review.interpret"]
    llm.by_kind["review.interpret"] = lambda u: (seen.append(u), orig(u))[1]
    rp.run(llm, idx, "개인정보를 목적 외로 제공하려 한다", track="해석")
    assert seen and "[해석 맥락 — 지식 위키]" in seen[0]
