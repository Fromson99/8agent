"""구조화 결과 → 증분 비교 · 자동 반영 · 되돌리기 계약."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lawrag.increment.db import SqliteDatabase
from lawrag.increment.diff import BaseArticle, diff_snapshot
from lawrag.increment.lawgo_parse import parse_lawgo_xml
from lawrag.increment.normalize import text_hash
from lawrag.increment.service import ChannelSwitch, IncrementError, IncrementService
from lawrag.increment.structured import (Header, annex_fingerprint, annex_text, from_result,
                                         from_structure, header_from_name, header_from_xml, name_code)

from test_law_increment import ART, law_xml, v1_xml, v2_xml

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "01_DATA/PACKAGES/EXTERNAL/ontology-operational-8def52ccda54d7b0/gen-8def52ccda54d7b01cce8a4a/ARTIFACTS/STRUCTURE"


# ------------------------------------------------------------------ 합성 구조화 결과

class Tree:
    """구조화 result.json의 nodes·blocks를 문서 순서대로 만든다 (span은 마디가 덮는 블록 범위)."""

    def __init__(self):
        self.nodes, self.blocks, self._open = [], [], []

    def block(self, text, node):
        self.blocks.append({"idx": len(self.blocks), "text": text, "kind": "text", "node": node})

    def node(self, family, surface, *, title="", parent=None, level=0, scope=None, lines=()):
        nid = len(self.nodes)
        start = len(self.blocks)
        node = {"id": nid, "parent": parent, "level": level, "family": family, "surface": surface,
                "title": title, "block": start, "span": [start, start]}
        if scope:
            node["coordinate_scope"] = scope
        self.nodes.append(node)
        for line in lines:
            self.block(line, nid)
        node["span"][1] = len(self.blocks)
        return nid

    def close(self, nid):
        self.nodes[nid]["span"][1] = len(self.blocks)


def law_tree(*, art3="제3조(설립) 회사는 정관을 작성하여 설립한다.", annex_lines=("| 구분 | 금액 1만원 |", "|---|---|"),
             division="제1장 총칙"):
    t = Tree()
    chapter = t.node("kr_장", division.split()[0], title=division, lines=[division])
    t.node("kr_article", "제1조", title="목적", parent=chapter, level=1, lines=[ART[1]])
    t.node("kr_article", "제2조", title="정의", parent=chapter, level=1, lines=[ART[2]])
    t.close(chapter)
    second = t.node("kr_장", "제1장의2", title="제1장의2 특례", lines=["제1장의2 특례 <신설 2025.1.1>"])
    t.node("kr_article", "제3조", title="설립", parent=second, level=1, lines=[art3, "① 정관은 서면으로 한다."])
    t.block("제4조 삭제 <2025. 2. 5.>", second)                    # 장 마디에 붙은 삭제 줄
    t.close(second)
    buchik = t.node("buchik", "부칙", title="부칙", lines=["부칙"])
    unit = t.node("kr_article", "부칙", title="부칙 <제100호, 20250101>", parent=buchik, level=1,
                  lines=["부칙 <제100호, 20250101>", "부칙 <제100호,2025.1.1>", "이 법은 공포한 날부터 시행한다."])
    t.close(unit)
    t.close(buchik)
    annex = t.node("annex", "별표", title="별표·서식", lines=["별표·서식"])
    t.node("kr_article", "별표 1", title="수수료", parent=annex, level=1, scope="annex",
           lines=["[별표 1] 수수료", *annex_lines])
    t.node("kr_article", "제5조의2", title="", parent=annex, level=2, lines=["제5조의2 표 안의 인용"])
    t.close(annex)
    return t


HEADER = Header("LAW:999001", "LAW", "999001", "시험법", "20250101", "100", "20250101", "일부개정", "a" * 64)


def test_structured_tree_to_snapshot():
    s = from_structure(law_tree().nodes, law_tree().blocks, HEADER)
    keys = [a.key for a in s.articles]
    assert keys == ["1", "2", "3", "4", "별표1", "부칙:100"]           # 별표 안 `제5조의2`는 키가 아니다
    by = {a.key: a for a in s.articles}
    assert "특례" not in by["2"].text                                # 가지번호 장 제목은 앞 조문에 붙지 않는다
    assert by["3"].text.endswith("정관은 서면으로 한다.") and by["3"].title == "설립"   # ①은 NFKC로 1 (XML 경로와 같음)
    assert by["4"].deleted and by["4"].kind == "ARTICLE"
    assert by["부칙:100"].text.splitlines()[0] == "부칙 <제100호,2025.1.1>"   # 합성 제목 줄 제외
    assert by["별표1"].text.splitlines()[0] == "수수료"
    assert by["별표1"].attachment_sha256.startswith("content:")
    assert s.addenda[0].number == "100" and s.addenda[0].promulgated == "20250101"


def _base(snapshot):
    return [BaseArticle(a.key, a.kind, a.title, a.text, "L" + a.key, "b" + a.key, snapshot.effective, a.seq,
                        a.attachment_sha256) for a in snapshot.articles if not a.deleted]


def _changes(old, new):
    result = diff_snapshot(_base(old), new.articles, doc_cd="d", version_id="v")
    return [(c.change_type, c.new.key if c.new else c.old.key) for c in result.changes if c.change_type != "SAME"]


def test_annex_table_layout_is_not_a_change_but_content_is():
    box = law_tree(annex_lines=("┌──┬──────┐", "│구분│금액 1만│", "│  │원    │", "└──┴──────┘"))
    md = law_tree(annex_lines=("| 구분 | 금액 1만원 |", "|---|---|"))
    changed = law_tree(annex_lines=("| 구분 | 금액 2만원 |", "|---|---|"))
    a, b, c = (from_structure(t.nodes, t.blocks, HEADER) for t in (box, md, changed))
    assert _changes(a, b) == []
    assert _changes(b, c) == [("AMEND", "별표1")]
    assert annex_text(["| a<br>b |", "|---|"]) == "a b"
    assert annex_fingerprint("가?나") == annex_fingerprint("가▪나")      # 기호 변환 차이는 같은 내용


def test_body_change_found_through_structure():
    old = from_structure(law_tree().nodes, law_tree().blocks, HEADER)
    t = law_tree(art3="제3조(설립) 회사는 정관을 작성하고 공증을 받아 설립한다.")
    new = from_structure(t.nodes, t.blocks, HEADER)
    assert _changes(old, new) == [("AMEND", "3")]


def test_xml_division_with_branch_number_is_not_article_text():
    raw = law_xml(["제1장 총칙", (1, None, "목적", ART[1]), "제1장의2 특례 <신설 2025.1.1>", (2, None, "정의", ART[2])])
    by = {a.key: a for a in parse_lawgo_xml(raw).articles}
    assert "특례" not in by["1"].text


def test_internal_document_header():
    header = header_from_name("내부통제 기준", filename="내부통제기준_20260101.docx", source_sha256="b" * 64)
    assert header.doc_cd == name_code("내부통제기준") and header.doc_cd.startswith("INTERNAL:")
    assert header.source_kind == "INTERNAL" and header.effective == "20260101"
    t = law_tree()
    s = from_structure(t.nodes, t.blocks, header)
    assert s.promulgation_no == "100" and s.promulgated == "20250101"    # 마지막 부칙에서
    assert header_from_name("규정", filename="규정.docx", source_sha256="c" * 64).effective == ""


def test_real_governance_act_structured_equals_xml():
    folder = REAL / "c4b33879c7dc5554"
    if not (folder / "result.json").is_file():
        pytest.skip("실제 구조화 결과 없음")
    raw = (folder / "source.xml").read_bytes()
    xml_snap = parse_lawgo_xml(raw)
    st_snap = from_result(json.loads((folder / "result.json").read_text(encoding="utf-8")), header_from_xml(raw))
    body = lambda s: {a.key: (a.deleted, text_hash(a.text)) for a in s.articles if a.kind != "ANNEX"}
    assert body(xml_snap) == body(st_snap)
    assert {a.key for a in xml_snap.articles} == {a.key for a in st_snap.articles}


# ------------------------------------------------------------------ 자동 반영·되돌리기

@pytest.fixture
def service():
    svc = IncrementService(SqliteDatabase(), today="20250801")
    svc.create_schema()
    return svc


def auto_to_active(svc, raw, **kw):
    result = svc.ingest(parse_lawgo_xml(raw), source_name="t.xml")
    decision = svc.auto_apply(result.load_id)
    assert decision["decision"] == "APPROVED", decision
    svc.prepare_index(result.load_id, external=())
    svc.activate(result.load_id, user="AUTO", **kw)
    return result


def test_auto_apply_approves_normal_and_holds_suspicious(service):
    first = auto_to_active(service, v1_xml())
    assert service.job(first.load_id)["APRV_USER_ID"] == "AUTO"
    truncated = law_xml([(1, None, "a", ART[1])], prom="20250701", no="200", eff="20250701")
    held = service.ingest(parse_lawgo_xml(truncated))
    decision = service.auto_apply(held.load_id)
    assert decision["decision"] == "HOLD" and decision["state"] == "PREVIEW"
    assert any(r.startswith("ARTICLE_COUNT_DROP") or r.startswith("MANY_DELETES") for r in decision["reasons"])
    assert service.job(held.load_id)["PRCS_STTS_CD"] == "PREVIEW"
    hist = service.db.query("SELECT HIST_CTNT FROM IDD_B003_LGL_LOAD_HIST WHERE LOAD_WORK_ID=:id "
                            "ORDER BY HIST_SEQ DESC", {"id": held.load_id})[0]["HIST_CTNT"]
    assert "hold" in hist
    assert service.auto_apply(held.load_id, hold_on_strong=False)["decision"] == "APPROVED"
    blocked = service.ingest(parse_lawgo_xml(law_xml([(1, None, "a", ART[1] + " 변경")], prom="20240101",
                                                     no="50", eff="20240101")))
    assert blocked.state == "BLOCKED"
    assert service.auto_apply(blocked.load_id)["decision"] == "HOLD"


def test_rollback_restores_previous_version(service):
    with service.db.transaction() as tx:
        tx.execute("CREATE TABLE IDD_B003_LGL_SRCH_CHNL (RFRN_CHNL_NAME TEXT, RFRN_POST_HASH_VALU TEXT, CHAN_NO INTEGER)")
        tx.execute("INSERT INTO IDD_B003_LGL_SRCH_CHNL VALUES ('main', 'g1', 1)")
    first = auto_to_active(service, v1_xml())
    before = [(a.key, a.text) for a in service.current_articles("LAW:999001")]
    second = auto_to_active(service, v2_xml(), channel=ChannelSwitch("IDD_B003_LGL_SRCH_CHNL", "main", "g1", "g2", 1))
    assert [(a.key, a.text) for a in service.current_articles("LAW:999001")] != before
    with pytest.raises(IncrementError, match="최신 판본부터"):
        service.rollback(first.load_id, user="u", reason="x")
    out = service.rollback(second.load_id, user="u", reason="잘린 파일",
                           channel=ChannelSwitch("IDD_B003_LGL_SRCH_CHNL", "main", "g2", "g1", 2))
    assert out["state"] == "ROLLED_BACK" and out["hidden_rows"] == 5
    assert [(a.key, a.text) for a in service.current_articles("LAW:999001")] == before
    assert {r["ARTC_KEY_VALU"] for r in service.articles_as_of("LAW:999001", "20260102")} == {k for k, _ in before}
    assert service.document("LAW:999001")["ACTV_VER_ID"] == service.job(first.load_id)["NEW_VER_ID"]
    assert service.db.query("SELECT RFRN_POST_HASH_VALU AS P FROM IDD_B003_LGL_SRCH_CHNL")[0]["P"] == "g1"
    assert not service.db.query("SELECT 1 FROM IDD_B003_LGL_RVW_TRGT WHERE LOAD_WORK_ID=:id AND RVW_STTS_CD='OPEN'",
                                {"id": second.load_id})
    with pytest.raises(IncrementError):
        service.rollback(second.load_id, user="u", reason="again")
    assert service.ingest(parse_lawgo_xml(v2_xml())).reused             # 같은 파일은 같은 작업


# ------------------------------------------------------------------ 떨어진 폴더 → 비교 → 조립 → 활성화

def _real_pair():
    old, new = REAL / "1ab2b728e6280db5", REAL / "c4b33879c7dc5554"         # 지배구조법 제19913호 → 제21065호
    if not (old / "result.json").is_file() or not (new / "result.json").is_file():
        pytest.skip("실제 구조화 결과 없음")
    return [(p / "source.xml").read_bytes() for p in (old, new)], \
           [json.loads((p / "result.json").read_text(encoding="utf-8")) for p in (old, new)]


def test_daily_cycle_structured_auto_assemble_activate(service, tmp_path):
    import hashlib
    import zipfile
    from lawrag.core.legal_generation import build_contract
    from lawrag.increment.corpus import assemble
    from lawrag.increment.daily import Incoming, decide, finish, replacements

    (gov_old, gov_new), (gov_old_r, gov_new_r) = _real_pair()
    test_v1 = law_xml([(1, None, "목적", ART[1])])
    test_cut = law_xml([(1, None, "목적", ART[1])], prom="20250701", no="200", eff="20250701")
    rule_v1, rule_v2 = b"PK-docx-v1", b"PK-docx-v2"
    with service.db.transaction() as tx:
        tx.execute("CREATE TABLE IDD_B003_LGL_SRCH_CHNL (RFRN_CHNL_NAME TEXT, RFRN_POST_HASH_VALU TEXT, CHAN_NO INTEGER)")
        tx.execute("INSERT INTO IDD_B003_LGL_SRCH_CHNL VALUES ('main', 'g0', 1)")

    def item(name, law_id, data):
        return {"kind": "law", "status": "ok", "name": name, "law_id": law_id, "authority_as_of": "20250101",
                "body_file": f"{name}/{name} 본문.xml", "body_sha256": hashlib.sha256(data).hexdigest(),
                "attachments": [{"title": "[별표] 옛 별표", "role": "attachment", "file": f"{name}/별표서식/옛.hwp",
                                 "sha256": "0" * 64}]}
    manifest = {"authority_as_of": "20250101",
                "items": [item("금융회사의 지배구조에 관한 법률", "012338", gov_old), item("시험법", "999001", test_v1)]}
    base = tmp_path / "base.zip"
    with zipfile.ZipFile(base, "w") as z:
        z.writestr("law/manifest.json", json.dumps(manifest, ensure_ascii=False))
        z.writestr("law/금융회사의 지배구조에 관한 법률/금융회사의 지배구조에 관한 법률 본문.xml", gov_old)
        z.writestr("law/금융회사의 지배구조에 관한 법률/별표서식/옛.hwp", b"hwp")
        z.writestr("law/시험법/시험법 본문.xml", test_v1)
        z.writestr("law/시험법/별표서식/옛.hwp", b"hwp")
        z.writestr("internal/risk_team/내부통제기준_20250101.docx", rule_v1)

    tree = law_tree()
    first = decide(service, [Incoming("gov.xml", gov_old, gov_old_r), Incoming("test.xml", test_v1, {"nodes": tree.nodes, "blocks": tree.blocks}),
                             Incoming("내부통제기준_20250101.docx", rule_v1, {"nodes": tree.nodes, "blocks": tree.blocks})])
    assert first["summary"] == {"APPROVED": 3}                              # 기준선: 처음 적재는 전부 신설
    done = finish(service, first, dtls_hash="g1",
                  channel=ChannelSwitch("IDD_B003_LGL_SRCH_CHNL", "main", "g0", "g1", 1))
    assert done["state"] == "ACTIVATED" and len(done["activated"]["results"]) == 3

    cut = Tree()
    ch = cut.node("kr_장", "제1장", title="제1장 총칙", lines=["제1장 총칙"])
    cut.node("kr_article", "제1조", title="목적", parent=ch, level=1, lines=[ART[1]])
    cut.close(ch)
    changed = law_tree(art3="제3조(설립) 회사는 정관을 작성하고 공증을 받아 설립한다.")
    drop = [Incoming("gov21065.xml", gov_new, gov_new_r),
            Incoming("test-cut.xml", test_cut, {"nodes": cut.nodes, "blocks": cut.blocks}),
            Incoming("내부통제기준_20250701.docx", rule_v2, {"nodes": changed.nodes, "blocks": changed.blocks})]
    report = decide(service, drop)
    by = {e["file"]: e for e in report["entries"]}
    assert by["gov21065.xml"]["decision"] == "APPROVED"
    assert by["내부통제기준_20250701.docx"]["decision"] == "APPROVED"
    assert by["test-cut.xml"]["decision"] == "HOLD" and by["test-cut.xml"]["reasons"]
    assert "<html" in by["gov21065.xml"]["preview_html"].lower()

    out = tmp_path / "new.zip"
    assembly = assemble(base, out, replacements(report, drop), as_of="20260102")
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        new_manifest = json.loads(z.read("law/manifest.json"))
        assert hashlib.sha256(z.read("law/금융회사의 지배구조에 관한 법률/금융회사의 지배구조에 관한 법률 본문.xml")).hexdigest() \
            == hashlib.sha256(gov_new).hexdigest()
        assert z.read("law/시험법/시험법 본문.xml") == test_v1                    # 보류 문서는 지난 파일 그대로
    assert "internal/risk_team/내부통제기준_20250701.docx" in names
    assert "internal/risk_team/내부통제기준_20250101.docx" not in names
    assert "law/금융회사의 지배구조에 관한 법률/별표서식/옛.hwp" not in names and "law/시험법/별표서식/옛.hwp" in names
    gov_item = next(i for i in new_manifest["items"] if i["law_id"] == "012338")
    assert gov_item["promul_no"] == "21065" and gov_item["enforce"] == "20260102"
    assert new_manifest["generation_id"] == build_contract(new_manifest, as_of="20260102")["generation_id"]
    assert len(assembly.replaced) == 2 and assembly.warnings                # 옛 별표 파일 제외 경고
    again = assemble(base, tmp_path / "again.zip", replacements(report, drop), as_of="20260102")
    assert again.out_sha256 == assembly.out_sha256                          # 같은 입력이면 같은 ZIP

    done = finish(service, report, dtls_hash="g2",
                  channel=ChannelSwitch("IDD_B003_LGL_SRCH_CHNL", "main", "g1", "g2", 2))
    assert done["state"] == "ACTIVATED" and len(done["activated"]["results"]) == 2
    a26 = {r["ARTC_KEY_VALU"]: r for r in service.articles_as_of("LAW:012338", "20260102")}["26"]
    assert "재정경제부" in a26["ARTC_CTNT"]
    rule = {r["ARTC_KEY_VALU"]: r for r in service.articles_as_of(
        by["내부통제기준_20250701.docx"]["doc_cd"], "20250801")}["3"]
    assert "공증" in rule["ARTC_CTNT"]
    assert len(service.articles_as_of("LAW:999001", "20250801")) > 1          # 보류 문서는 지난 판본 유지
    assert service.db.query("SELECT RFRN_POST_HASH_VALU AS P, CHAN_NO AS N FROM IDD_B003_LGL_SRCH_CHNL")[0] == {"P": "g2", "N": 3}
    assert decide(service, drop[:1])["entries"][0]["decision"] == "ALREADY"   # 같은 파일 재투입
