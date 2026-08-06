#!/usr/bin/env python3
"""agent6 CLI — 전사 하나를 받아 체크리스트 30항목을 점검한다 (AGENT6 §10).

    python -m agents.agent6.src.cli run --transcript t.json [--meta m.json] -o out/
        [--llm-mode {live,record,replay}] [--consistency K]
    python -m agents.agent6.src.cli harvest --queue review_queue.jsonl --resolved r.jsonl

`run` 은 §5 의 파이프라인을 순서대로 부를 뿐이고, 각 단계의 계약은 그 모듈에 있다.

    preprocess  → 전사(라우터 경유) · 활성 항목 확정
    context_asm → 항목별 프롬프트 (운영정의 + 근거 발췌 + few_shot + 전사 전문)
    judge       → LLM 단독 판정 + 자기일관성 k회
    aggregate   → 파생(F-29) · 라우팅 · 리포트 행
    report      → report.json · guidance.md · review_queue.jsonl

**LLM 없이는 점검할 수 없다.** 예전에는 키가 없으면 lexicon 결정론 모드로 자동 강등해
끝까지 돌았지만, 그 판정기가 사실상 아무것도 잡지 못한다는 것이 적대적 검증에서
드러나 없앴다. 이제 키가 없으면 그 실행은 **점검 실패**이며 종료코드 3 으로 끝난다.
키 없이 결정론적으로 돌려야 하는 자리(테스트)는 `--llm-mode replay` 를 쓴다.

## 종료 코드

    0  완전판매요건충족
    1  보완필요 (FAIL·UNCLEAR·점검불가가 있다)
    2  입력이 잘못됐다 (파일 없음·스펙 오류 등)
    3  점검 실패 — 판정자를 쓸 수 없어 점검하지 못한 항목이 있다
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.agent6.src import (aggregate, context_asm, harvest,      # noqa: E402
                               judge as judge_mod, llm_cache, preprocess, report,
                               schema)

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "output"

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_INPUT = 2
EXIT_NO_JUDGE = 3


@dataclass
class RunResult:
    """`run` 한 번의 산출 — 테스트가 이것을 직접 본다."""
    report: schema.Report
    guidance: list[schema.GuidanceEntry]
    queue: list[schema.QueueEntry]
    prepared: preprocess.Prepared
    judged: judge_mod.Judged
    paths: dict[str, str] = field(default_factory=dict)

    @property
    def checked(self) -> bool:
        """점검이 실제로 이루어졌는가. 거짓이면 리포트의 판정을 결과로 읽으면 안 된다."""
        return self.judged.usable


def run_pipeline(transcript: str | Path, *, meta: Any = None,
                 out_dir: Optional[str | Path] = None,
                 llm_mode: str = "live", consistency: int = 3,
                 per_item: bool = False, max_batch: int = 6,
                 model: Optional[str] = None,
                 cache_dir: Any = llm_cache.DEFAULT_CACHE_DIR,
                 items_dir: str | Path = preprocess.ITEMS_DIR,
                 basis_policy: str = "warn",
                 allow_missing_basis: Sequence[str] = (),
                 append_queue: bool = True, history: bool = True,
                 llm: Any = None) -> RunResult:
    """§5 파이프라인 전체. `--llm-mode replay` 면 같은 입력에 같은 결과다(녹화 재생)."""
    prepared = preprocess.prepare(transcript, meta, items_dir=items_dir,
                                  basis_policy=basis_policy,
                                  allow_missing_basis=allow_missing_basis)

    cfg = judge_mod.JudgeConfig(llm_mode=llm_mode, consistency=consistency,
                                per_item=per_item, max_batch=max_batch, model=model,
                                cache_dir=cache_dir)
    judged = judge_mod.run(prepared, config=cfg, llm=llm)

    agg = aggregate.run(prepared, judged.judgments)
    # 완전성은 aggregate 가 본다 — 꺼 둔 항목(enabled=false)까지 한 행씩 나와야 하기
    # 때문이다. `schema.Report.assert_complete` 는 켜진 항목만 기대하므로 여기서는
    # 쓰지 않는다(같은 리포트를 좁은 범위로 검사해 꺼 둔 행을 "없는 항목"이라 부른다).
    aggregate.assert_complete(agg.rows, prepared.items)

    contexts = {c.item_id: c for b in judged.batches for c in b.contexts}
    guidance = report.build_guidance(agg.rows, prepared, contexts)
    queue = report.build_queue(agg.rows, prepared)

    d = Path(out_dir or DEFAULT_OUT)
    hist = report.update_history(d / report.HISTORY_NAME, agg.rows, persist=history)
    rep = report.build(prepared, agg.rows, judged, extra_notes=agg.notes, history=hist)
    paths = report.write(rep, guidance, queue, d, append_queue=append_queue)
    return RunResult(report=rep, guidance=guidance, queue=queue, prepared=prepared,
                     judged=judged, paths=paths)


# ===========================================================================
# 명령
# ===========================================================================

def cmd_run(args) -> int:
    result = run_pipeline(
        args.transcript, meta=args.meta, out_dir=args.out,
        llm_mode=args.llm_mode, consistency=args.consistency,
        per_item=args.per_item, max_batch=args.max_batch, model=args.model,
        cache_dir=args.llm_cache, items_dir=args.items,
        basis_policy=args.basis_policy,
        allow_missing_basis=args.allow_missing_basis or (),
        append_queue=not args.fresh_queue, history=not args.no_history)

    print(report.to_text(result.report))

    judged = result.judged
    audit = judged.basis_audit
    routes = aggregate.route_counts(result.report.items)
    print()
    print("라우팅     " + ("  ".join(f"{k} {v}건" for k, v in sorted(routes.items()))
                           or "없음"))
    print(f"컨텍스트   배치 {audit.get('batches', 0)}개 / 항목 {audit.get('items', 0)}개 / "
          f"근거 원문 실림 {audit.get('with_basis_text', 0)}개 / "
          f"프롬프트 {audit.get('chars', 0):,}자")
    t = judged.llm_totals or {}
    print(f"LLM        모드 {t.get('mode', args.llm_mode)}  요청 {judged.calls}회"
          f"(배치 {audit.get('batches', 0)} × 자기일관성 {args.consistency})  "
          f"실호출 {t.get('calls', 0)}  재생 {t.get('replayed', 0)}  "
          f"신규녹화 {t.get('recorded', 0)}")
    print(f"           입력 {t.get('input_tokens', 0):,} 토큰  "
          f"출력 {t.get('output_tokens', 0):,} 토큰  오류 {t.get('errors', 0)}  "
          f"소요 {judged.seconds:.1f}초")
    print(f"저장       report={result.paths['report']}")
    print(f"           guidance={result.paths['guidance']}")
    print(f"           queue={result.paths['queue']} (신규 {result.paths['queue_added']}건)")

    if not result.checked:
        # 판정자를 못 썼다는 것은 "미비 없음"이 아니라 "보지 못했음"이다. 종료코드로 가른다.
        print(f"\n점검 실패: LLM 판정을 받지 못한 항목 {len(judged.unavailable)}개 "
              f"({', '.join(sorted(judged.unavailable))}). "
              f"이 리포트를 점검 결과로 쓰지 마십시오.", file=sys.stderr)
        return EXIT_NO_JUDGE
    # 종합 판정이 '완전판매요건충족' 이 아니면 0 이 아니다 — 판매 프로세스를 진행할 수
    # 없다는 뜻이다(§5-6).
    return EXIT_OK if result.report.overall == "완전판매요건충족" else EXIT_INCOMPLETE


def cmd_harvest(args) -> int:
    result = harvest.run(args.queue, args.resolved, items_dir=args.items,
                         dry_run=args.dry_run)
    print(result.to_text())
    if args.dry_run:
        print("\n(dry-run — 파일을 고치지 않았습니다)")
    elif result.files:
        print("\n갱신된 스펙 파일:")
        for f in result.files:
            print(f"  {f}")
    return EXIT_OK


def cmd_recordings(args) -> int:
    """무엇이 녹화돼 있는가 — replay 로 돌기 전에 사람이 확인하는 자리."""
    rows = llm_cache.index(args.llm_cache)
    if not rows:
        print(f"녹화가 없습니다: {args.llm_cache}")
        return EXIT_OK
    print(f"녹화 {len(rows)}건 — {args.llm_cache}")
    for r in rows:
        print(f"  {r['key']}  {r.get('kind', ''):<28} "
              f"{', '.join(r.get('items') or []) or '-'}  {r.get('model', '')}")
    return EXIT_OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="agent6", description="녹취 체크리스트 점검")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="전사 하나를 점검한다")
    r.add_argument("--transcript", required=True, help="STT 전사 (.json 또는 평문 .txt)")
    r.add_argument("--meta", help="상품·고객 메타 JSON (선택 — 없으면 조건부 항목이 보수 활성)")
    r.add_argument("-o", "--out", default=str(DEFAULT_OUT), help="산출 디렉터리")
    r.add_argument("--llm-mode", choices=list(llm_cache.MODES), default="live",
                   help="live: 호출만(기본) / record: 호출하고 녹화 / "
                        "replay: 녹화만 재생(키 불필요, 결정론)")
    r.add_argument("--consistency", type=int, default=3, metavar="K",
                   help="자기일관성 회차 — 같은 항목을 K번 독립 판정한다 (기본 3). "
                        "만장일치 PASS 만 PASS, 한 번이라도 FAIL 이면 FAIL")
    r.add_argument("--llm-cache", default=str(llm_cache.DEFAULT_CACHE_DIR),
                   help="녹화 디렉터리")
    r.add_argument("--per-item", action="store_true", help="항목당 한 번씩 LLM 호출")
    r.add_argument("--max-batch", type=int, default=6, help="배치당 항목 수 (기본 6)")
    r.add_argument("--model", help="LLM 모델 이름 (기본: core/llm.py 의 값)")
    r.add_argument("--items", default=str(preprocess.ITEMS_DIR), help="항목 스펙 디렉터리")
    r.add_argument("--basis-policy", choices=list(preprocess.BASIS_POLICIES), default="warn",
                   help="근거(basis)가 미해소인 항목 처리 — warn: 활성 유지+감점(기본), "
                        "block: 활성 차단(§2). block 은 종합 판정을 통과로 만들지 않는다")
    r.add_argument("--allow-missing-basis", nargs="*", metavar="좌표",
                   help="미해소를 눈감을 좌표·코퍼스 ID (예: CASE KOFIA-R). 이름을 대야 한다")
    r.add_argument("--fresh-queue", action="store_true", help="큐 파일을 새로 쓴다(덮어쓰기)")
    r.add_argument("--no-history", action="store_true",
                   help="UNCLEAR 비율 이력을 갱신하지 않는다")
    r.set_defaults(fn=cmd_run)

    h = sub.add_parser("harvest", help="큐 해소 결과를 few_shot 으로 재적재한다")
    h.add_argument("--queue", required=True)
    h.add_argument("--resolved", required=True)
    h.add_argument("--items", default=str(preprocess.ITEMS_DIR))
    h.add_argument("--dry-run", action="store_true", help="무엇이 추가될지만 보여 준다")
    h.set_defaults(fn=cmd_harvest)

    c = sub.add_parser("recordings", help="녹화된 LLM 응답 목록")
    c.add_argument("--llm-cache", default=str(llm_cache.DEFAULT_CACHE_DIR))
    c.set_defaults(fn=cmd_recordings)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except llm_cache.CacheMiss as exc:
        # 재생할 녹화가 없다 — 조용히 통과시키지 않는다. 무엇을 녹화해야 하는지 말한다.
        print(f"점검 실패(녹화 없음):\n{exc}", file=sys.stderr)
        return EXIT_NO_JUDGE
    # 사람이 고칠 수 있는 실패는 역추적(traceback) 대신 한 줄로 말한다.
    # (그 밖의 예외는 잡지 않는다 — 원인을 감추면 조용한 실패가 된다.)
    except (preprocess.PreprocessError, context_asm.ContextError,
            aggregate.AggregateError, harvest.HarvestError,
            schema.ChecklistLoadError, FileNotFoundError) as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
