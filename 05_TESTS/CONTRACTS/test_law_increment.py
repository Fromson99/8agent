"""법제처 증분 처리 — 파싱·조문 비교·시행일·게이트·상태 전이·활성화 계약."""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from lawrag.increment.addenda import read_schedule, resolve_when, schedule_for
from lawrag.increment.db import DataikuDatabase, SqliteDatabase
from lawrag.increment.diff import BaseArticle, diff_snapshot
from lawrag.increment.gate import assign_effective, evaluate
from lawrag.increment.lawgo_parse import (Article, ParseError, parse_lawgo_xml, snapshot_fingerprint,
                                          split_flat_articles)
from lawrag.increment.schema import PREFIX, TABLES, ddl, new_words
from lawrag.increment.service import ChannelSwitch, IncrementError, IncrementService

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "01_DATA/PACKAGES/EXTERNAL/ontology-operational-8def52ccda54d7b0/gen-8def52ccda54d7b01cce8a4a/ARTIFACTS/STRUCTURE"


# ------------------------------------------------------------------ 합성 XML

def law_xml(articles, *, law_id="999001", name="시험법", prom="20250101", no="100", eff="20250101",
            addenda=(), annexes=(), pad=""):
    units = []
    for item in articles:
        if isinstance(item, str):                         # 장·절 제목
            units.append(f"<조문단위><조문번호>1</조문번호><조문여부>전문</조문여부>"
                         f"<조문내용>{escape(item)}</조문내용></조문단위>")
            continue
        number, branch, title, text = item
        branch_tag = f"<조문가지번호>{branch}</조문가지번호>" if branch else ""
        units.append(f"<조문단위><조문번호>{number}</조문번호>{branch_tag}<조문여부>조문</조문여부>"
                     f"<조문제목>{escape(title)}</조문제목><조문시행일자>{eff}</조문시행일자>"
                     f"<조문내용>{escape(text)}</조문내용></조문단위>")
    adds = "".join(f"<부칙단위><부칙공포일자>{d}</부칙공포일자><부칙공포번호>{n}</부칙공포번호>"
                   f"<부칙내용>{escape(t)}</부칙내용></부칙단위>" for d, n, t in addenda)
    annex = "".join(f"<별표단위><별표번호>{k:04d}</별표번호><별표가지번호>00</별표가지번호><별표구분>별표</별표구분>"
                    f"<별표제목>{escape(t)}</별표제목><별표내용>{escape(c)}</별표내용></별표단위>"
                    for k, t, c in annexes)
    return (f"<?xml version='1.0' encoding='utf-8'?><법령><기본정보><법령ID>{law_id}</법령ID>"
            f"<공포일자>{prom}</공포일자><공포번호>{no}</공포번호><법령명_한글>{name}</법령명_한글>"
            f"<시행일자>{eff}</시행일자><제개정구분>일부개정</제개정구분></기본정보>{pad}"
            f"<조문>{''.join(units)}</조문><부칙>{adds}</부칙><별표>{annex}</별표></법령>").encode("utf-8")


ART = {
    1: "제1조(목적) 이 법은 회사의 설립과 운영에 관한 사항을 정함을 목적으로 한다.",
    2: "제2조(정의) 이 법에서 \"회사\"란 상행위를 목적으로 설립한 법인을 말하며, 제5조의 과태료 대상을 포함한다.",
    3: "제3조(설립) 회사는 정관을 작성하여 설립한다. 제2조에 따른 회사에 한한다.",
    4: "제4조(등기) 회사는 본점 소재지에서 설립등기를 하여야 한다. 제3조에 따라 설립한 경우에 같다.",
    5: "제5조(벌칙) 제4조를 위반한 자는 1천만원 이하의 과태료에 처한다.",
    6: "제6조(보고) 회사는 매년 영업보고서를 금융위원회에 제출하여야 한다.",
}


def v1_xml():
    rows = ["제1장 총칙"] + [(n, None, t.split("(")[1].split(")")[0], t) for n, t in ART.items()]
    return law_xml(rows, addenda=[("20250101", "100", "부칙 <제100호,2025.1.1>\n이 법은 공포한 날부터 시행한다.")],
                   annexes=[(1, "수수료", "1. 기본 수수료 1만원")])


