"""질의 트레이스 판독 — tuples 기록(qid)을 사람이 읽는 모양으로 편다.

    python scripts/rag_trace.py <qid>          # 특정 질의 (요약)
    python scripts/rag_trace.py --last [N]     # 최근 N건 (기본 1)
    python scripts/rag_trace.py <qid> --split  # 단별 로그 — 어느 단이 무엇을 데려왔나
    python scripts/rag_trace.py <qid> --prompt # 합성 프롬프트 원문까지
    python scripts/rag_trace.py --index        # 질의 목록 + 발동한 단
    python scripts/rag_trace.py --index --stage 필수 동반   # 그 단이 발동한 질의만

data/rag/tuples/*.jsonl 의 질의 레코드는 전모(질문·답·사다리·회수 구역·
콜 타이밍·프롬프트)를 담지만 한 줄 JSON 이라 눈으로 못 읽는다. 이 스크립트가
그 한 줄을 판독한다 — 쓰기는 없다(관측의 관측).

`--split` 은 사다리(단 이름·건수)와 회수 구역(`kind` 에 경위가 박혀 있다)을
**조인해서** 단마다 실제로 들어온 구역을 붙인다. 귀속은 kind 로 한다:
"탐색(깔때기)" → 깔때기 단, "위임"·"수임"·"배제"·"준용" → 필수 동반,
"참조" → 참조 확장, "벡터" → 벡터 진입, "용어"·"제목"·"본문" → 어휘 단.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(REPO_ROOT))


def tuples_dir() -> Path:
    store = Path(os.environ.get("STRUCTURE_STORE", REPO_ROOT / "01_DATA" / "structure"))
    return Path(os.environ.get("RAG_LOG_DIR", store.parent / "rag")) / "tuples"


def _records():
    for p in sorted(tuples_dir().glob("*.jsonl")):
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") == "질의":
                yield r


def _bar(ms: float, full_ms: float, width: int = 24) -> str:
    n = max(1, round(width * ms / full_ms)) if full_ms else 1
    return "█" * n


# ------------------------------------------------------- 단별 로그 (--split)

# 단 이름 → 그 단이 만드는 구역 kind. 회수 사다리는 kind 가 "탐색(단이름)"
# 이라 표에 없어도 이름으로 붙는다(아래 _claims). 판단·배경 단(쟁점 분해·
# 쟁점 판정·위키 맥락)은 구역을 만들지 않는다 — note 만 남는다.
STAGE_KINDS: dict[str, set] = {
    "승인 용어": {"용어"},
    "정확 일치": {"용어", "제목", "본문"},
    "부분 일치": {"용어", "제목", "본문"},
    "벡터 진입": {"벡터"},
    "필수 동반": {"배제", "위임", "수임", "준용"},
    "간선 항해": {"항해"},
    "참조 확장": {"참조"},
    "착지 교정": {"참조(교정)"},
}
NO_SECTION_STAGES = {"쟁점 분해", "쟁점 판정", "위키 맥락"}
# 회복 사다리 단 (recover.run · recover_domains) — 필터가 전부 걸렀을 때만 돈다
RECOVER_STAGES = {"의미해석", "깔때기", "원문", "수색대", "둘러보기",
                  "쟁점 재회수", "판정 재회수", "명칭 확장"}


def _w(s: str) -> int:
    """동아시아 폭 — 한글은 두 칸으로 센다(터미널 정렬)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(0, n - _w(s))


def _tail(s: str, n: int) -> str:
    """길면 앞을 접는다 — 경로는 꼬리(조·항)가 정보다."""
    if _w(s) <= n:
        return s
    out = []
    acc = 0
    for c in reversed(s):
        acc += 2 if unicodedata.east_asian_width(c) in "WF" else 1
        if acc > n - 2:
            break
        out.append(c)
    return "…" + "".join(reversed(out))


