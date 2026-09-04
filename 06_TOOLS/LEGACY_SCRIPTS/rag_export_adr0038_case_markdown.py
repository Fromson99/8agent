#!/usr/bin/env python3
"""ADR-0038의 51개 질문을 제품/채점 입력·출력까지 사례별 Markdown으로 내보낸다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 저장소 환경 기본값
from lawrag.core.rag import answer, legal_coordinates, wikictx  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.rag_definition_context_answer_ab import (  # noqa: E402
    JUDGE_SYSTEM,
)
from scripts.rag_definition_context_wiki_eval import _legacy_wiki_pick  # noqa: E402


DISCLAIMER = """이 파일은 ADR-0038 원시 JSON을 사람이 검토하기 쉽게 펼친 감사본이다.

- 질문, 기준답변, 모델 출력, 채점 결과와 usage는 원시 artifact 값을 그대로 복사했다.
- 당시 provider raw API payload는 저장하지 않았다. 제품 system prompt는 코드 정본,
  user prompt는 동결 좌표의 원문·저장된 Wiki slug·정의 부록으로 결정론 재구성했다.
- 따라서 아래 `재구성 제품 입력`은 provider byte-for-byte 원본이라는 주장이 아니다.
  기준답변은 제품 프롬프트에 들어가지 않고 채점 프롬프트에만 들어갔다.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fence(value: str, language: str = "text") -> str:
    text = str(value or "")
    marker = "```"
    while marker in text:
        marker += "`"
    return f"{marker}{language}\n{text}\n{marker}"


def _json(value) -> str:
    return _fence(json.dumps(value, ensure_ascii=False, indent=2), "json")


def _sections(index, selected, appendix=None) -> list[Section]:
    rows = []
    for position, item in enumerate(selected, 1):
        view = index.docs[item["doc_id"]]
        rows.append(Section(
            n=position, doc_id=item["doc_id"], doc=item["doc"], node=item["node"],
            path=item["path"], page=view.by_id[item["node"]].get("page"),
            kind="법률좌표폐쇄", matched=item.get("origin") or "frozen",
            text=legal_coordinates.subtree_text(view, item["node"], cap=None)))
    for item in appendix or []:
        target = next((row for row in rows if row.doc_id == item.get("doc_id")), None)
        if target is not None:
            target.definition_context.append(dict(item))
    return rows


def _pick_from_audit(audit: list[dict]) -> list[dict]:
    catalog = {row["slug"]: row for row in wikictx._rows()}
    out = []
    for picked in audit or []:
        row = catalog.get(picked.get("slug"))
        if row is None:
            continue
        out.append({
            "slug": row["slug"], "title": picked.get("title") or row["title"],
            "text": wikictx._prompt_slice(row["text"]),
            "why": list(picked.get("why") or []), "score": 0,
        })
    return out


def _prompt(question: str, sections: list[Section], picks: list[dict]) -> str:
    return (f"[질문]\n{question}\n\n[컨텍스트]\n{answer._context_text(sections)}"
            + answer._definition_context_text(sections) + wikictx.block(picks))


def _current_picks(question: str, sections: list[Section]) -> list[dict]:
    picks, have = [], set()
    for row in wikictx.methods_for(sections):
        if row["slug"] not in have:
            picks.append(row)
            have.add(row["slug"])
    for row in wikictx.pick(question, {section.doc for section in sections}):
        if row["slug"] not in have:
            picks.append(row)
            have.add(row["slug"])
    return picks


def _legacy_picks(question: str, sections: list[Section]) -> list[dict]:
    """ADR 전 baseline의 방법 카드 + 한 단어 허용 일반 Wiki를 재구성한다."""
    catalog = {row["slug"]: row for row in wikictx._rows()}
    picks, have = [], set()
    # 방법 선택 신호는 현재와 같았고, 본문만 당시처럼 raw prefix를 사용했다.
    for picked in wikictx.methods_for(sections):
        row = catalog[picked["slug"]]
        text = row["text"][:wikictx.ARTICLE_MAX_CHARS]
        if len(row["text"]) > wikictx.ARTICLE_MAX_CHARS:
            text += "\n…(잘림 — 전문은 위키)"
        picks.append({**picked, "text": text})
        have.add(picked["slug"])
    for picked in _legacy_wiki_pick(question, {section.doc for section in sections}):
        if picked["slug"] not in have:
            picks.append(picked)
            have.add(picked["slug"])
    return picks


def _judge_user(reference: str, baseline: str, candidate: str,
                mapping: dict) -> str:
    answers = {mapping["baseline"]: baseline, mapping["candidate"]: candidate}
    return (f"[기준답변]\n{reference}\n\n[답변 A]\n{answers['A']}\n\n"
            f"[답변 B]\n{answers['B']}")


def _vote_mapping(vote: dict, default: dict) -> dict:
    if "swapped" not in vote:
        return dict(default)
    return ({"baseline": "B", "candidate": "A"} if vote["swapped"]
            else {"baseline": "A", "candidate": "B"})