def v2_xml(future="2026년 1월 1일"):
    """제3조 신설로 3~5조가 한 칸씩 밀리고, 벌칙 금액 개정(부칙 예외로 늦게 시행), 6조 삭제."""
    texts = {
        1: ART[1], 2: ART[2],
        3: "제3조(사전신고) 회사는 설립 전에 금융위원회에 사전신고를 하여야 한다.",
        4: ART[3].replace("제3조", "제4조"),
        5: ART[4].replace("제4조", "제5조").replace("제3조에", "제4조에"),
        6: "제6조(벌칙) 제5조를 위반한 자는 2천만원 이하의 과태료에 처한다.",
        7: "제7조 삭제 <2025.7.1>",
    }
    rows = ["제1장 총칙"] + [(n, None, (t.split("(")[1].split(")")[0] if "(" in t else ""), t)
                          for n, t in texts.items()]
    return law_xml(rows, prom="20250701", no="200", eff="20250701",
                   addenda=[("20250101", "100", "부칙 <제100호,2025.1.1>\n이 법은 공포한 날부터 시행한다."),
                            ("20250701", "200", f"부칙 <제200호,2025.7.1>\n제1조(시행일) 이 법은 공포한 날부터 "
                                                f"시행한다. 다만, 제6조의 개정규정은 {future}부터 시행한다.")],
                   annexes=[(1, "수수료", "1. 기본 수수료 1만원")])


def snap(raw):
    return parse_lawgo_xml(raw)


def base_of(snapshot):
    return [BaseArticle(a.key, a.kind, a.title, a.text, "L" + a.key, "b" + a.key, snapshot.effective, a.seq,
                        a.attachment_sha256) for a in snapshot.articles if not a.deleted]


def kinds(result):
    return [(c.change_type, c.old.key if c.old else None, c.new.key if c.new else None)
            for c in result.changes if c.change_type != "SAME" and c.kind != "ADDENDUM"]


# ------------------------------------------------------------------ 파싱

def test_flat_parse_rules():
    lines = ["이 규정은 내부 지침이다.", "제1장 총칙", "제1조(목적) 이 규정은 목적을 정한다.",
             "제1조에 따른 사항은 별도로 정한다.", "제2조 삭제<2020. 1. 1.>", "제3조", "본문 계속",
             "제4조 <삭제 2020.1.1>", "제5-1조(정의) 정의한다."]
    arts = split_flat_articles(lines)
    assert [a.key for a in arts] == ["전문", "1", "2", "3", "4", "5-1"]
    assert arts[0].text == "이 규정은 내부 지침이다."
    assert "제1조에 따른 사항은" in arts[1].text and "제1장" not in arts[1].text
    assert [a.deleted for a in arts] == [False, False, True, False, True, False]


def test_parse_rejects_duplicate_and_empty():
    with pytest.raises(ParseError, match="중복"):
        parse_lawgo_xml(law_xml([(1, None, "a", "제1조(a) 가"), (1, None, "b", "제1조(b) 나")]))
    with pytest.raises(ParseError, match="조문 0건"):
        parse_lawgo_xml(law_xml(["제1장 총칙"]))
    with pytest.raises(ParseError):
        parse_lawgo_xml(b"<not-xml")


def test_law_xml_keeps_mok_that_is_sibling_of_ho():
    raw = law_xml([(1, None, "x", "제1조(x)")]).replace(
        "<조문내용>제1조(x)</조문내용>".encode(),
        "<조문내용>제1조(x)</조문내용><항><항내용>① 다음 각 호</항내용><호><호내용>1. 첫째</호내용></호>"
        "<목><목내용>가. 목 하나</목내용></목><호><호내용>2. 둘째</호내용></호></항>".encode())
    text = parse_lawgo_xml(raw).articles[0].text
    assert text.split("\n") == ["제1조(x)", "① 다음 각 호", "1. 첫째", "가. 목 하나", "2. 둘째"]