def _claims(ladder: list, ctx: list) -> tuple[dict, list]:
    """단 → 구역 귀속. 어느 단에도 안 붙는 구역은 따로 돌려준다(귀속 미상)."""
    by_stage: dict[int, list] = {}
    taken = set()
    for i, st in enumerate(ladder):
        name = str(st.get("stage") or "")
        kinds = set(STAGE_KINDS.get(name, ()))
        kinds.add(f"탐색({name})")
        got = [s for j, s in enumerate(ctx)
               if j not in taken and s.get("kind") in kinds]
        for j, s in enumerate(ctx):
            if j not in taken and s.get("kind") in kinds:
                taken.add(j)
        by_stage[i] = got
    return by_stage, [s for j, s in enumerate(ctx) if j not in taken]


def _section_line(w, s: dict, indent: str = "        ", kind: bool = False) -> None:
    tag = f"{s.get('kind', '')} " if kind else ""
    if s.get("부칙"):
        tag += f"[부칙·{s['부칙']}] "
    w(f"{indent}· [{s.get('n')}] {tag}{_tail(str(s.get('doc') or ''), 34)}"
      f" ▸ {_tail(str(s.get('path') or ''), 58)}\n")
    if s.get("matched"):
        w(f"{indent}      {str(s['matched'])[:76]}\n")


def _filter_block(w, r: dict) -> None:
    f = r.get("filter") or {}
    if not f:
        return
    if not f.get("applied"):
        w("\n■ 필터 — 돌지 않음 (구역이 문턱 미만이거나 LLM 없음)\n")
        return
    dropped = int(f.get("in", 0)) - int(f.get("out", 0))
    w(f"\n■ 필터  {f.get('in')}구역 → {f.get('out')}구역  (버림 {dropped})\n")
    if f.get("reason"):
        w(f"        └ {str(f['reason'])[:100]}\n")
    lost = f.get("버림") or []
    if lost:
        w(f"        버려진 {len(lost)}구역 — 답에 안 실린 원문:\n")
        for s in lost:
            w(f"        ✗ [{s.get('n')}] {s.get('kind', '')} "
              f"{_tail(str(s.get('doc') or ''), 30)} ▸ {_tail(str(s.get('path') or ''), 54)}\n")
            if s.get("matched"):
                w(f"              ({s['matched']})\n")
            body = re.sub(r"\s+", " ", str(s.get("발췌") or "")).strip()
            if body:
                w(f"              「{body[:300]}」\n")
    elif dropped:
        w("        ⚠ 버려진 구역의 목록이 이 기록엔 없다 (필터 버림 기록 이전의 질의)\n")


def _spot_block(w, r: dict, stage: str) -> None:
    """쟁점 상세 — 트리거가 무엇을 물었나 / LLM 이 무엇으로 판정했나."""
    js = r.get("쟁점") or {}
    if stage == "쟁점 분해":
        # 검색 전 LLM 분해가 돌았으면 그것이 실제로 쓰인 결과다 — 트리거
        # 결과는 대조용으로 그 아래 남는다(어느 쪽이 맞았는지 눈으로 잰다).
        cards = js.get("분해") if js.get("분해") is not None else js.get("트리거")
    else:
        cards = js.get("판정")
    for c in (cards or []):
        why = c.get("why") or []
        why = why if isinstance(why, list) else [str(why)]
        tag = str(c.get("via") or "")
        if c.get("score"):
            tag += f", 점수 {c['score']}"
        w(f"        ▸ {c.get('slug', '')}  ({tag})\n")
        if why:
            label = "적중 트리거" if stage == "쟁점 분해" else "판정 근거"
            w(f"          {label}: {' · '.join(str(x) for x in why)}\n")
        if c.get("probe"):
            w(f"          조문질의(벡터에 들어간 법률 문장):\n"
              f"            「{c['probe']}」\n")
        if c.get("axis"):
            w(f"          판단 축: {c['axis']}\n")
        if c.get("provisions"):
            w(f"          조문 후보: {' · '.join(c['provisions'])}\n")
    if stage == "쟁점 분해" and js.get("분해") is not None and js.get("트리거"):
        w("        ▷ (대조) 트리거 매칭이었다면: "
          + " · ".join(f"{c.get('title')}〈{' '.join(c.get('why') or [])}〉"
                       for c in js["트리거"]) + "\n")
    if stage == "쟁점 분해" and js.get("벡터질의"):
        w("        ▸ 벡터에 실제로 임베딩된 질의 (구어 제외):\n")
        for line in str(js["벡터질의"]).splitlines():
            w(f"          ⊕ {line}\n")
    if stage == "쟁점 분해" and js.get("질의확장"):
        w("        ▸ 어휘 사다리에 들어간 확장 질의 (원문 포함):\n")
        for line in str(js["질의확장"]).splitlines():
            w(f"          | {line}\n")