def _selected_markdown(rows: list[dict]) -> str:
    if not rows:
        return "- 없음"
    return "\n".join(
        f"- `{row['doc_id']}:{row['node']}` {row['doc']} ▸ {row['path']} "
        f"(`{row.get('origin', '')}`)" for row in rows)


def _case_markdown(*, structural: dict, combined: dict, combined_regrade: dict | None,
                   definition_only: dict | None,
                   definition_regrade: dict | None,
                   baseline_selected: list[dict], index) -> str:
    case_no, question = structural["case_no"], structural["question"]
    candidate_selected = structural["candidate"]["selected"]
    appendix = structural["candidate"]["definition_appendix"]
    baseline_sections = _sections(index, baseline_selected)
    candidate_sections = _sections(index, candidate_selected, appendix)
    baseline_picks = _legacy_picks(question, baseline_sections)
    # 실제 결합 실행이 기록한 slug를 우선해 실행 당시 선택 집합을 보존한다.
    candidate_picks = _pick_from_audit(combined["candidate"].get("wiki") or [])

    parts = [
        f"# {case_no}", "", DISCLAIMER.rstrip(), "",
        "## 사용자 질문 — 원문 그대로", "", _fence(question), "",
        "## 기준답변 — 채점 전용", "", _fence(combined["reference_answer"]), "",
        "## 구조 재생", "",
        _json({
            "gold": structural["gold"],
            "baseline": structural["baseline"],
            "candidate_summary": {
                key: structural["candidate"][key] for key in (
                    "selected_count", "body_chars", "definition_appendix_count",
                    "definition_appendix_chars", "definition_appendix_documents")
            },
            "wiki": structural["wiki"],
        }), "",
        "### 후보 최종 좌표", "", _selected_markdown(candidate_selected), "",
        "### 제거된 정의 좌표", "",
        _json(structural["candidate"]["definition_dropped"]), "",
        "### 정리된 정의 부록", "", _json(appendix), "",
        "## 결합 51건 A/B", "",
        "### Baseline 재구성 제품 입력", "",
        "#### System", "", _fence(answer.ANSWER_SYSTEM), "",
        "#### User", "", _fence(_prompt(question, baseline_sections, baseline_picks)), "",
        "### Baseline 모델 출력 — artifact 원값", "",
        _fence(combined["baseline"]["answer"]), "",
        "### Candidate 재구성 제품 입력", "",
        "#### System", "", _fence(answer.ANSWER_SYSTEM), "",
        "#### User", "", _fence(_prompt(question, candidate_sections, candidate_picks)), "",
        "### Candidate 모델 출력 — artifact 원값", "",
        _fence(combined["candidate"]["answer"]), "",
        "### Candidate usage·관측값", "", _json({
            key: combined["candidate"].get(key) for key in (
                "answerable", "selected_count", "definition_entries", "wiki",
                "usage", "product_wall_ms")}), "",
        "### Paired Haiku 채점 입력", "",
        "#### System", "", _fence(JUDGE_SYSTEM), "",
        "#### User", "", _fence(_judge_user(
            combined["reference_answer"], combined["baseline"]["answer"],
            combined["candidate"]["answer"], combined["judge_order"])), "",
        "### Paired Haiku 채점 출력 — artifact 원값", "",
        _json({"order": combined["judge_order"], "judge": combined["judge"],
               "usage": combined["judge_usage"]}), "",
    ]

    if combined_regrade:
        parts.extend(["### 결합 답변 3표 재채점", ""])
        for number, vote in enumerate(combined_regrade["votes"], 1):
            mapping = _vote_mapping(vote, combined["judge_order"])
            parts.extend([
                f"#### Vote {number} 입력", "",
                _fence(_judge_user(
                    combined["reference_answer"], combined["baseline"]["answer"],
                    combined["candidate"]["answer"], mapping)), "",
                f"#### Vote {number} 출력", "", _json(vote), "",
            ])
        parts.extend(["#### 다수결", "", _json(combined_regrade["majority"]), ""])
    else:
        parts.extend(["### 결합 답변 3표 재채점", "", "- 최초 paired 판정에서 두 답변의 정오가 같아 추가 호출하지 않음.", ""])

    if definition_only:
        fresh_baseline = _sections(index, baseline_selected)
        fresh_candidate = _sections(index, candidate_selected, appendix)
        # fresh/fresh 실행은 같은 당시 Wiki 정책이었다. 저장 slug가 없어 현재 정본으로
        # 재구성하며 파일 머리의 한계를 적용한다.
        fresh_baseline_picks = _current_picks(question, fresh_baseline)
        fresh_candidate_picks = _current_picks(question, fresh_candidate)
        parts.extend([
            "## 정의-only fresh/fresh A/B", "",
            "### 정의 유지 Baseline 재구성 제품 User", "",
            _fence(_prompt(question, fresh_baseline, fresh_baseline_picks)), "",
            "### 정의 유지 Baseline 출력 — artifact 원값", "",
            _fence(definition_only["baseline"]["answer"]), "",
            "### 정의 제거+부록 Candidate 재구성 제품 User", "",
            _fence(_prompt(question, fresh_candidate, fresh_candidate_picks)), "",
            "### 정의 제거+부록 Candidate 출력 — artifact 원값", "",
            _fence(definition_only["candidate"]["answer"]), "",
            "### 정의-only paired 채점 입력", "",
            _fence(_judge_user(
                definition_only["reference_answer"], definition_only["baseline"]["answer"],
                definition_only["candidate"]["answer"], definition_only["judge_order"])), "",
            "### 정의-only paired 채점 출력", "",
            _json({"order": definition_only["judge_order"],
                   "judge": definition_only["judge"],
                   "usage": definition_only["judge_usage"]}), "",
        ])
        if definition_regrade:
            parts.extend(["### 정의-only 3표 재채점", ""])
            for number, vote in enumerate(definition_regrade["votes"], 1):
                mapping = _vote_mapping(vote, definition_only["judge_order"])
                parts.extend([
                    f"#### Vote {number} 입력", "",
                    _fence(_judge_user(
                        definition_only["reference_answer"],
                        definition_only["baseline"]["answer"],
                        definition_only["candidate"]["answer"], mapping)), "",
                    f"#### Vote {number} 출력", "", _json(vote), "",
                ])
            parts.extend(["#### 다수결", "", _json(definition_regrade["majority"]), ""])
        else:
            parts.extend(["### 정의-only 3표 재채점", "", "- 최초 paired 판정에서 두 답변의 정오가 같아 추가 호출하지 않음.", ""])
    else:
        parts.extend(["## 정의-only fresh/fresh A/B", "", "- 이 사례는 정의 조 제거 대상이 아니어서 27건 격리 실험에 포함되지 않음.", ""])
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out-dir", type=Path,
        default=ROOT / "docs/adr/ADR-0038-definition-context-wiki-hygiene/cases")
    args = parser.parse_args()
    sources = {
        "structural": ROOT / "var/eval/e2e/ADR-0038/definition_context_wiki_51.json",
        "combined": ROOT / "var/eval/e2e/ADR-0038/definition_context_answer_ab_51.json",
        "combined_regrade": ROOT / "var/eval/e2e/ADR-0038/definition_context_answer_ab_disputed21_regrade3.json",
        "definition_only": ROOT / "var/eval/e2e/ADR-0038/definition_only_fresh_answer_ab_27.json",
        "definition_regrade": ROOT / "var/eval/e2e/ADR-0038/definition_only_fresh_answer_ab_disputed12_regrade3.json",
        "stage": ROOT / "var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json",
    }
    blobs = {name: json.loads(path.read_text("utf-8")) for name, path in sources.items()}
    maps = {name: {row["case_no"]: row for row in blob.get("rows") or []}
            for name, blob in blobs.items() if name != "stage"}
    stage = {row["case_no"]: row for row in blobs["stage"]["rows"]}
    index = index_mod.current().scoped(None)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for position, structural in enumerate(blobs["structural"]["rows"], 1):
        case_no = structural["case_no"]
        baseline_selected = stage[case_no]["variants"]["control_d_then_verifier"]["selected"]
        path = args.out_dir / f"{position:03d}-{case_no}.md"
        path.write_text(_case_markdown(
            structural=structural, combined=maps["combined"][case_no],
            combined_regrade=maps["combined_regrade"].get(case_no),
            definition_only=maps["definition_only"].get(case_no),
            definition_regrade=maps["definition_regrade"].get(case_no),
            baseline_selected=baseline_selected, index=index), "utf-8")
        files.append({"position": position, "case_no": case_no,
                      "file": path.name, "bytes": path.stat().st_size,
                      "sha256": _sha(path)})

    index_lines = [
        "# ADR-0038 질문별 입력·출력 감사본", "", DISCLAIMER.rstrip(), "",
        f"- 질문 파일: {len(files)}개", "- 생성 LLM 호출: 0회", "",
        "| 번호 | 사례 | 파일 | 정의-only 포함 |", "|---:|---|---|---|",
    ]
    definition_ids = set(maps["definition_only"])
    for row in files:
        index_lines.append(
            f"| {row['position']} | {row['case_no']} | [{row['file']}]({row['file']}) | "
            f"{'예' if row['case_no'] in definition_ids else '아니오'} |")
    (args.out_dir / "README.md").write_text("\n".join(index_lines) + "\n", "utf-8")
    manifest = {
        "experiment": "ADR-0038-per-case-markdown-export-v1",
        "case_files": len(files), "llm_calls": 0,
        "sources": {name: {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
                    for name, path in sources.items()},
        "files": files,
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    artifact_manifest_path = args.out_dir.parent / "artifacts/manifest.json"
    artifact_manifest = json.loads(artifact_manifest_path.read_text("utf-8"))
    artifact_manifest["case_markdown_export"] = {
        "directory": str(args.out_dir.relative_to(ROOT)),
        "case_files": len(files),
        "readme_sha256": _sha(args.out_dir / "README.md"),
        "manifest_sha256": _sha(args.out_dir / "manifest.json"),
        "total_bytes": sum(row["bytes"] for row in files),
    }
    artifact_manifest_path.write_text(
        json.dumps(artifact_manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(artifact_manifest["case_markdown_export"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

