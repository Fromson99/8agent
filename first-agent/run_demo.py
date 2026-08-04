#!/usr/bin/env python3
"""데모 러너.

    .venv/bin/python run_demo.py                       # 픽스처 + 실물 PDF 1쌍
    .venv/bin/python run_demo.py --tags trust_fee,trust_period   # 볼 태그만 좁혀서

ANTHROPIC_API_KEY 가 있으면 실제 호출하고 결과를 snapshots/ 에 기록한다.
키가 없으면 기록된 스냅샷을 재생한다 — 없으면 그 사실을 명확히 알리고 멈춘다.
(문서 해석을 LLM 에 맡기므로, 가짜 판정을 지어내지 않는다)
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from trust_reconciler import report as reporting                    # noqa: E402
from trust_reconciler.docmodel import to_jsonable                   # noqa: E402
from trust_reconciler.llm.client import LLMUnavailable              # noqa: E402
from trust_reconciler.main import load_json, reconcile              # noqa: E402

FIX = ROOT / "trust_reconciler" / "tests" / "fixtures"
DATA = ROOT / "dataset"

CASES = [
    ("case_a", "정상 일치", FIX / "case_a/contract.txt", FIX / "case_a/statement.txt"),
    ("case_b", "값 1개 불일치", FIX / "case_b/contract.txt", FIX / "case_b/statement.txt"),
    ("case_c", "항목 누락", FIX / "case_c/contract.txt", FIX / "case_c/statement.txt"),
    ("case_d", "스키마 밖 항목", FIX / "case_d/contract.txt", FIX / "case_d/statement.txt"),
    ("real_pdf", "실물 PDF (발행사 상이)",
     DATA / "유안타 증권 특정금전신탁 계약서(일반형).pdf",
     DATA / "부산은행 특정금전신탁 요약(핵심) 및 추가설명서(신탁형 ISA).pdf"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="auto", choices=["auto", "anthropic", "snapshot"])
    ap.add_argument("--tags", help="쉼표로 구분한 태그 목록")
    ap.add_argument("--out", default=str(ROOT / "out"))
    args = ap.parse_args()

    schema = load_json("tag_schema.json")
    mapping = load_json("mapping_table.json")
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    rows, skipped = [], []

    for name, label, contract, statement in CASES:
        if not contract.exists() or not statement.exists():
            skipped.append((name, "입력 파일 없음")); continue
        try:
            rep = reconcile(str(contract), str(statement), tag_schema=schema,
                            mapping_table=mapping, tags=tags, llm_backend=args.llm,
                            snapshot=str(ROOT / "snapshots" / f"{name}.json"))
        except LLMUnavailable as e:
            skipped.append((name, str(e))); continue

        d = Path(args.out) / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps(to_jsonable(rep), ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        (d / "report.md").write_text(reporting.to_markdown(rep), encoding="utf-8")
        s = rep.summary
        rows.append((name, label, s["pairs"], s["match"], s["mismatch"], s["uncertain"],
                     s["missing"], s["high_severity"]))
        print(f"[ok] {name:9s} {label:22s} → {d}")

    if rows:
        print(f"\n{'케이스':10s} {'설명':24s} {'쌍':>4s} {'일치':>5s} {'불일치':>6s} "
              f"{'불확실':>6s} {'누락':>5s} {'high':>5s}")
        print("-" * 80)
        for r in rows:
            print(f"{r[0]:10s} {r[1]:24s} {r[2]:>4d} {r[3]:>5d} {r[4]:>6d} "
                  f"{r[5]:>6d} {r[6]:>5d} {r[7]:>5d}")
    for name, why in skipped:
        print(f"[skip] {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