def test_format_only_change_has_same_fingerprint():
    assert snapshot_fingerprint(snap(v1_xml())) == snapshot_fingerprint(
        snap(v1_xml().replace(b"<\xec\xa1\xb0\xeb\xac\xb8>", b"\n  <\xec\xa1\xb0\xeb\xac\xb8>")))


# ------------------------------------------------------------------ 조문 비교

def test_diff_insert_shift_keeps_lineage():
    old, new = snap(v1_xml()), snap(v2_xml())
    result = diff_snapshot(base_of(old), new.articles, doc_cd="LAW:999001", version_id="v2")
    assert kinds(result) == [("ADD", None, "3"), ("MOVE", "3", "4"), ("MOVE", "4", "5"),
                             ("MOVE_AMEND", "5", "6"), ("DELETE", "6", None)]
    moved = {c.new.key: c for c in result.changes if c.new is not None}
    assert moved["4"].lineage_id == "L3" and moved["6"].lineage_id == "L5"
    assert "이동으로 설명" in moved["5"].reason          # 제3조→제4조 인용 변경은 이동으로 설명됨


def _pair(old_text, new_text, extra_old=(), extra_new=()):
    old = [Article(k, "ARTICLE", "", t, i) for i, (k, t) in enumerate([*extra_old, ("9", old_text)], 1)]
    new = [Article(k, "ARTICLE", "", t, i) for i, (k, t) in enumerate([*extra_new, ("9", new_text)], 1)]
    base = [BaseArticle(a.key, a.kind, "", a.text, "L" + a.key, "b" + a.key, "20250101", a.seq) for a in old]
    return diff_snapshot(base, new, doc_cd="D", version_id="v")


def test_ref_only_requires_explained_internal_move():
    long = "회사는 보고서를 작성하여 금융위원회에 제출하고 그 사본을 본점에 비치하여야 한다."
    moved_old = [("5", "제5조(보고) " + long)]
    moved_new = [("1", "제1조(신설) 새로 생긴 의무를 정한다."), ("6", "제6조(보고) " + long)]
    explained = _pair("제9조(인용) 제5조에 따른 보고를 한다.", "제9조(인용) 제6조에 따른 보고를 한다.",
                      moved_old, moved_new)
    assert ("REF_ONLY", "9", "9") in kinds(explained)
    external = _pair("제9조(인용) 「상법」 제5조에 따른 보고를 한다.", "제9조(인용) 「상법」 제6조에 따른 보고를 한다.",
                     moved_old, moved_new)
    assert ("AMEND", "9", "9") in kinds(external)
    paragraph = _pair("제9조(인용) 제2조제1항에 따른다.", "제9조(인용) 제2조제2항에 따른다.")
    assert kinds(paragraph) == [("AMEND", "9", "9")]


def test_whitespace_only_is_same_and_low_similarity_is_full_amend():
    same = _pair("제9조(x) 제2조 부터 제7조까지 생략", "제9조(x) 제2조부터 제7조까지 생략")
    assert kinds(same) == []
    full = _pair("제9조(보고) 회사는 매년 보고한다.", "제9조(보고) 이사회는 분기마다 위험관리위원회를 개최하고 결과를 공시한다.")
    change = [c for c in full.changes if c.change_type == "AMEND"][0]
    assert "전면 개정" in change.reason