def _calls_block(w, r: dict) -> None:
    """모든 LLM 콜의 원문 — 판정이 무엇을 보고 섰는지."""
    calls = r.get("콜") or []
    if not calls:
        w("\n■ LLM 콜 상세 — 기록 없음 (콜 원문 저장 이전의 질의)\n")
        return
    w(f"\n{'=' * 78}\n■ LLM 콜 상세 {len(calls)}번 — 각 판정의 입력과 출력 원문\n{'=' * 78}\n")
    for i, c in enumerate(calls, 1):
        u = c.get("usage") or {}
        w(f"\n{'─' * 78}\n① {i}. {c.get('kind', '')}  {c.get('model', '')}  "
          f"{c.get('dur_ms', 0) / 1000:.1f}s  "
          f"in {u.get('input_tokens', 0):,} / out {u.get('output_tokens', 0):,} 토큰"
          f"{'  ERROR: ' + c['error'] if c.get('error') else ''}\n{'─' * 78}\n")
        w(f"\n[system]\n{c.get('system', '')}\n")
        w(f"\n[user]\n{c.get('user', '')}\n")
        w(f"\n[응답]\n{c.get('응답', '')}\n")


def render_split(r: dict, limit: int = 4, show_prompt: bool = False,
                 show_calls: bool = False) -> None:
    """단별 로그 — 사다리 각 단을 블록으로 끊고 그 단이 데려온 구역을 붙인다."""
    w = sys.stdout.write
    ctx = r.get("context") or []
    ladder = r.get("ladder") or []
    by_stage, orphans = _claims(ladder, ctx)

    w(f"\n{'━' * 78}\n")
    w(f"질의 {r.get('qid')} · {r.get('ts', '')} · mode={r.get('mode')}"
      f" · answerable={r.get('answerable')}\n")
    w(f"Q  {r.get('질의', '')}\n")
    w("   ('N건' = 그 단이 보고한 수 · '구역 +N' = 최종 컨텍스트까지 살아남아 "
      "그 단에 귀속된 수)\n\n")

    filtered = False
    running = 0
    for i, st in enumerate(ladder):
        name = str(st.get("stage") or "")
        # 필터는 사다리에 단으로 안 남는다 — 회복 단 직전(= 필터가 다 걸러
        # 회복이 돈 자리)이나 판단 단 직전에 끼워 실제 순서를 복원한다.
        if not filtered and (name in RECOVER_STAGES or name in NO_SECTION_STAGES) \
                and i > 0:
            _filter_block(w, r)
            filtered = True
            w("\n")
        got = by_stage.get(i) or []
        running += len(got)
        head = f"[{i + 1:02d}] {_pad(name, 14)}"
        if name in NO_SECTION_STAGES:
            w(f"{head} {st.get('count', 0):>3}건  (판단·배경 — 구역 없음)\n")
        else:
            w(f"{head} {st.get('count', 0):>3}건  구역 +{len(got)} → 누적 {running}\n")
        if st.get("note"):
            w(f"        └ {str(st['note'])[:96]}\n")
        if name in ("쟁점 분해", "쟁점 판정"):
            _spot_block(w, r, name)
        for s in got[:limit]:
            _section_line(w, s)
        if len(got) > limit:
            w(f"        · … 외 {len(got) - limit}구역\n")
        w("\n")

    if not filtered:
        _filter_block(w, r)
        w("\n")

    if orphans:
        w(f"[--] {_pad('귀속 미상', 14)} {len(orphans):>3}건  "
          f"(그 구역을 만든 단이 사다리에 안 남았다)\n")
        for s in orphans[:limit]:
            _section_line(w, s, kind=True)
        if len(orphans) > limit:
            w(f"        · … 외 {len(orphans) - limit}구역\n")
        w("\n")

    add = [c.get("부칙") for c in ctx if c.get("부칙")]
    if add:
        import collections as _c
        dist = " · ".join(f"{k} {v}" for k, v in _c.Counter(add).most_common())
        w(f"■ 부칙 종류 (관측 — 회수에 관여 안 함)  {dist}"
          f"  / 본문 {len(ctx) - len(add)}\n\n")

    t = r.get("timing") or {}
    calls = t.get("calls") or []
    if calls:
        total = sum(c.get("dur_ms", 0) for c in calls)
        w(f"■ LLM 콜 {len(calls)}번 · 합계 {total / 1000:.1f}초 "
          f"(사용자 대기 = 합계, SSE 없음)\n")
        for c in calls:
            d = c.get("dur_ms", 0)
            w(f"   {_pad(str(c.get('kind', '')), 22)} {d / 1000:>6.1f}s "
              f"{_bar(d, total)}\n")
        w("\n")

    refs = r.get("refs") or []
    w(f"■ 근거  refs {len(refs)}개"
      + (f" · cited {r.get('cited')}" if r.get("cited") else "") + "\n")
    for ref in refs:
        w(f"   → [{ref.get('n')}] {_tail(str(ref.get('doc') or ''), 34)}"
          f" ▸ {_tail(str(ref.get('path') or ''), 58)}\n")
    w(f"\n■ 답 ({'가능' if r.get('answerable') else '불가'})\n"
      f"{(r.get('답') or '(없음)')}\n")
    if show_calls:
        _calls_block(w, r)
    if show_prompt and r.get("프롬프트"):
        p = r["프롬프트"]
        w(f"\n■ 합성 프롬프트 — system\n{p.get('system', '')}\n")
        w(f"\n■ 합성 프롬프트 — user (지식이 주입된 실물)\n{p.get('user', '')}\n")


