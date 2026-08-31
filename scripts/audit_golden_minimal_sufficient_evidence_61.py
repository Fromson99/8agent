#!/usr/bin/env python3
"""Build the ADR-0124 source-grounded Golden61 v3 evidence audit.

This is an offline deterministic annotation migration.  It never calls a model,
retrieval, or a provider.  Frozen v2 inputs are read-only; outputs are versioned.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/ADR-0124-golden-minimal-sufficient-evidence-audit-61"
CM_V2 = ROOT / "data/review/cm_core_e2e_v2.json"
FSC_V2 = ROOT / "data/review/fsc_hard_retrieval_v2.json"
CM_V3 = ROOT / "data/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "data/review/fsc_hard_retrieval_v3.json"
LEDGER = ADR / "artifacts/golden-evidence-audit-run-003.json"

EXPECTED_INPUT_HASHES = {
    CM_V2: "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    FSC_V2: "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
}

ROLE_CONTRACT = {
    "MAIN": "direct governing article necessary for the requested conclusion",
    "DELEGATION_BRIDGE": "higher-authority provision authorizing the detailed rule",
    "INCORPORATION_BRIDGE": "article that expressly applies another provision mutatis mutandis",
    "INCORPORATED_RULE": "target rule whose substantive effect is used in the answer",
    "DEFINITION": "definition or legal-status provision needed to resolve an outcome-bearing term",
    "CONDITION_EXCEPTION": "condition, proviso, exclusion, displaced baseline, or material qualification",
    "DELEGATED_DETAIL": "decree, rule, or subordinate provision supplying delegated values or procedure",
    "TEMPORAL_TRANSITION": "effective-date, transitional, or answer-time version evidence",
}


def key(case_id: str, law: str, article: str) -> tuple[str, str, str]:
    return case_id, law, article


ROLE_OVERRIDES = {
    key("cm-003", "코스닥시장 상장규정 시행세칙", "제23조"): "CONDITION_EXCEPTION",
    key("cm-004", "증권 인수업무 등에 관한 규정", "제5조"): "DEFINITION",
    key("cm-008", "코스닥시장 상장규정 시행세칙", "제15조"): "CONDITION_EXCEPTION",
    key("cm-009", "코스닥시장 상장규정", "제31조"): "CONDITION_EXCEPTION",
    key("cm-010", "코스닥시장 상장규정", "제13조"): "INCORPORATED_RULE",
    key("cm-013", "벤처기업육성에 관한 특별법", "제16조의6"): "CONDITION_EXCEPTION",
    key("cm-013", "상법", "제340조의2"): "INCORPORATED_RULE",
    key("cm-013", "상법", "제340조의5"): "INCORPORATED_RULE",
    key("cm-013", "상법", "제434조"): "INCORPORATED_RULE",
    key("cm-014", "벤처기업육성에 관한 특별법 시행령", "제11조의3"): "DELEGATED_DETAIL",
    key("cm-015", "벤처기업육성에 관한 특별법 시행령", "제11조의5"): "DELEGATED_DETAIL",
    key("cm-015", "벤처기업육성에 관한 특별법", "제16조의4"): "CONDITION_EXCEPTION",
    key("cm-016", "벤처기업육성에 관한 특별법 시행령", "제11조의4"): "CONDITION_EXCEPTION",
    key("cm-016", "벤처기업육성에 관한 특별법", "제16조의3"): "INCORPORATED_RULE",
    key("cm-016", "벤처기업육성에 관한 특별법", "제16조의4"): "INCORPORATED_RULE",
    key("cm-017", "상속세 및 증여세법", "제60조"): "INCORPORATED_RULE",
    key("cm-017", "상속세 및 증여세법 시행령", "제49조"): "INCORPORATED_RULE",
    key("cm-018", "상속세 및 증여세법 시행령", "제49조의2"): "INCORPORATED_RULE",
    key("cm-018", "상속세 및 증여세법 시행령", "제78조"): "DELEGATED_DETAIL",
    key("cm-020", "상속세 및 증여세법", "제63조"): "DELEGATION_BRIDGE",
    key("cm-023", "상속세 및 증여세법 시행령", "제31조의3"): "DELEGATED_DETAIL",
    key("cm-025", "상속세 및 증여세법", "제35조"): "CONDITION_EXCEPTION",
    key("cm-025", "상속세 및 증여세법", "제39조"): "CONDITION_EXCEPTION",
    key("cm-027", "벤처기업육성에 관한 특별법", "제16조의3"): "DEFINITION",
    key("cm-027", "상법", "제340조의2"): "DEFINITION",
    key("cm-027", "상법", "제542조의3"): "DEFINITION",
    key("cm-028", "벤처기업육성에 관한 특별법", "제16조의3"): "DEFINITION",
    key("cm-028", "소득세법", "제94조"): "INCORPORATED_RULE",
    key("cm-029", "소득세법", "제97조"): "INCORPORATED_RULE",
    key("cm-030", "증권의 발행 및 공시 등에 관한 규정", "제2-4조"): "DEFINITION",
    key("cm-030", "자본시장과 금융투자업에 관한 법률 시행령", "제170조"): "DEFINITION",
    key("cm-035", "주식회사 등의 외부감사에 관한 법률 시행령", "제9조"): "CONDITION_EXCEPTION",
    key("cm-042", "상법", "제382조"): "DEFINITION",
    key("cm-043", "상법", "제415조"): "INCORPORATION_BRIDGE",
    key("cm-043", "상법", "제388조"): "INCORPORATED_RULE",
    key("cm-043", "상법", "제542조의12"): "CONDITION_EXCEPTION",
    key("cm-045", "상법", "제434조"): "INCORPORATED_RULE",
    key("cm-046", "상법", "제341조의4"): "CONDITION_EXCEPTION",
    key("cm-047", "상법", "제418조"): "INCORPORATED_RULE",
    key("cm-049", "증권 인수업무 등에 관한 규정", "제2조"): "DEFINITION",
    key("cm-049", "증권 인수업무 등에 관한 규정", "제15조"): "CONDITION_EXCEPTION",
    key("cm-050", "중소기업기본법", "제2조"): "DEFINITION",
    key("cm-050", "중소기업창업 지원법 시행령", "제4조"): "CONDITION_EXCEPTION",
    key("cm-051", "자본시장과 금융투자업에 관한 법률 시행규칙", "제14조"): "INCORPORATED_RULE",
    key("fsc-hard-001", "전자금융거래법", "제21조"): "DELEGATION_BRIDGE",
    key("fsc-hard-002", "금융회사의 지배구조에 관한 법률", "제11조"): "CONDITION_EXCEPTION",
    key("fsc-hard-002", "금융회사의 지배구조에 관한 법률 시행령", "제11조"): "CONDITION_EXCEPTION",
    key("fsc-hard-003", "금융회사의 지배구조에 관한 법률 시행령", "제24조"): "DELEGATED_DETAIL",
    key("fsc-hard-003", "상호저축은행법", "제11조"): "INCORPORATED_RULE",
    key("fsc-hard-003", "개인금융채권의 관리 및 개인금융채무자의 보호에 관한 법률", "제2조"): "DEFINITION",
    key("fsc-hard-005", "금융회사의 지배구조에 관한 법률 시행령", "제24조"): "DELEGATED_DETAIL",
    key("fsc-hard-006", "금융회사의 지배구조에 관한 법률", "제2조"): "DEFINITION",
    key("fsc-hard-006", "금융회사의 지배구조에 관한 법률 시행령", "제4조"): "DELEGATED_DETAIL",
    key("fsc-hard-008", "자본시장과 금융투자업에 관한 법률 시행령", "제167조"): "CONDITION_EXCEPTION",
    key("fsc-hard-009", "자본시장과 금융투자업에 관한 법률 시행령", "제46조"): "DELEGATED_DETAIL",
    key("fsc-hard-010", "신용정보의 이용 및 보호에 관한 법률", "제2조"): "DEFINITION",
}

CM_ADDITIONS = {
    "cm-023": [
        ("상속세 및 증여세법 시행령", "제31조의3", "DELEGATED_DETAIL",
         "제41조의3의 대통령령 기준금액과 정산 계산을 구체화한다."),
    ],
}

FSC_PRESENT_ADDITIONS = {
    "fsc-hard-002": [
        ("금융회사의 지배구조에 관한 법률", "제11조", "CONDITION_EXCEPTION",
         "타 영리법인이 금융회사인 경우의 보고 요건을 보존한다."),
        ("금융회사의 지배구조에 관한 법률 시행령", "제11조", "CONDITION_EXCEPTION",
         "비상근 겸직 보고의 세부 범위를 보존한다."),
    ],
    "fsc-hard-010": [
        ("신용정보의 이용 및 보호에 관한 법률", "제2조", "DEFINITION",
         "익명화 일부만으로 신용정보 성격이 사라지는지 판단할 정의 근거다."),
    ],
}

FSC_EXTERNAL_ADDITIONS = {
    "fsc-hard-001": [
        {
            "law": "전자금융거래법", "article": "제21조", "evidence_role_v3": "DELEGATION_BRIDGE",
            "reason": "전자금융감독규정 제13조의 상위 안전성 확보의무와 금융위원회 기준 위임 근거다.",
            "source_quote": "금융회사등은 전자금융거래의 안전성과 신뢰성을 확보할 수 있도록 전자적 전송이나 처리를 위한 인력, 시설, 전자적 장치, 소요경비 등의 정보기술부문, 전자금융업무 및 「전자서명법」에 의한 인증서의 사용 등 인증방법에 관하여 금융위원회가 정하는 기준을 준수하여야 한다.",
        },
    ],
    "fsc-hard-003": [
        {
            "law": "상호저축은행법", "article": "제11조", "evidence_role_v3": "INCORPORATED_RULE",
            "reason": "채무조정을 상호저축은행의 본질적·부수 업무인 자금 대출과 연결하는 규칙이다.",
            "source_quote": "상호저축은행법 제11조제1항제4호는 “자금의 대출 업무”를 규정",
        },
        {
            "law": "개인금융채권의 관리 및 개인금융채무자의 보호에 관한 법률", "article": "제2조", "evidence_role_v3": "DEFINITION",
            "reason": "채무조정이 원리금 감면·이자율 조정·새 대출에 의한 기존 채무 변제 등 채무 내용 변경임을 정한다.",
            "source_quote": "‘채무조정’이란 채권금융회사등이 보유한 개인금융채권에 대하여 원리금 감면 또는 이자율 조정, 새로운 대출을 통한 기존 채무의 변제 등으로 그 채무의 내용을 변경하는 것을 의미합니다.",
        },
    ],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class Corpus:
    def __init__(self) -> None:
        index = load(ROOT / "data/law_index.json")
        self.as_of = str(index["as_of"])
        self.current = {row["name"]: row["doc_id"] for row in index["docs"] if row.get("canonical") and row.get("in_store")}
        self.history: dict[str, list[tuple[str, str]]] = {}
        for directory in sorted((ROOT / "data/structure").iterdir()):
            meta_path = directory / "meta.json"
            result_path = directory / "result.json"
            if not meta_path.exists() or not result_path.exists():
                continue
            meta = load(meta_path)
            name = str(meta.get("name") or "")
            enforce = re.sub(r"\D", "", str(meta.get("enforce") or ""))
            self.history.setdefault(name, []).append((enforce, directory.name))

    def _card(self, doc_id: str, law: str, article: str, role: str, authority_as_of: str) -> dict[str, Any]:
        directory = ROOT / "data/structure" / doc_id
        meta = load(directory / "meta.json")
        result = load(directory / "result.json")
        nodes = [row for row in result["nodes"] if str(row.get("surface") or "").strip() == article and str(row.get("coordinate_scope") or "body") == "body"]
        if len(nodes) != 1:
            raise RuntimeError(f"{law} {article} in {doc_id}: body article roots={len(nodes)}")
        node = nodes[0]
        start, end = (int(value) for value in node["span"])
        article_text = "\n".join(str(row.get("text") or "") for row in result["blocks"][start:end + 1]).strip()
        card = {
            "law": law,
            "article": article,
            "doc_id": doc_id,
            "document_revision": str(meta.get("revised") or ""),
            "document_enforcement": str(meta.get("enforce") or ""),
            "node": str(node["id"]),
            "corpus_status": "present",
            "evidence_role": "required_companion" if role != "MAIN" else "decisive",
            "evidence_role_v3": role,
            "authority_as_of": authority_as_of,
            "coordinate_scope": "body",
            "coordinate_key": str(node.get("coordinate_key") or f"body:{article}"),
            "source_text_sha256": hashlib.sha256(article_text.encode("utf-8")).hexdigest(),
            "article_text": article_text,
        }
        if meta.get("historical_source"):
            card["authority_source"] = copy.deepcopy(meta["historical_source"])
        return card

    def current_card(self, law: str, article: str, role: str) -> dict[str, Any]:
        doc_id = self.current.get(law)
        if not doc_id:
            raise KeyError(f"no canonical current document: {law}")
        return self._card(doc_id, law, article, role, self.as_of)

    def historical_card(self, law: str, article: str, role: str, as_of: str) -> dict[str, Any]:
        candidates = [(enforce, doc_id) for enforce, doc_id in self.history.get(law, ()) if enforce and enforce <= as_of]
        if not candidates:
            raise KeyError(f"no historical document on or before {as_of}: {law}")
        enforce, doc_id = max(candidates)
        return self._card(doc_id, law, article, role, as_of)

    def verify_existing(self, case_id: str, row: dict[str, Any]) -> dict[str, Any]:
        law, article, doc_id = str(row["law"]), str(row["article"]), str(row["doc_id"])
        role = ROLE_OVERRIDES.get(key(case_id, law, article), "MAIN")
        checked = self._card(doc_id, law, article, role, str(row.get("authority_as_of") or self.as_of))
        if str(checked["node"]) != str(row["node"]):
            raise RuntimeError(f"stale node: {case_id} {law} {article}: {row['node']} != {checked['node']}")
        merged = copy.deepcopy(row)
        merged["evidence_role_v3"] = role
        merged["source_text_sha256"] = checked["source_text_sha256"]
        return merged | {"_article_text": checked["article_text"]}


def clean_for_fixture(row: dict[str, Any]) -> dict[str, Any]:
    return {key_: value for key_, value in row.items() if not key_.startswith("_") and key_ != "article_text"}


def audit_entry(row: dict[str, Any], *, action: str, reason: str) -> dict[str, Any]:
    article_text = str(row.get("_article_text") or row.get("article_text") or "")
    clean = clean_for_fixture(row)
    return clean | {
        "action": action,
        "reason": reason,
        "exact_source_text": article_text,
        "exact_source_text_sha256": hashlib.sha256(article_text.encode("utf-8")).hexdigest() if article_text else None,
    }


def generic_reason(role: str) -> str:
    return {
        "MAIN": "기준답변의 직접 결론·요건·수치·기간을 규정한다.",
        "DELEGATION_BRIDGE": "상위법의 위임 또는 권한 근거를 연결한다.",
        "INCORPORATION_BRIDGE": "다른 조문의 준용·적용을 선언한다.",
        "INCORPORATED_RULE": "준용·인용된 규칙의 실질 내용을 제공한다.",
        "DEFINITION": "결론에 영향을 주는 용어·주체·법적 지위를 정한다.",
        "CONDITION_EXCEPTION": "본문 결론의 조건·단서·예외·적용배제를 정한다.",
        "DELEGATED_DETAIL": "상위 조문이 맡긴 수치·절차·세부 범위를 정한다.",
        "TEMPORAL_TRANSITION": "회신일 또는 시행시점에 맞는 법문을 제공한다.",
    }[role]


def build_cm(corpus: Corpus, source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(source)
    out["schema_version"] = "cm-field-core-e2e-v3"
    out["version"] = "v3-minimal-sufficient-evidence"
    out["supersedes"] = "data/review/cm_core_e2e_v2.json"
    out["evidence_role_contract_v3"] = ROLE_CONTRACT
    audits = []
    for case in out["cases"]:
        case_id = case["id"]
        kept = []
        for bucket in ("expected_articles", "required_companions"):
            verified = []
            for row in case.get(bucket, ()):
                checked = corpus.verify_existing(case_id, row)
                verified.append(clean_for_fixture(checked))
                kept.append(checked)
            case[bucket] = verified
        auxiliary = []
        for row in case.get("auxiliary_evidence", ()):
            if row.get("doc_id") and row.get("node"):
                checked = corpus.verify_existing(case_id, row)
                auxiliary.append(clean_for_fixture(checked))
            else:
                checked = copy.deepcopy(row)
                checked["evidence_role_v3"] = "INCORPORATED_RULE" if row.get("evidence_role") == "incorporated_range" else "DEFINITION"
                auxiliary.append(checked)
        case["auxiliary_evidence"] = auxiliary
        additions = []
        for law, article, role, reason in CM_ADDITIONS.get(case_id, ()):
            if any(row["law"] == law and row["article"] == article for row in kept):
                raise RuntimeError(f"duplicate CM addition: {case_id} {law} {article}")
            checked = corpus.current_card(law, article, role)
            checked["addition_reason"] = reason
            case["required_companions"].append(clean_for_fixture(checked))
            kept.append(checked)
            additions.append((checked, reason))
        identities = [(row["law"], row["article"], row["doc_id"], row["node"]) for row in kept]
        if len(identities) != len(set(identities)):
            raise RuntimeError(f"duplicate CM evidence identity: {case_id}")
        case["evidence_articles"] = [clean_for_fixture(row) for row in kept]
        case["evidence_audit"] = {
            "status": "audited",
            "method": "manual reference-answer proposition and current article-root review",
            "minimal_sufficient": True,
            "article_count": len(kept),
            "external_missing_count": 0,
        }
        audits.append({
            "case_id": case_id,
            "suite": "cm-core-51",
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "status": "audited",
            "retained": [audit_entry(row, action="retain", reason=generic_reason(row["evidence_role_v3"])) for row in kept if row not in [item[0] for item in additions]],
            "added": [audit_entry(row, action="add", reason=reason) for row, reason in additions],
            "removed": [],
            "external_missing": [],
            "proposition_coverage": "complete",
        })
    out["counts"] = copy.deepcopy(out["counts"])
    out["counts"]["required_companion_instances"] = sum(len(case.get("required_companions", ())) for case in out["cases"])
    out["counts"]["minimal_sufficient_article_instances"] = sum(len(case["evidence_articles"]) for case in out["cases"])
    out["counts"]["external_missing_instances"] = 0
    return out, audits


def raw_source(case: dict[str, Any]) -> tuple[Path, str]:
    path = ROOT / case["source_file"]
    return path, path.read_text(encoding="utf-8")


def external_entry(case: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    path, text = raw_source(case)
    quote = row["source_quote"]
    if quote not in text:
        raise RuntimeError(f"external source quote not exact in {path}: {quote[:80]}")
    return row | {
        "corpus_status": "missing_document",
        "authority_as_of": re.sub(r"\D", "", str(case["published"])),
        "source_path": path.relative_to(ROOT).as_posix(),
        "source_sha256": sha(path),
        "source_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    }


def build_fsc(corpus: Corpus, source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(source)
    out["schema_version"] = "fsc-hard-retrieval-v3"
    out["version"] = "v3-minimal-sufficient-evidence"
    out["supersedes"] = "data/review/fsc_hard_retrieval_v2.json"
    out["evidence_role_contract_v3"] = ROLE_CONTRACT
    audits = []
    for case in out["cases"]:
        case_id = case["id"]
        current_checked = [corpus.verify_existing(case_id, row) for row in case["current_articles"]]
        answer_checked = [corpus.verify_existing(case_id, row) for row in case["answer_time_articles"]]
        current_companions = []
        answer_companions = []
        addition_reasons: dict[tuple[str, str], str] = {}
        for law, article, role, reason in FSC_PRESENT_ADDITIONS.get(case_id, ()):
            current = corpus.current_card(law, article, role)
            current["addition_reason"] = reason
            current_companions.append(current)
            answer_time = re.sub(r"\D", "", str(case["published"]))
            same_law = next((row for row in answer_checked if row["law"] == law), None)
            if same_law:
                historical = corpus._card(str(same_law["doc_id"]), law, article, role, answer_time)
                if same_law.get("authority_source"):
                    historical["authority_source"] = copy.deepcopy(same_law["authority_source"])
            else:
                historical = corpus.historical_card(law, article, role, answer_time)
            historical["addition_reason"] = reason
            historical["corpus_status"] = "historical_present"
            answer_companions.append(historical)
            addition_reasons[(law, article)] = reason
        external = [external_entry(case, row) for row in FSC_EXTERNAL_ADDITIONS.get(case_id, ())]
        case["current_articles"] = [clean_for_fixture(row) for row in current_checked]
        case["expected_articles"] = copy.deepcopy(case["current_articles"])
        case["answer_time_articles"] = [clean_for_fixture(row) for row in answer_checked]
        case["current_required_companions"] = [clean_for_fixture(row) for row in current_companions]
        case["answer_time_required_companions"] = [clean_for_fixture(row) for row in answer_companions]
        case["required_external_evidence"] = external
        case["current_evidence_articles"] = [clean_for_fixture(row) for row in current_checked + current_companions]
        case["answer_time_evidence_articles"] = [clean_for_fixture(row) for row in answer_checked + answer_companions]
        for group in (case["current_evidence_articles"], case["answer_time_evidence_articles"]):
            identities = [(row["law"], row["article"], row["doc_id"], row["node"]) for row in group]
            if len(identities) != len(set(identities)):
                raise RuntimeError(f"duplicate FSC evidence identity: {case_id}")
        case["evidence_audit"] = {
            "status": "audited",
            "method": "manual official FSC reply/reason and article-root review",
            "minimal_sufficient": not external,
            "current_article_count": len(case["current_evidence_articles"]),
            "answer_time_article_count": len(case["answer_time_evidence_articles"]),
            "external_missing_count": len(external),
        }
        retained = [audit_entry(row, action="retain", reason=generic_reason(row["evidence_role_v3"])) for row in current_checked]
        added = [audit_entry(row, action="add", reason=addition_reasons[(row["law"], row["article"])]) for row in current_companions]
        audits.append({
            "case_id": case_id,
            "suite": "fsc-hard-10",
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "status": "audited",
            "retained": retained,
            "added": added,
            "removed": [],
            "external_missing": external,
            "proposition_coverage": "blocked_by_missing_corpus" if external else "complete",
        })
    out["counts"] = copy.deepcopy(out["counts"])
    out["counts"]["current_required_companion_instances"] = sum(len(case["current_required_companions"]) for case in out["cases"])
    out["counts"]["answer_time_required_companion_instances"] = sum(len(case["answer_time_required_companions"]) for case in out["cases"])
    out["counts"]["required_external_evidence_instances"] = sum(len(case["required_external_evidence"]) for case in out["cases"])
    return out, audits


def question_markdown(number: int, audit: dict[str, Any]) -> str:
    def table(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "없음"
        lines = ["| 조치 | 역할 | 법령 | 조문 | corpus | 사유 |", "|---|---|---|---|---|---|"]
        for row in rows:
            lines.append("| {action} | {role} | {law} | {article} | {status} | {reason} |".format(
                action=row.get("action", "external"), role=row.get("evidence_role_v3", ""),
                law=row.get("law", "").replace("|", "\\|"), article=row.get("article", ""),
                status=row.get("corpus_status", "present"), reason=row.get("reason", "").replace("|", "\\|")))
        return "\n".join(lines)
    rows = audit["retained"] + audit["added"] + audit["external_missing"]
    quotes = []
    for row in audit["added"] + audit["external_missing"]:
        quote = row.get("exact_source_text") or row.get("source_quote") or ""
        quotes.append(f"### {row['law']} {row['article']}\n\n```text\n{quote}\n```")
    return f"""# 질문-{number:03d}: {audit['case_id']}