def test_out_of_order_move_is_recovered_and_manual_relink():
    text = "회사는 내부통제기준을 마련하고 준법감시인을 두어 그 준수 여부를 점검하여야 한다. 위반 시 보고한다."
    old = [Article("2", "ARTICLE", "", "제2조(내부통제) " + text, 1), Article("3", "ARTICLE", "", "제3조(a) 가나다라", 2),
           Article("4", "ARTICLE", "", "제4조(b) 마바사아", 3)]
    new = [Article("3", "ARTICLE", "", "제3조(a) 가나다라", 1), Article("4", "ARTICLE", "", "제4조(b) 마바사아", 2),
           Article("9", "ARTICLE", "", "제9조(내부통제) " + text, 3)]
    base = [BaseArticle(a.key, a.kind, "", a.text, "L" + a.key, "b" + a.key, "20250101", a.seq) for a in old]
    result = diff_snapshot(base, new, doc_cd="D", version_id="v")
    assert kinds(result) == [("MOVE", "2", "9")]
    short_old = [BaseArticle("7", "ARTICLE", "", "제7조(과태료) 1백만원", "L7", "b7", "20250101", 1)]
    short_new = [Article("8", "ARTICLE", "", "제8조(벌칙) 3년 이하 징역", 1)]
    # 짧은 조문의 번호·내용이 함께 바뀌면 계보가 끊긴다 (설계 12장) → 승인 화면에서 수동 연결
    assert sorted(c.change_type for c in diff_snapshot(short_old, short_new, doc_cd="D", version_id="v").changes) \
        == ["ADD", "DELETE"]
    linked = diff_snapshot(short_old, short_new, doc_cd="D", version_id="v", forced={"7": "8"})
    assert [(c.change_type, c.lineage_id) for c in linked.changes] == [("MOVE_AMEND", "L7")]


# ------------------------------------------------------------------ 시행일

def test_addendum_schedule_forms():
    assert resolve_when("공포 후 6개월이 경과한 날", "20260203") == "20260804"      # 실측 자본시장법 21324
    assert resolve_when("공포 후 1년이 경과한 날", "20260203") == "20270204"
    assert resolve_when("2026년 10월 1일", "20260715") == "20261001"
    s = read_schedule("제1조(시행일) 이 고시는 공포한 날부터 시행한다. 다만, 제56조의8 및 제56조의9의 개정규정은 "
                      "2026년 10월 1일부터 시행한다.", "20260715")
    assert s.default == "20260715" and s.per_article == {"56의8": "20261001", "56의9": "20261001"}
    s = read_schedule("제1조(시행일) 이 법은 공포한 날부터 시행한다. 다만, 다음 각 호의 개정규정은 해당 호에서 정하는 날부터 "
                      "시행한다.\n1. 다음 각 목의 개정규정은 2026년 1월 2일부터 시행한다.\n가. 제2조제1호의 개정규정\n"
                      "나. 제10조부터 제12조까지의 개정규정\n2. 제30조의 개정규정: 2027년 1월 1일\n제2조(경과조치) 생략",
                      "20251001")
    assert s.per_article == {"2": "20260102", "10": "20260102", "11": "20260102", "12": "20260102",
                             "30": "20270101"} and not s.unparsed


def test_foreign_addendum_numbers_are_not_this_laws_articles():
    raw = law_xml([(1, None, "a", "제1조(a) 가")], addenda=[(
        "20251001", "21065", "부칙(정부조직법) <제21065호,2025.10.1>\n제1조(시행일) 이 법은 공포한 날부터 시행한다. "
                             "다만, 제19조의 개정규정은 2026년 1월 2일부터 시행한다.")], eff="20260102")
    schedule = schedule_for(parse_lawgo_xml(raw))
    assert schedule.foreign == "정부조직법" and schedule.per_article == {} and schedule.default == "20260102"


def test_gate_stops_and_no_change():
    old, new = snap(v1_xml()), snap(v2_xml())
    base = base_of(old)
    def gate(snapshot, base_eff, today="20250801", base_list=base):
        result = diff_snapshot(base_list, snapshot.articles, doc_cd="D", version_id="v")
        schedule = schedule_for(snapshot)
        assign_effective(result, snapshot, schedule)
        return evaluate(result, snapshot, schedule, base_effective=base_eff, base_count=len(base_list), today=today)
    assert gate(old, "20250101").no_change
    assert gate(new, "20250901").stop == "BLOCKED"                     # 더 이른 시행일
    assert "정정" in gate(new, "20250701").stop_reason                  # 같은 시행일 재업로드
    pending = [BaseArticle(b.key, b.kind, b.title, b.text, b.lineage_id, b.version_id,
                           "20260101" if b.key == "5" else b.effective_from, b.seq) for b in base]
    assert gate(new, "20250101", base_list=pending).stop == "BLOCKED_PENDING"
    ok = gate(new, "20250101")
    assert ok.stop == "" and ok.counts["DELETE"] == 1


