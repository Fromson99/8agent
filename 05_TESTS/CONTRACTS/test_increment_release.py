"""새 표 없는 증분 — 세대 정리 계획·업데이트 기록·전체 원문 조립·판단·SQL 값 검사 (DB 없이)."""
from __future__ import annotations

import zipfile

import pytest

from lawrag.increment import history
from lawrag.increment.corpus import (CorpusError, LazyZip, Replacement, assemble_files, identify, inventory,
                                     sha256, verify_base, write_zip, write_zip_file)
from lawrag.increment.dataiku_flow import Flow, Params, Stop
from lawrag.increment.decide import APPROVED, HOLD, NO_CHANGE, WAIT_EFFECTIVE, compare
from lawrag.increment.lawgo_parse import parse_lawgo_xml
from lawrag.increment.release_ops import (Names, ReleaseError, activate_sql, lit, own_channel, prune_plan)
from lawrag.increment.structured import header_from_name, header_from_xml

from test_law_increment import ART, law_xml, v1_xml, v2_xml


def rel(q, s="", d="", v="", channels=()):
    return {"query_id": q, "source_release_id": s, "dataset_version": d, "vector_post_id": v,
            "channels": list(channels)}


def test_prune_plan_protects_serving_and_shared_keys():
    g0, g1, g2, g3 = ("0" * 64, "1" * 64, "2" * 64, "3" * 64)
    rows = [rel(g0, "s0", "d0", "v0", [own_channel(g0)]),
            rel(g1, "s1", "dX", "v1", [own_channel(g1)]),            # 데이터셋을 g3와 공유
            rel(g2, "s2", "d2", "v2", ["main"]),                      # 서빙 채널이 가리킴 (keep 밖이어도 보호)
            rel(g3, "s3", "dX", "v3", [own_channel(g3)])]
    plan = prune_plan(rows, [g3])
    assert plan["protected"] == [g2]
    by = {p["query_id"]: p for p in plan["remove"]}
    assert set(by) == {g0, g1}
    assert by[g0]["own_channel"] == own_channel(g0) and by[g0]["dataset_version"] == "d0"
    assert by[g1]["dataset_version"] == ""                            # 남길 세대와 공유 → 지우지 않음
    old_serving = rel(g0, "s0", "d0", "v0", [own_channel(g1)])        # 다른 세대 이름 채널이 g0을 가리킴
    assert prune_plan([old_serving, rows[3]], [g3])["protected"] == [g0]


def test_activate_sql_is_one_guarded_block_and_values_are_checked():
    target = {"tables": {k: {"owner": "SIDDS", "name": "T_" + k, "columns": {c: {"name": c} for c in (
        "RFRN_POST_HASH_VALU", "RFRN_POST_IFMN_CTNT", "VCTR_POST_ID", "CHAN_NO", "RFRN_CHNL_NAME",
        "VCTR_POST_IFMN_CTNT", "MNFST_HASH_VALU", "DOC_ID", "DOC_NAME", "DOC_HASH_VALU", "DOC_POST_HASH_VALU",
        "STRC_UNIT_ADDN_IFMN_CTNT", "BODY_SLC_ID", "STRC_UNIT_ID", "BODY_CTNT", "BODY_SLC_ADDN_IFMN_CTNT")}}
        for k in ("DOC_VER", "DOC_UNIT", "DOC_BLK", "SRC_POST", "SRCH_POST", "SRCH_ROW", "SRCH_CHNL",
                  "VCTR_POST", "VCTR_ITEM", "VCTR_HEAD")}}
    sql = activate_sql(Names(target), channel_name="main", old_query="a" * 64, chan_no=3, new_query="b" * 64,
                       vector_post_id="v1")
    assert sql.startswith("DECLARE") and "INCREMENT_CHANNEL_CAS" in sql and "SQL%ROWCOUNT <> 1" in sql
    assert "T_VCTR_HEAD" in sql and "CHAN_NO=3" in sql
    with pytest.raises(ReleaseError):
        lit("x' OR '1'='1")
    with pytest.raises(ReleaseError):
        activate_sql(Names(target), channel_name="main", old_query="a", chan_no="3", new_query="b", vector_post_id="v")


def test_update_history_keeps_three_and_previous_generations(tmp_path):
    store = history.LocalStore(tmp_path)
    for i in range(1, 6):
        history.write_update(store, {"run": f"r{i}", "channel_before": {"query_id": f"q{i - 1}"},
                                     "channel_after": {"query_id": f"q{i}"}}, {f"a/{i}.xml": b"old"})
    ups = history.updates(store)
    assert [u["seq"] for u in ups] == [3, 4, 5]
    assert not store.list("updates/0001/") and store.get("updates/0005/old/a/5.xml") == b"old"
    assert history.keep_queries(store, "q5") == ["q5", "q4", "q3"]      # 지금 + 이전 2개
    history.mark(store, 5, "ROLLED_BACK")
    assert history.updates(store)[-1]["status"] == "ROLLED_BACK"


