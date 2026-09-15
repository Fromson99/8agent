"""녹화 도구 — 실제 모델을 한 번 태워 응답을 고정한다 (T-A6.9 녹화/재생).

    .venv/bin/python -m tests.agent6.record_fixtures --dry-run     # 무엇을 부를지만
    .venv/bin/python -m tests.agent6.record_fixtures               # 전부 녹화(과금)
    .venv/bin/python -m tests.agent6.record_fixtures --only clean D-20:하락부인

lexicon 이 사라지면서 판정이 전부 LLM 이 되었고, 테스트가 키 없이 도는 길은 재생뿐이다.
이 파일은 그 재생분을 만드는 자리이며, **여기서만 돈이 든다.**

## 무엇을 녹화하고 무엇을 녹화하지 않는가

    녹화한다     모델의 판정이 궁금한 것 — 골든 3종, 변이 12종.
    녹화 안 한다 엔진의 처리가 궁금한 것 — 인용 검증·화자 검사·파생·라우팅·종합 판정.
                 그쪽은 대본 판정기(tests/agent6/fakes.py)가 더 적대적으로 시험한다.

## 회차(consistency)를 픽스처마다 다르게 두는 이유 — 비용이 아니라 문턱이다

    clean       k=3. **PASS 의 문턱이 가장 높은 설정**이다. 3회 만장일치가 아니면 통과가
                아니므로, 정상 통화가 통과하는지를 여기서 가장 엄하게 본다.
    violation   k=1. **위반을 잡는 문턱이 가장 높은 설정**이다. 회차를 늘리면 "한 번이라도
    ambiguous   FAIL 이면 FAIL" 규칙 덕에 잡기가 쉬워진다. 한 번에 잡는지를 본다.
    변이 12종   k=1. 같은 이유. 놓침 0 은 가장 불리한 조건에서 성립해야 한다.

## 프롬프트가 바뀌면 녹화는 낡는다

녹화 키는 요청(kind·system·user·응답 스키마)의 해시다. 항목 스펙·근거 발췌·전사·시스템
프롬프트가 한 글자라도 바뀌면 키가 달라져 재생이 **시끄럽게 실패**한다(CacheMiss).
그때는 이 도구를 다시 돌린다 — 낡은 녹화가 조용히 재생되는 것보다 낫다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.agents.agent6.src import cli, llm_cache          # noqa: E402
from tests.agent6 import mutations as mut             # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CACHE_DIR = FIXTURES / "llm"


@dataclass
class Run:
    """녹화 단위 하나 — 전사 + 메타 + 회차."""
    key: str
    transcript: Path
    meta: Path
    consistency: int
    note: str = ""
    kwargs: dict[str, Any] = field(default_factory=dict)


def plan(work_dir: Path) -> list[Run]:
    """무엇을 녹화할지 정한다. 변이 전사는 여기서 만들어진다(테스트와 같은 생성기)."""
    runs = [
        Run("clean", FIXTURES / "clean.json", FIXTURES / "clean.meta.json", 3,
            "정상 통화 — 만장일치 PASS 여야 통과"),
        Run("violation", FIXTURES / "violation.json", FIXTURES / "violation.meta.json", 1,
            "B-07·C-17 누락 + D-20 위반"),
        Run("ambiguous", FIXTURES / "ambiguous.json", FIXTURES / "ambiguous.meta.json", 1,
            "경계 발화 + 고객 질문(F-30 활성)"),
    ]
    # 변이는 **한 전사에 12종을 흩어 심어** 한 번만 태운다. 변이마다 전사를 따로 만들면
    # 전사가 12개가 되어 녹화가 열두 배로 늘어나는데(실측 72회 호출), 항목별 판정은
    # 서로 독립이므로 묻는 것은 똑같다(tests/agent6/mutations.py 의 build_combined 참조).
    runs.append(Run("mutation_combined", mut.build_combined(work_dir),
                    FIXTURES / "clean.meta.json", 1,
                    f"부재형 변이 {len(mut.변이들)}종을 흩어 심은 통화"))
    return runs


def _one(run: Run, mode: str, out_dir: Path) -> dict[str, Any]:
    result = cli.run_pipeline(
        run.transcript, meta=run.meta, out_dir=out_dir / run.key,
        llm_mode=mode, consistency=run.consistency, cache_dir=CACHE_DIR,
        history=False, append_queue=False, **run.kwargs)
    t = result.judged.llm_totals or {}
    실패 = [w for w in result.judged.warnings if "응답" in w or "호출 실패" in w]
    return {
        "key": run.key,
        "calls": result.judged.calls,
        "recorded": t.get("recorded", 0),
        "input": t.get("input_tokens", 0),
        "output": t.get("output_tokens", 0),
        "errors": t.get("errors", 0),
        "seconds": result.judged.seconds,
        "overall": result.report.overall,
        "미비": [r.id for r in result.report.items if r.verdict in ("FAIL", "UNCLEAR")],
        "실패": 실패,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="record_fixtures", description="LLM 응답 녹화")
    ap.add_argument("--only", nargs="*", metavar="KEY", help="이 키만 녹화한다")
    ap.add_argument("--mode", choices=list(llm_cache.MODES), default="record")
    ap.add_argument("--dry-run", action="store_true", help="무엇을 부를지만 보여 준다")
    args = ap.parse_args(argv)

    work = Path(tempfile.mkdtemp(prefix="agent6-record-"))
    try:
        runs = plan(work)
        if args.only:
            want = set(args.only)
            runs = [r for r in runs if r.key in want]
            모름 = want - {r.key for r in runs}
            if 모름:
                print(f"모르는 키: {', '.join(sorted(모름))}", file=sys.stderr)
                return 2
        if not runs:
            print("녹화할 것이 없습니다", file=sys.stderr)
            return 2

        print(f"녹화 계획 {len(runs)}건 → {CACHE_DIR}")
        for r in runs:
            print(f"  {r.key:<22} k={r.consistency}  {r.note}")
        if args.dry_run:
            return 0

        rows, 합 = [], {"calls": 0, "recorded": 0, "input": 0, "output": 0, "errors": 0}
        for i, r in enumerate(runs, 1):
            print(f"\n[{i}/{len(runs)}] {r.key} …", flush=True)
            got = _one(r, args.mode, work / "out")
            rows.append(got)
            for k in 합:
                합[k] += got[k]
            print(f"    호출 {got['calls']}회 / 신규녹화 {got['recorded']} / "
                  f"입력 {got['input']:,} · 출력 {got['output']:,} 토큰 / "
                  f"{got['seconds']:.0f}초 → {got['overall']}  미비 {got['미비']}")
            for w in got["실패"]:
                print(f"    !! {w}", flush=True)

        print("\n" + "=" * 78)
        print(f"합계  호출 {합['calls']}회  신규녹화 {합['recorded']}  "
              f"입력 {합['input']:,} 토큰  출력 {합['output']:,} 토큰  오류 {합['errors']}")
        print(f"녹화 파일 {len(list(CACHE_DIR.glob('*.json')))}건 — {CACHE_DIR}")
        if 합["errors"] or any(r["실패"] for r in rows):
            print("일부 호출이 실패했습니다 — 그 요청은 녹화되지 않았고 재생에서 실패합니다",
                  file=sys.stderr)
            return 1
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