# ------------------------------------------------------------------ 서비스 전체 흐름

@pytest.fixture
def service():
    svc = IncrementService(SqliteDatabase(), today="20250801")
    svc.create_schema()
    return svc


def run_to_active(svc, raw, *, external=(), ack=True):
    result = svc.ingest(parse_lawgo_xml(raw), source_name="t.xml")
    assert result.state == "PREVIEW", result.gate
    svc.approve(result.load_id, user="u", preview_digest=result.preview_hash, acknowledge=ack)
    svc.prepare_index(result.load_id, external=external)
    return result


def test_full_cycle_versions_as_of_and_idempotency(service):
    first = run_to_active(service, v1_xml())
    service.activate(first.load_id, user="u")
    again = service.ingest(snap(v1_xml()))
    assert again.reused and again.state == "ACTIVATED"
    assert service.ingest(snap(v1_xml().replace(b"<\xec\xa1\xb0\xeb\xac\xb8>", b" <\xec\xa1\xb0\xeb\xac\xb8>"))).state == "NO_CHANGE"

    second = run_to_active(service, v2_xml())
    out = service.activate(second.load_id, user="u")
    assert out["new_rows"] == 5                                         # 신설1·이동2·이동개정1·부칙1 (삭제는 행 없이 닫기만)
    doc = "LAW:999001"
    before = {r["ARTC_KEY_VALU"]: r for r in service.articles_as_of(doc, "20250630")}
    middle = {r["ARTC_KEY_VALU"]: r for r in service.articles_as_of(doc, "20250801")}
    later = {r["ARTC_KEY_VALU"]: r for r in service.articles_as_of(doc, "20260102")}
    assert "1천만원" in before["5"]["ARTC_CTNT"] and "6" in before and "사전신고" not in before["3"]["ARTC_CTNT"]
    assert "사전신고" in middle["3"]["ARTC_CTNT"] and "1천만원" in middle["5"]["ARTC_CTNT"]   # 벌칙 개정은 아직 시행 전
    assert "2천만원" in later["6"]["ARTC_CTNT"] and "1천만원" not in json.dumps(later, ensure_ascii=False)
    assert middle["5"]["LNG_ID"] == later["6"]["LNG_ID"]               # 번호가 바뀌어도 계보 유지
    total = service.db.query("SELECT COUNT(*) AS N FROM IDD_B003_LGL_ARTC_VER")[0]["N"]
    assert service.ingest(snap(v2_xml())).reused
    assert service.db.query("SELECT COUNT(*) AS N FROM IDD_B003_LGL_ARTC_VER")[0]["N"] == total
    reviews = {r["RVW_KIND_CD"] for r in service.db.query("SELECT RVW_KIND_CD FROM IDD_B003_LGL_RVW_TRGT")}
    assert "RULE" in reviews


def test_approval_guards(service):
    first = run_to_active(service, v1_xml())
    service.activate(first.load_id, user="u")
    big = law_xml([(1, None, "a", ART[1])], prom="20250701", no="200", eff="20250701")    # 조문 대량 삭제
    result = service.ingest(snap(big))
    assert result.state == "PREVIEW"
    with pytest.raises(IncrementError, match="해시"):
        service.approve(result.load_id, user="u", preview_digest="0" * 64)
    with pytest.raises(IncrementError, match="강한 경고"):
        service.approve(result.load_id, user="u", preview_digest=result.preview_hash)
    other = service.ingest(snap(v2_xml()))
    service.approve(other.load_id, user="u", preview_digest=other.preview_hash, acknowledge=True)
    service.prepare_index(other.load_id, external=())
    service.activate(other.load_id, user="u")
    with pytest.raises(IncrementError, match="기준 판본"):
        service.approve(result.load_id, user="u", preview_digest=result.preview_hash, acknowledge=True)