def _corpus():
    gov_v1 = law_xml([(1, None, "목적", ART[1])], law_id="012338", name="지배구조법")
    return {"external/financial_team/law/지배구조법/지배구조법 본문.xml": gov_v1,
            "external/risk_team/law/지배구조법/지배구조법 본문.xml": gov_v1,
            "external/financial_team/law/시험법/시험법 본문.xml": v1_xml(),
            "internal/risk_team/내부통제기준_20250101.docx": b"PK-v1"}


def test_identify_and_verify_base():
    files = _corpus()
    inv = inventory(files)
    assert {r["doc_cd"] for r in inv} >= {"LAW:012338", "LAW:999001"}
    assert identify("내부통제기준_20260101.docx", b"x") == identify("내부통제기준 20250101.docx", b"y")
    ids = {r["doc_id"] for r in inv}
    assert len(ids) == 3                                               # 두 팀 같은 파일 = 한 문서
    assert verify_base(files, ids)["ok"]
    bad = verify_base(files, ids | {"f" * 16})
    assert not bad["ok"] and bad["missing_count"] == 1


def test_assemble_replaces_all_team_copies_and_lazy_equals_dict(tmp_path):
    files = _corpus()
    gov_v2 = law_xml([(1, None, "목적", ART[1] + " 개정")], law_id="012338", name="지배구조법",
                     prom="20250701", no="200", eff="20250701")
    reps = [Replacement("LAW:012338", "x.xml", gov_v2, header_from_xml(gov_v2)),
            Replacement(identify("내부통제기준_20260101.docx", b"PK-v2"), "내부통제기준_20260101.docx", b"PK-v2",
                        header_from_name("내부통제기준", filename="내부통제기준_20260101.docx", source_sha256=sha256(b"PK-v2")))]
    out, asm = assemble_files(files, reps, as_of="20260101")
    assert out["external/financial_team/law/지배구조법/지배구조법 본문.xml"] == gov_v2
    assert out["external/risk_team/law/지배구조법/지배구조법 본문.xml"] == gov_v2
    assert "internal/risk_team/내부통제기준_20260101.docx" in out and "internal/risk_team/내부통제기준_20250101.docx" not in out
    assert out["external/financial_team/law/시험법/시험법 본문.xml"] == v1_xml()
    assert len(asm.replaced) == 3 and files["internal/risk_team/내부통제기준_20250101.docx"] == b"PK-v1"
    path = tmp_path / "base.zip"
    path.write_bytes(write_zip(files))
    lazy = LazyZip(path)
    out2, _ = assemble_files(lazy, reps, as_of="20260101")
    assert write_zip_file(out2, tmp_path / "o.zip") == sha256(write_zip(out))   # 디스크 조립 = 메모리 조립
    assert len(lazy) == len(files)                                     # 원본 ZIP 보기는 그대로
    with pytest.raises(CorpusError, match="출처 경로"):
        assemble_files(files, [Replacement("INTERNAL:new", "새규정.docx", b"n",
                                           header_from_name("새규정", source_sha256=sha256(b"n")))], as_of="x")
    new_doc, asm2 = assemble_files(files, [Replacement("INTERNAL:new", "새규정.docx", b"n",
                                                       header_from_name("새규정", source_sha256=sha256(b"n")),
                                                       source="internal/risk_team")], as_of="x")
    assert "internal/risk_team/새규정.docx" in new_doc and asm2.added


def test_decide_waits_for_effective_date_and_holds_truncated():
    old, new = parse_lawgo_xml(v1_xml()), parse_lawgo_xml(v2_xml())
    assert compare(old, new, today="20250601")["decision"] == WAIT_EFFECTIVE   # 시행일 20250701 전
    done = compare(old, new, today="20250801")
    assert done["decision"] == APPROVED and any("시행일이 더 늦음" in w for w in done["warnings"])
    assert done["preview_html"] and done["changes"]
    cut = parse_lawgo_xml(law_xml([(1, None, "목적", ART[1])], prom="20250701", no="200", eff="20250701"))
    assert compare(old, cut, today="20250801")["decision"] == HOLD
    assert compare(old, parse_lawgo_xml(v1_xml()), today="20250801")["decision"] == NO_CHANGE


def test_flow_refuses_loader_channel_as_serving(tmp_path):
    flow = Flow(store=history.LocalStore(tmp_path / "s"), drop=history.LocalStore(tmp_path / "d"),
                inputs=history.LocalStore(tmp_path / "i"), db=None, agent_db=None, names=None, r6=None,
                params=Params(channel="g19_7c1f8f4931c8be61b914f5bc"))
    with pytest.raises(Stop, match="SERVING_CHANNEL_IS_LOADER_CHANNEL"):
        flow.status()