## 1. 실행 메타

- run: `run-003`
- arm: `baseline`, `corrected-minimal-sufficient-v3`
- 실행 유형: 결정론적 수동 골든 원문 감사; LLM·retrieval·judge 호출 없음
- 상태: `{audit['status']}`

## 2. 사용자 질문 원문

{audit['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

> 채점·감사 전용. 제품 입력에는 제공하지 않는다.

{audit['reference_answer']}

## 4. 제품 입력을 구성한 원값

제품 입력은 구성하지 않았다. 아래는 채점 전용 골든 근거 감사 원값이다.

### 회수·탈락 단계 원장 — run·arm별

{table(rows)}

## 추가·외부 누락 원문

{chr(10).join(quotes) if quotes else '추가 없음. 기존 좌표의 exact 원문 hash는 run ledger에 보존했다.'}

## 5. 제품 모델 호출 — run·arm별 실제 원문

해당 없음. 제품 모델 호출을 수행하지 않았다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

해당 없음. 중간 LLM 호출을 수행하지 않았다.

## 7. 채점 호출과 반복 판정

해당 없음. judge·다수결·반복 호출을 수행하지 않았다.

## 8. 사례 최종 판정

- proposition coverage: `{audit['proposition_coverage']}`
- 제거 좌표: 0
- 제품·채점 입출력: 해당 없음
"""


def write_outputs(cm: dict[str, Any], fsc: dict[str, Any], audits: list[dict[str, Any]]) -> dict[str, Any]:
    CM_V3.write_bytes(stable_bytes(cm))
    FSC_V3.write_bytes(stable_bytes(fsc))
    role_counts = Counter()
    for audit in audits:
        for row in audit["retained"] + audit["added"] + audit["external_missing"]:
            role_counts[row["evidence_role_v3"]] += 1
    ledger = {
        "schema_version": "golden-minimal-sufficient-evidence-audit-v1",
        "adr_id": "ADR-0124",
        "run_id": "run-003",
        "method": "manual source-grounded deterministic audit",
        "llm_calls": 0,
        "retrieval_calls": 0,
        "frozen_inputs": {path.relative_to(ROOT).as_posix(): digest for path, digest in EXPECTED_INPUT_HASHES.items()},
        "outputs": {
            CM_V3.relative_to(ROOT).as_posix(): sha(CM_V3),
            FSC_V3.relative_to(ROOT).as_posix(): sha(FSC_V3),
        },
        "summary": {
            "cases": len(audits),
            "audited_cases": sum(row["status"] == "audited" for row in audits),
            "complete_proposition_cases": sum(row["proposition_coverage"] == "complete" for row in audits),
            "blocked_by_missing_corpus_cases": sum(row["proposition_coverage"] == "blocked_by_missing_corpus" for row in audits),
            "retained_article_instances": sum(len(row["retained"]) for row in audits),
            "added_present_article_instances": sum(len(row["added"]) for row in audits),
            "removed_article_instances": sum(len(row["removed"]) for row in audits),
            "required_external_missing_instances": sum(len(row["external_missing"]) for row in audits),
            "role_counts": dict(sorted(role_counts.items())),
        },
        "cases": audits,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_bytes(stable_bytes(ledger))
    experiment = ADR / "실험"
    for number, audit in enumerate(audits, start=1):
        target = experiment / f"질문-{number:03d}-{audit['case_id']}.md"
        target.write_text(question_markdown(number, audit), encoding="utf-8")
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify committed outputs byte-for-byte")
    args = parser.parse_args()
    for path, digest in EXPECTED_INPUT_HASHES.items():
        if sha(path) != digest:
            raise RuntimeError(f"frozen v2 hash changed: {path}")
    corpus = Corpus()
    cm, cm_audits = build_cm(corpus, load(CM_V2))
    fsc, fsc_audits = build_fsc(corpus, load(FSC_V2))
    if args.check:
        expected = {CM_V3: stable_bytes(cm), FSC_V3: stable_bytes(fsc)}
        for path, payload in expected.items():
            if not path.exists() or path.read_bytes() != payload:
                raise RuntimeError(f"non-deterministic or stale output: {path}")
        print(json.dumps({"status": "ok", "checked": [path.relative_to(ROOT).as_posix() for path in expected]}, ensure_ascii=False))
        return 0
    ledger = write_outputs(cm, fsc, cm_audits + fsc_audits)
    print(json.dumps(ledger["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