def test_activation_waits_for_index_and_rolls_back(service):
    first = run_to_active(service, v1_xml(), external=("GOLD",))
    with pytest.raises(IncrementError, match="색인 준비 미완료"):
        service.activate(first.load_id, user="u")
    service.mark_index(first.load_id, "GOLD", status="READY", count=7, ref="dtls/doc")
    service.activate(first.load_id, user="u")
    second = run_to_active(service, v2_xml())
    current = [a.text for a in service.current_articles("LAW:999001")]
    # 경합 흉내: 활성화 전에 옛 조문 하나가 이미 닫혔다 → CAS 실패 → 전체 롤백
    victim = service.db.query("SELECT OLD_ARTC_VER_ID FROM IDD_B003_LGL_ARTC_CMPR WHERE LOAD_WORK_ID=:id "
                              "AND CHG_TYPE_CD='DELETE'", {"id": second.load_id})[0]["OLD_ARTC_VER_ID"]
    with service.db.transaction() as tx:
        tx.execute("UPDATE IDD_B003_LGL_ARTC_VER SET ENFC_END_DT='20250101' WHERE ARTC_VER_ID=:v", {"v": victim})
    with pytest.raises(IncrementError, match="롤백"):
        service.activate(second.load_id, user="u")
    assert service.job(second.load_id)["PRCS_STTS_CD"] == "INDEXING"
    assert service.db.query("SELECT COUNT(*) AS N FROM IDD_B003_LGL_ARTC_VER WHERE OPEN_YN='N'")[0]["N"] == 5
    with service.db.transaction() as tx:
        tx.execute("UPDATE IDD_B003_LGL_ARTC_VER SET ENFC_END_DT=NULL WHERE ARTC_VER_ID=:v", {"v": victim})
    assert [a.text for a in service.current_articles("LAW:999001")] == current
    service.activate(second.load_id, user="u")
    assert service.job(second.load_id)["PRCS_STTS_CD"] == "ACTIVATED"


def test_channel_switch_is_part_of_activation(service):
    with service.db.transaction() as tx:
        tx.execute("CREATE TABLE IDD_B003_LGL_SRCH_CHNL (RFRN_CHNL_NAME TEXT, RFRN_POST_HASH_VALU TEXT, CHAN_NO INTEGER)")
        tx.execute("INSERT INTO IDD_B003_LGL_SRCH_CHNL VALUES ('main', 'old', 3)")
    first = run_to_active(service, v1_xml())
    wrong = ChannelSwitch("IDD_B003_LGL_SRCH_CHNL", "main", "old", "new", expected_no=9)
    with pytest.raises(IncrementError):
        service.activate(first.load_id, user="u", channel=wrong)
    assert service.document("LAW:999001")["ACTV_VER_ID"] is None
    right = ChannelSwitch("IDD_B003_LGL_SRCH_CHNL", "main", "old", "new", expected_no=3)
    service.activate(first.load_id, user="u", channel=right)
    assert service.db.query("SELECT * FROM IDD_B003_LGL_SRCH_CHNL")[0] == {
        "RFRN_CHNL_NAME": "main", "RFRN_POST_HASH_VALU": "new", "CHAN_NO": 4}


