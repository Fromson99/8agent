#!/usr/bin/env python3
"""CM/FSC 골든을 증거 역할·법령 시점·scope 좌표 계약으로 마이그레이션한다."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.ingest import ingest_lawxml_bytes
from lawrag.core.legal_generation import atomic_json
from lawrag.core.rag.index import Index, norm
from lawrag.sources.lawgo import BASE, parse_body_meta, parse_search

AS_OF = "20260827"
OFFICIAL_OC = "test"

DECISIVE_ADDITIONS = {
    "cm-025": [("상속세 및 증여세법", "제35조"), ("상속세 및 증여세법", "제39조")],
    "cm-030": [("자본시장과 금융투자업에 관한 법률 시행령", "제170조")],
    "cm-049": [("증권 인수업무 등에 관한 규정", "제2조"),
               ("증권 인수업무 등에 관한 규정", "제15조")],
}

COMPANIONS = {
    "cm-006": [("유가증권시장 상장규정", "제27조")],
    "cm-009": [("코스닥시장 상장규정", "제31조")],
    "cm-013": [("벤처기업육성에 관한 특별법", "제16조의6"),
               ("상법", "제340조의2"), ("상법", "제340조의5"), ("상법", "제434조")],
    "cm-015": [("벤처기업육성에 관한 특별법", "제16조의4")],
    "cm-016": [("벤처기업육성에 관한 특별법", "제16조의3"),
               ("벤처기업육성에 관한 특별법", "제16조의4")],
    "cm-018": [("상속세 및 증여세법 시행령", "제78조")],
    "cm-027": [("벤처기업육성에 관한 특별법", "제16조의3"),
               ("상법", "제340조의2"), ("상법", "제542조의3")],
    "cm-028": [("벤처기업육성에 관한 특별법", "제16조의3"), ("소득세법", "제94조")],
    "cm-029": [("소득세법", "제97조")],
    "cm-042": [("상법", "제382조")],
    "cm-043": [("상법", "제542조의12")],
    "cm-045": [("상법", "제434조")],
    "cm-047": [("상법", "제418조")],
    "cm-050": [("중소기업기본법", "제2조"), ("중소기업창업 지원법 시행령", "제4조")],
}


def _date(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _body_node(view, article: str):
    hits = [node for node in view.nodes
            if str(node.get("surface") or "").strip() == article
            and view.coordinate_scope(node.get("id")) == "body"]
    if len(hits) != 1:
        raise RuntimeError(f"{view.name} {article}: body 좌표 {len(hits)}개")
    return hits[0]


def _card(view, article: str, *, role: str, authority_as_of: str,
          corpus_status: str = "present", source: dict | None = None) -> dict:
    node = _body_node(view, article)
    out = {
        "law": view.name,
        "article": article,
        "doc_id": view.doc_id,
        "document_revision": view.revised,
        "document_enforcement": view.enforce,
        "node": str(node["id"]),
        "corpus_status": corpus_status,
        "evidence_role": role,
        "authority_as_of": authority_as_of,
        "coordinate_scope": "body",
        "coordinate_key": node.get("coordinate_key", f"body:{article}"),
    }
    if source:
        out["authority_source"] = source
    return out


class CurrentResolver:
    def __init__(self, store: Path):
        self.index = Index.load(store=store).scoped(None)
        self.by_name: dict[str, list] = {}
        for doc_id, view in self.index.entry_docs.items():
            self.by_name.setdefault(norm(view.name), []).append(view)

    def card(self, law: str, article: str, role: str) -> dict:
        views = self.by_name.get(norm(law), [])
        matches = []
        for view in views:
            try:
                _body_node(view, article)
            except RuntimeError:
                continue
            matches.append(view)
        if len(matches) != 1:
            raise RuntimeError(f"current {law} {article}: 문서 {len(matches)}개")
        return _card(matches[0], article, role=role, authority_as_of=AS_OF)


class HistoricalResolver:
    def __init__(self, store: Path, corpus: Path, current: CurrentResolver):
        self.store, self.corpus, self.current = store, corpus, current
        self.session = requests.Session()
        self.cache: dict[tuple[str, str, str], tuple] = {}
        self.current_ids = set(current.index.canonical_doc_ids or ())

    def _rows(self, law: str, kind: str) -> list[dict]:
        target = "eflaw" if kind == "law" else "admrul"
        nw = "1,2,3" if kind == "law" else "2"
        rows, page, total = [], 1, None
        while total is None or len(rows) < total:
            response = self.session.get(
                f"{BASE}/DRF/lawSearch.do",
                params={"OC": OFFICIAL_OC, "target": target, "type": "XML",
                        "query": law, "display": "100", "page": str(page), "nw": nw},
                timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            if total is None:
                total = int(root.findtext("totalCnt", "0") or 0)
            batch = parse_search(response.text, kind)
            rows.extend(batch)
            if not batch or page >= 10:
                break
            page += 1
        return [row for row in rows if norm(row.get("name", "")) == norm(law)]

    def snapshot(self, law: str, article: str, as_of: str, kind: str) -> dict:
        key = (law, as_of, kind)
        cached = self.cache.get(key)
        if cached is None:
            eligible = [row for row in self._rows(law, kind)
                        if _date(row.get("enforce", ""))
                        and _date(row["enforce"]) <= as_of]
            if not eligible:
                raise RuntimeError(f"{law}: {as_of} 이전 공식 시행본문 없음")
            row = max(eligible, key=lambda item: (
                _date(item.get("enforce", "")), _date(item.get("promulgated", "")),
                str(item.get("serial", ""))))
            if kind == "law":
                params = {"OC": OFFICIAL_OC, "target": "eflaw", "MST": row["serial"],
                          "efYd": _date(row["enforce"]), "type": "XML"}
            else:
                params = {"OC": OFFICIAL_OC, "target": "admrul", "ID": row["serial"],
                          "type": "XML"}
            response = self.session.get(f"{BASE}/DRF/lawService.do", params=params, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            if root.tag == "Law" and not list(root) and "일치하는 법령" in "".join(root.itertext()):
                raise RuntimeError(f"{law}: 역사 본문 API가 빈 결과")
            meta = parse_body_meta(response.text, kind)
            raw = response.content
            sha = hashlib.sha256(raw).hexdigest()
            doc_id = sha[:16]
            safe = re.sub(r"[\\/:*?\"<>|]", "_", law)
            raw_path = self.corpus / safe / f"{as_of}-effective-{row['enforce']}-{row['serial']}.xml"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(raw)
            source = {"provider": "국가법령정보센터",
                      "endpoint": response.url, "sha256": sha,
                      "official_serial": row["serial"],
                      "effective_snapshot": _date(row["enforce"])}
            if doc_id not in self.current_ids:
                ingest_lawxml_bytes(raw, law, self.store, "법령·규정/연혁", {
                    "kind": kind, "series": law, "status": "구판", "canonical": False,
                    "enforce": _date(row.get("enforce", "")),
                    "revised": _date(meta.get("promulgated") or row.get("promulgated", "")),
                    "promul_no": meta.get("promul_no") or row.get("promul_no", ""),
                    "law_serial": row["serial"], "law_id": meta.get("doc_id", ""),
                    "authority_mode": "historical-effective",
                    "authority_as_of": as_of, "historical_source": source,
                })
            meta_path = self.store / doc_id / "meta.json"
            result_path = self.store / doc_id / "result.json"
            meta_blob = json.loads(meta_path.read_text(encoding="utf-8"))
            result_blob = json.loads(result_path.read_text(encoding="utf-8"))
            from lawrag.core.rag.index import DocView
            view = DocView.build(doc_id, meta_blob, result_blob)
            cached = (view, source, doc_id in self.current_ids)
            self.cache[key] = cached
        view, source, same_current = cached
        return _card(view, article, role="decisive", authority_as_of=as_of,
                     corpus_status=("present_same_text" if same_current else "historical_present"),
                     source=source)


def migrate_cm(path: Path, resolver: CurrentResolver) -> dict:
    blob = json.loads(path.read_text(encoding="utf-8"))
    blob["schema_version"] = 3
    blob["version"] = 2
    blob["name"] = "cm-field-core-e2e-v2"
    blob["supersedes"] = {"name": "cm-field-core-e2e-v1",
                           "reason": "legal authority generation, evidence roles, and coordinate scopes"}
    blob["evidence_contract"] = {
        "decisive": "expected_articles; primary retrieval/citation grading",
        "required_companion": "required_companions; closure completeness grading outside top-k competition",
        "auxiliary": "auxiliary_evidence; explicit non-primary context or incorporated range",
        "authority_as_of": AS_OF,
        "coordinate_schema": "coordinate-scope-v1",
    }
    for case in blob["cases"]:
        decisive = []
        for row in case.get("expected_articles", ()):
            decisive.append(resolver.card(row["law"], row["article"], "decisive"))
        existing = {(row["law"], row["article"]) for row in decisive}
        for law, article in DECISIVE_ADDITIONS.get(case["id"], ()):
            if (law, article) not in existing:
                decisive.append(resolver.card(law, article, "decisive"))
        case["expected_articles"] = decisive
        case["required_companions"] = [
            resolver.card(law, article, "required_companion")
            for law, article in COMPANIONS.get(case["id"], ())]
        case["auxiliary_evidence"] = []
        if case["id"] == "cm-005":
            case["auxiliary_evidence"] = [
                resolver.card("자본시장과 금융투자업에 관한 법률", "제9조",
                              "context_definition")]
        elif case["id"] == "cm-046":
            case["auxiliary_evidence"] = [{
                "law": "상법", "from_article": "제417조", "to_article": "제432조",
                "evidence_role": "incorporated_range", "authority_as_of": AS_OF,
                "coordinate_scope": "body", "grading": "relation_range_not_each_article",
            }]
        case["material"] = "complete"
        case["axes"]["material"] = "complete"
    blob["counts"].update({
        "decisive_article_instances": sum(len(c["expected_articles"]) for c in blob["cases"]),
        "required_companion_instances": sum(len(c["required_companions"]) for c in blob["cases"]),
        "auxiliary_evidence_items": sum(len(c["auxiliary_evidence"]) for c in blob["cases"]),
    })
    blob["grading"].update({
        "retrieval": "expected_articles(decisive)의 현행 canonical 법령·본문 조문 좌표 회수",
        "companion_closure": "required_companions 전부 부착; top-k 경쟁과 별도 집계",
        "auxiliary": "auxiliary_evidence는 primary recall 분모에서 제외",
    })
    atomic_json(path, blob)
    return {"cases": len(blob["cases"]), **{k: blob["counts"][k] for k in (
        "decisive_article_instances", "required_companion_instances", "auxiliary_evidence_items")}}


def migrate_fsc(path: Path, resolver: CurrentResolver,
                historical: HistoricalResolver) -> dict:
    blob = json.loads(path.read_text(encoding="utf-8"))
    blob["schema_version"] = 2
    blob["version"] = 2
    blob["name"] = "fsc-hard-retrieval-v2"
    blob["supersedes"] = {"name": "fsc-hard-retrieval-v1",
                           "reason": "answer-time/current coordinate separation"}
    blob["temporal_contract"] = {
        "answer_time_articles": "official effective snapshot on or before published date",
        "current_articles": f"official canonical generation as of {AS_OF}",
        "expected_articles": "backward-compatible alias of current_articles for retrieval-only grading",
        "no_silent_rebinding": True,
    }
    for case in blob["cases"]:
        current = [resolver.card(row["law"], row["article"], "decisive")
                   for row in case.get("expected_articles", ())]
        answer_time = []
        for row in current:
            views = resolver.by_name[norm(row["law"])]
            kind = "admrul" if any(view.kind == "admrul" for view in views) else "law"
            answer_time.append(historical.snapshot(
                row["law"], row["article"], _date(case["published"]), kind))
        case["answer_as_of"] = _date(case["published"])
        case["answer_time_articles"] = answer_time
        case["current_as_of"] = AS_OF
        case["current_articles"] = current
        case["expected_articles"] = copy.deepcopy(current)
    blob["counts"].update({
        "current_article_instances": sum(len(c["current_articles"]) for c in blob["cases"]),
        "answer_time_article_instances": sum(len(c["answer_time_articles"]) for c in blob["cases"]),
        "historical_documents": len({a["doc_id"] for c in blob["cases"]
                                     for a in c["answer_time_articles"]}),
    })
    blob["selection_policy"].pop("exclude_temporally_drifted_coordinates", None)
    blob["selection_policy"]["temporal_drift_explicitly_split"] = True
    blob["grading"]["match_key"] = "current_articles: doc_id + body article-root node"
    blob["grading"]["historical_provenance"] = (
        "answer_time_articles is audited separately and never silently rebound to current_articles")
    atomic_json(path, blob)
    return {"cases": len(blob["cases"]), **{k: blob["counts"][k] for k in (
        "current_article_instances", "answer_time_article_instances", "historical_documents")}}


def migrate_semantic_seed(source: Path, target: Path, cm_path: Path,
                          fsc_path: Path) -> dict:
    """Rebind a derived semantic suite to the current source-golden coordinates."""
    blob = json.loads(source.read_text(encoding="utf-8"))
    cm = json.loads(cm_path.read_text(encoding="utf-8"))
    fsc = json.loads(fsc_path.read_text(encoding="utf-8"))
    source_cases = {case["id"]: case for case in cm["cases"]}
    source_cases.update({case["id"]: case for case in fsc["cases"]})
    source_hashes = {
        "cm": hashlib.sha256(cm_path.read_bytes()).hexdigest(),
        "fsc-hard": hashlib.sha256(fsc_path.read_bytes()).hexdigest(),
    }
    blob["schema_version"] = 2
    blob["version"] = 2
    blob["name"] = "semantic-operation-seed-golden-v2"
    blob["supersedes"] = {
        "name": "semantic-operation-seed-golden-v1",
        "reason": "source golden authority generation and current body coordinates",
    }
    blob["authority_contract"] = {
        "as_of": AS_OF,
        "source_cm": str(cm_path.relative_to(ROOT)),
        "source_cm_sha256": source_hashes["cm"],
        "source_fsc": str(fsc_path.relative_to(ROOT)),
        "source_fsc_sha256": source_hashes["fsc-hard"],
        "coordinate_schema": "coordinate-scope-v1",
        "no_stale_source_copy": True,
    }
    for case in blob["cases"]:
        provenance = case["provenance"]
        source_id = provenance["source_case_id"]
        source_case = source_cases[source_id]
        dataset = provenance["source_dataset"]
        expected = (source_case["current_articles"] if dataset == "fsc-hard"
                    else source_case["expected_articles"])
        if case["reference_answer"] != source_case["reference_answer"]:
            raise RuntimeError(f"{case['id']}: source reference answer drift")
        case["expected_articles"] = copy.deepcopy(expected)
        provenance["source_path"] = str((fsc_path if dataset == "fsc-hard" else cm_path).relative_to(ROOT))
        provenance["source_sha256"] = source_hashes[dataset]
        provenance["inherited_fields"] = ["reference_answer", "expected_articles"]
    blob["counts"]["expected_article_instances"] = sum(
        len(case["expected_articles"]) for case in blob["cases"])
    blob["counts"]["current_exact_coordinates"] = blob["counts"]["expected_article_instances"]
    atomic_json(target, blob)
    return {
        "cases": len(blob["cases"]),
        "expected_article_instances": blob["counts"]["expected_article_instances"],
        "current_exact_coordinates": blob["counts"]["current_exact_coordinates"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=ROOT / "01_DATA" / "structure")
    parser.add_argument("--cm", type=Path, default=ROOT / "01_DATA" / "review" / "cm_core_e2e_v2.json")
    parser.add_argument("--fsc", type=Path, default=ROOT / "01_DATA" / "review" / "fsc_hard_retrieval_v2.json")
    parser.add_argument("--history-corpus", type=Path,
                        default=ROOT / "01_DATA" / "corpus" / "law_history")
    parser.add_argument("--semantic-source", type=Path,
                        default=ROOT / "01_DATA" / "review" / "semantic_operation_seed_v1.json")
    parser.add_argument("--semantic", type=Path,
                        default=ROOT / "01_DATA" / "review" / "semantic_operation_seed_v2.json")
    parser.add_argument("--semantic-only", action="store_true")
    args = parser.parse_args()
    if args.semantic_only:
        result = {"semantic": migrate_semantic_seed(
            args.semantic_source, args.semantic, args.cm, args.fsc)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    current = CurrentResolver(args.store)
    history = HistoricalResolver(args.store, args.history_corpus, current)
    result = {"cm": migrate_cm(args.cm, current),
              "fsc": migrate_fsc(args.fsc, current, history),
              "semantic": migrate_semantic_seed(
                  args.semantic_source, args.semantic, args.cm, args.fsc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