def render_index(rows: list, stage: str = "") -> None:
    """질의 목록 — 어느 상황(단 조합)이 발동했는지로 예시를 고른다."""
    w = sys.stdout.write
    if stage:
        rows = [r for r in rows
                if any(stage in str(st.get("stage") or "")
                       for st in (r.get("ladder") or []))]
        w(f"\n단 '{stage}' 이(가) 발동한 질의 {len(rows)}건\n")
    else:
        w(f"\n질의 {len(rows)}건 — qid 를 골라 --split 으로 편다\n")
    w(f"{'─' * 78}\n")
    for r in rows:
        stages = " → ".join(str(st.get("stage") or "")
                            for st in (r.get("ladder") or [])) or "(사다리 없음)"
        w(f"{r.get('qid')}  {str(r.get('ts', ''))[5:16]}  "
          f"{_pad(str(r.get('mode') or ''), 8)}"
          f"{'○' if r.get('answerable') else '×'}  "
          f"{_tail(str(r.get('질의', '')), 40)}\n")
        w(f"{' ' * 14}{stages}\n")


def render(r: dict, show_prompt: bool = False) -> None:
    w = sys.stdout.write
    w(f"\n{'=' * 74}\n")
    w(f"질의 {r.get('qid')} · {r.get('ts', '')} · mode={r.get('mode')}"
      f" · answerable={r.get('answerable')}\n")
    w(f"Q: {r.get('질의', '')}\n")

    ladder = r.get("ladder") or []
    if ladder:
        w("\n■ 사다리 — 회수 경위 (위에서 아래로 흐른다)\n")
        for st in ladder:
            note = str(st.get("note") or "")
            w(f"   {st.get('stage', ''):　<10} {st.get('count', 0):>3}  {note[:88]}\n")

    f = r.get("filter") or {}
    if f.get("applied"):
        w(f"\n■ 필터  {f.get('in')}구역 → {f.get('out')}구역"
          f"{' — ' + str(f.get('reason'))[:60] if f.get('reason') else ''}\n")

    t = r.get("timing") or {}
    calls = t.get("calls") or []
    if calls:
        total = sum(c.get("dur_ms", 0) for c in calls)
        models = {c.get("model", "?") for c in calls}
        w(f"\n■ LLM 콜 {len(calls)}번 · 합계 {total / 1000:.1f}초"
          f" · 모델 {' · '.join(sorted(models))}\n")
        for c in calls:
            d = c.get("dur_ms", 0)
            w(f"   {c.get('kind', ''):<24} {d / 1000:>6.1f}s "
              f"{_bar(d, total)}  (TTFT {c.get('ttft_ms', 0) / 1000:.1f}s)\n")
        w(f"   답 합성 TTFT {t.get('answer_ttft_ms', 0) / 1000:.1f}초 — "
          f"사용자 체감은 파이프라인 전체이므로 합계가 대기 시간이다 (SSE 없음)\n")

    ctx = r.get("context") or []
    if ctx:
        w(f"\n■ 회수 구역 {len(ctx)}개 — 모델이 본 [컨텍스트]\n")
        for s in ctx:
            w(f"   [{s.get('n')}] {s.get('doc', '')} ▸ {s.get('path', '')}"
              f"  ({s.get('kind', '')})\n")

    refs = r.get("refs") or []
    cited = r.get("cited") or []
    w(f"\n■ 근거  refs {len(refs)}개"
      + (f" · cited {cited}" if cited else "") + "\n")
    for ref in refs:
        w(f"   → {ref.get('doc', '')} ▸ {ref.get('path', '')}\n")

    w(f"\n■ 답\n{(r.get('답') or '(없음)')}\n")

    if r.get("recovery"):
        w(f"\n■ 회복  rungs={r['recovery'].get('rungs_fired')}\n")
    if show_prompt and r.get("프롬프트"):
        p = r["프롬프트"]
        w(f"\n■ 합성 프롬프트 — system\n{p.get('system', '')}\n")
        w(f"\n■ 합성 프롬프트 — user (지식이 주입된 실물)\n{p.get('user', '')}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("qid", nargs="?", help="질의 id (응답·원장·이 스크립트 --last 로 확인)")
    ap.add_argument("--last", type=int, nargs="?", const=1, default=None,
                    help="최근 N건 (기본 1)")
    ap.add_argument("--prompt", action="store_true", help="합성 프롬프트 원문까지")
    ap.add_argument("--split", "-s", action="store_true",
                    help="단별 로그 — 각 단이 데려온 구역을 붙여 편다")
    ap.add_argument("--index", action="store_true",
                    help="질의 목록 + 발동한 단 (예시 고르기)")
    ap.add_argument("--stage", default="", help="--index 와 함께: 그 단이 발동한 질의만")
    ap.add_argument("--limit", type=int, default=4, help="단마다 보일 구역 수 (기본 4)")
    ap.add_argument("--calls", action="store_true",
                    help="모든 LLM 콜의 system·user·응답 원문 (--split 과 함께)")
    ap.add_argument("--raw", action="store_true",
                    help="기록 원본 그대로 (jsonl 한 줄을 들여쓴 JSON 으로)")
    args = ap.parse_args()

    rows = list(_records())
    if not rows:
        print("질의 기록이 없습니다 —", tuples_dir(), file=sys.stderr)
        return 2
    if args.index:
        render_index(rows, args.stage)
        return 0
    if args.qid:
        picked = [r for r in rows if r.get("qid") == args.qid][-1:]
        if not picked:
            print(f"qid {args.qid} 없음", file=sys.stderr)
            return 2
    else:
        picked = rows[-(args.last or 1):]
    for r in picked:
        if args.raw:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif args.split:
            render_split(r, limit=args.limit, show_prompt=args.prompt,
                         show_calls=args.calls)
        else:
            render(r, show_prompt=args.prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
