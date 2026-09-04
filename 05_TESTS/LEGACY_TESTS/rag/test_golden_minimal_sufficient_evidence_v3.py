from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CM_V2 = ROOT / "data/review/cm_core_e2e_v2.json"
FSC_V2 = ROOT / "data/review/fsc_hard_retrieval_v2.json"
CM_V3 = ROOT / "data/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "data/review/fsc_hard_retrieval_v3.json"
LEDGER = ROOT / "docs/adr/ADR-0124-golden-minimal-sufficient-evidence-audit-61/artifacts/golden-evidence-audit-run-003.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def by_id(blob: dict, case_id: str) -> dict:
    return next(row for row in blob["cases"] if row["id"] == case_id)


def test_frozen_v2_hashes_are_unchanged() -> None:
    assert digest(CM_V2) == "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1"
    assert digest(FSC_V2) == "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269"


def test_v3_audits_every_case_and_has_no_duplicate_coordinates() -> None:
    cm, fsc, ledger = load(CM_V3), load(FSC_V3), load(LEDGER)
    assert len(cm["cases"]) == 51
    assert len(fsc["cases"]) == 10
    assert ledger["summary"]["audited_cases"] == 61
    assert ledger["summary"]["retained_article_instances"] == 112
    assert ledger["summary"]["added_present_article_instances"] == 4
    assert ledger["summary"]["required_external_missing_instances"] == 3
    for case in cm["cases"]:
        identities = [(row["doc_id"], row["node"]) for row in case["evidence_articles"]]
        assert len(identities) == len(set(identities)), case["id"]
    for case in fsc["cases"]:
        for field in ("current_evidence_articles", "answer_time_evidence_articles"):
            identities = [(row["doc_id"], row["node"]) for row in case[field]]
            assert len(identities) == len(set(identities)), (case["id"], field)


def test_new_present_companions_and_temporal_identity() -> None:
    cm, fsc = load(CM_V3), load(FSC_V3)
    cm_023 = by_id(cm, "cm-023")
    assert [(row["law"], row["article"], row["evidence_role_v3"]) for row in cm_023["required_companions"]] == [
        ("상속세 및 증여세법 시행령", "제31조의3", "DELEGATED_DETAIL")]

    fsc_002 = by_id(fsc, "fsc-hard-002")
    assert {(row["law"], row["article"]) for row in fsc_002["current_required_companions"]} == {
        ("금융회사의 지배구조에 관한 법률", "제11조"),
        ("금융회사의 지배구조에 관한 법률 시행령", "제11조"),
    }
    answer_law = next(row for row in fsc_002["answer_time_required_companions"] if row["law"] == "금융회사의 지배구조에 관한 법률")
    assert answer_law["doc_id"] == "9ff3d75bd44e546b"
    assert answer_law["authority_as_of"] == "20260320"

    fsc_010 = by_id(fsc, "fsc-hard-010")
    assert [(row["law"], row["article"], row["evidence_role_v3"]) for row in fsc_010["current_required_companions"]] == [
        ("신용정보의 이용 및 보호에 관한 법률", "제2조", "DEFINITION")]


def test_missing_external_requirements_are_explicit_and_source_grounded() -> None:
    fsc = load(FSC_V3)
    expected = {
        "fsc-hard-001": {("전자금융거래법", "제21조")},
        "fsc-hard-003": {
            ("상호저축은행법", "제11조"),
            ("개인금융채권의 관리 및 개인금융채무자의 보호에 관한 법률", "제2조"),
        },
    }
    actual = {}
    for case in fsc["cases"]:
        rows = case["required_external_evidence"]
        if rows:
            actual[case["id"]] = {(row["law"], row["article"]) for row in rows}
        for row in rows:
            assert row["corpus_status"] == "missing_document"
            source = ROOT / row["source_path"]
            assert digest(source) == row["source_sha256"]
            assert row["source_quote"] in source.read_text(encoding="utf-8")
    assert actual == expected