def test_impact_reviews_follow_lineage(service):
    first = run_to_active(service, v1_xml())
    service.activate(first.load_id, user="u")
    with service.db.transaction() as tx:
        tx.execute("INSERT INTO IDD_B003_LGL_DOC_LINK VALUES ('LAW:999001', 'INTERNAL:R1', 'INTERNAL_MAP', NULL, NULL, "
                   "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
    second = run_to_active(service, v2_xml())
    service.activate(second.load_id, user="u")
    rows = service.db.query("SELECT RVW_KIND_CD, TAGT_RGLT_DOC_CD, TAGT_ARTC_KEY_VALU FROM IDD_B003_LGL_RVW_TRGT")
    assert {"RULE", "LINKED_DOC"} <= {r["RVW_KIND_CD"] for r in rows}
    # 제2조는 그대로(SAME)지만 인용 대상인 벌칙 조문(계보 L5)이 제5조→제6조로 이동·개정됐다
    assert ("CITING_ARTICLE", "LAW:999001", "2") in {(r["RVW_KIND_CD"], r["TAGT_RGLT_DOC_CD"],
                                                     r["TAGT_ARTC_KEY_VALU"]) for r in rows}


def test_preview_hash_is_reproducible(service):
    from lawrag.increment.preview import preview_hash, render_html
    result = service.ingest(snap(v1_xml()))
    preview = service.preview(result.load_id)
    assert preview_hash(preview) == result.preview_hash
    assert "신구조문 대비표" in render_html(preview, result.preview_hash)


# ------------------------------------------------------------------ 스키마·Dataiku

def test_schema_names_and_ddl():
    for table in TABLES:
        assert table.name.startswith(PREFIX) and len(table.name.encode()) <= 30
        for column in table.columns:
            assert len(column.name.encode()) <= 30
    oracle = ddl("oracle", "SIDDS")
    assert len([s for s in oracle if s.startswith("CREATE TABLE")]) == 10
    assert all("SIDDS." in s for s in oracle)
    assert ddl("oracle", "GOLDOWNER")[0].replace("GOLDOWNER", "SIDDS") == oracle[0]   # 개발·운영 같은 이름
    assert "LNG" in new_words() and "DOC" not in new_words()


class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def to_dict(self, orient):
        return self.rows


class _Executor:
    def __init__(self):
        self.calls = []

    def query_to_df(self, sql, pre_queries=None, post_queries=None, **kw):
        self.calls.append((sql, pre_queries, post_queries))
        return _Frame([{"ok": 1}])


def test_dataiku_transaction_is_one_plsql_block():
    executor = _Executor()
    db = DataikuDatabase(executor)
    long_text = "제1조(목적) 「상법」 '따옴표' \\ " + "가" * 2000
    with db.transaction() as tx:
        tx.execute("UPDATE T SET A=:a WHERE ID=:id AND S=:s", {"a": "x", "id": "W1", "s": "INDEXING"}, expect=1)
        tx.execute("INSERT INTO T (C) VALUES (:c)", {"c": long_text})
    sql, pre, post = executor.calls[0]
    block = pre[0]
    assert sql == "SELECT 1 AS OK FROM DUAL" and post == ["COMMIT"] and len(pre) == 1
    assert block.startswith("DECLARE") and block.rstrip().endswith("END;")
    assert "RAISE_APPLICATION_ERROR(-20901" in block and "DBMS_LOB.APPEND" in block
    assert "따옴표" not in block and "상법" not in block                # 값은 16진수로만 들어간다
    db.query("SELECT * FROM T WHERE ID=:id", {"id": "W1"})
    assert "HEXTORAW" in executor.calls[1][0]


# ------------------------------------------------------------------ 실제 법제처 판본

def _real(sha16):
    path = REAL / sha16 / "source.xml"
    if not path.is_file():
        pytest.skip("실제 판본 파일 없음")
    return parse_lawgo_xml(path.read_bytes())


def test_real_governance_act_21065_changes_article_26_only():
    old, new = _real("1ab2b728e6280db5"), _real("c4b33879c7dc5554")
    result = diff_snapshot(base_of(old), new.articles, doc_cd=new.doc_cd, version_id="v")
    assert kinds(result) == [("AMEND", "26", "26")]
    assert {a.key for a in new.articles if a.official_changed == "Y"} == {"26"}
    assert schedule_for(new).foreign == "정부조직법"


def test_real_electronic_finance_rule_future_articles():
    old, new = _real("dc75a9dab2d74863"), _real("342cfff1766f3631")
    assert old.doc_cd == new.doc_cd == "ADMRUL:21828"                 # 행정규칙ID는 발령마다 같다
    result = diff_snapshot(base_of(old), new.articles, doc_cd=new.doc_cd, version_id="v")
    schedule = schedule_for(new)
    assign_effective(result, new, schedule)
    added = {c.new.key: c.effective_from for c in result.changes if c.change_type == "ADD" and c.kind != "ADDENDUM"}
    assert added == {"56의8": "20261001", "56의9": "20261001"}
