"""T-A6.8 harvest — 큐 해소 결과를 few_shot 으로 되돌린다 (AGENT6 §6 수렴 루프).

UNCLEAR 는 없애는 것이 아니라 **줄이는** 것이다. 줄이는 유일한 길은 사람이 해소한
경계 사례를 항목 스펙으로 되먹이는 것이고, 이 파일이 그 마지막 한 걸음이다.

    review_queue.jsonl  +  resolved.jsonl   →   checklist/items/{id}.yaml 의 few_shot

## YAML 을 pyyaml 로 다시 쓰지 않는 이유

`yaml.safe_load` → `yaml.safe_dump` 로 왕복시키면 **주석이 전부 사라지고 키 순서가
바뀐다.** 항목 스펙의 주석은 장식이 아니라 "이 when 을 왜 이렇게 옮겼는가" 같은 번역
근거이고(§4), 그것이 사라지면 다음 사람이 같은 판단을 다시 할 수 없다. 그래서 이
파일은 YAML 을 **텍스트로** 다루어 few_shot 블록에만 줄을 끼워 넣는다.

쓰고 나서는 반드시 `schema.load_item` 으로 다시 읽어 검증하고, 깨졌으면 원문을
되돌린다. 스펙 파일을 망가뜨리면 다음 실행에서 **로드 전체가 실패한다**(schema.py 의
설계) — 그 편이 조용히 27개만 로드되는 것보다 낫지만, 애초에 망가뜨리지 않는 게 낫다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from lawrag.agents.agent6.src import schema
from lawrag.agents.agent6.src.preprocess import ITEMS_DIR, Normalizer

# 해소 결과에서 발화문을 찾을 때 보는 키들. STT·큐 도구마다 이름이 다르다.
UTTERANCE_KEYS = ("utterance", "text", "quote", "발화")
VERDICT_KEYS = ("resolved_verdict", "verdict", "판정")
REASON_KEYS = ("resolved_reason", "reason", "사유")


class HarvestError(ValueError):
    """재적재 실패. 스펙 파일을 반쯤 고친 채로 두지 않는다."""


@dataclass
class Resolution:
    """사람이 해소한 한 건 — 어떤 항목의 어떤 발화가 무엇으로 판정됐는가."""
    item_id: str
    utterance: str
    verdict: str
    reason: str
    source: str = ""
    resolver: str = ""

    def to_few_shot(self) -> schema.FewShot:
        return schema.FewShot(utterance=self.utterance, verdict=self.verdict,
                              reason=self.reason or "사람 해소",
                              source=self.source or None)


@dataclass
class HarvestResult:
    added: dict[str, list[str]] = field(default_factory=dict)      # item_id → 추가된 발화
    skipped: dict[str, list[str]] = field(default_factory=dict)    # 중복·거부
    warnings: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def total_added(self) -> int:
        return sum(len(v) for v in self.added.values())

    def to_text(self) -> str:
        lines = [f"few_shot 재적재 — 추가 {self.total_added()}건 / "
                 f"건너뜀 {sum(len(v) for v in self.skipped.values())}건"]
        for item_id in sorted(self.added):
            for u in self.added[item_id]:
                lines.append(f"  + {item_id}  \"{u[:60]}\"")
        for item_id in sorted(self.skipped):
            for u in self.skipped[item_id]:
                lines.append(f"  = {item_id}  {u}")
        lines += [f"  ! {w}" for w in self.warnings]
        return "\n".join(lines)


# ===========================================================================
# 입력 읽기
# ===========================================================================

def _read_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise HarvestError(f"파일을 찾을 수 없습니다: {p}")
    rows: list[dict] = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarvestError(f"{p}:{n} JSON 을 읽을 수 없습니다 — {exc}") from exc
        if not isinstance(row, dict):
            raise HarvestError(f"{p}:{n} 각 줄은 객체여야 합니다 (받은 형태: {type(row).__name__})")
        rows.append(row)
    return rows


def _pick(row: dict, keys: Sequence[str]) -> Optional[str]:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _queue_key(row: dict) -> tuple[str, str]:
    return (str(row.get("item_id") or ""), str(row.get("created_at") or ""))


def collect(queue_path: str | Path, resolved_path: str | Path) -> tuple[list[Resolution], list[str]]:
    """큐와 해소 결과를 맞춰 Resolution 목록을 만든다.

    해소 파일에 발화문이 직접 있으면 그것을 쓰고, 없으면 큐의 인용에서 가져온다.
    (사람은 보통 큐 줄을 복사해 `resolved_verdict` 만 채워 돌려준다.)
    """
    queue = {_queue_key(r): r for r in _read_jsonl(queue_path)}
    by_item: dict[str, list[dict]] = {}
    for r in queue.values():
        by_item.setdefault(str(r.get("item_id") or ""), []).append(r)

    out: list[Resolution] = []
    warns: list[str] = []
    for row in _read_jsonl(resolved_path):
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            warns.append(f"item_id 가 없는 해소 결과를 건너뜁니다: {json.dumps(row, ensure_ascii=False)[:80]}")
            continue
        verdict = _pick(row, VERDICT_KEYS)
        if verdict not in ("PASS", "FAIL", "UNCLEAR"):
            warns.append(f"{item_id}: 해소 판정이 없거나 알 수 없습니다({verdict!r}) — 건너뜁니다")
            continue
        if verdict == "UNCLEAR":
            # 사람도 UNCLEAR 라고 한 것은 few_shot 이 될 수 없다 — 가르칠 답이 없다.
            warns.append(f"{item_id}: 해소 결과가 UNCLEAR 라 few_shot 으로 만들지 않습니다")
            continue

        utterance = _pick(row, UTTERANCE_KEYS)
        if not utterance:
            src = queue.get(_queue_key(row)) or next(iter(by_item.get(item_id, [])), None)
            evidence = (src or {}).get("evidence") or []
            if evidence and isinstance(evidence[0], dict):
                utterance = str(evidence[0].get("text") or "").strip()
        if not utterance:
            warns.append(f"{item_id}: 인용 발화를 찾지 못해 few_shot 을 만들 수 없습니다")
            continue

        out.append(Resolution(
            item_id=item_id, utterance=utterance, verdict=verdict,
            reason=_pick(row, REASON_KEYS) or "사람 해소",
            source=str(row.get("source") or f"queue/{row.get('created_at') or ''}").strip("/ "),
            resolver=str(row.get("resolver") or "")))
    return out, warns


# ===========================================================================
# YAML 삽입 — 텍스트로 다룬다 (모듈 설명 참조)
# ===========================================================================

def _scalar(value: str) -> str:
    """YAML 큰따옴표 스칼라. JSON 문자열은 그대로 유효한 YAML 스칼라다."""
    return json.dumps(value, ensure_ascii=False)


def _entry_line(fs: schema.FewShot, indent: str = "  ") -> str:
    parts = [f"utterance: {_scalar(fs.utterance)}",
             f"verdict: {fs.verdict}",
             f"reason: {_scalar(fs.reason)}"]
    if fs.source:
        parts.append(f"source: {_scalar(fs.source)}")
    return f"{indent}- {{ {', '.join(parts)} }}"


def _block_end(lines: list[str], start: int) -> int:
    """`few_shot:` 블록의 끝(다음 최상위 키의 줄 번호)을 찾는다."""
    i = start + 1
    last = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() and not line[:1].isspace():
            break                       # 최상위 키 — 블록이 끝났다
        if line.strip() and not line.lstrip().startswith("#"):
            last = i + 1                # 주석·빈 줄은 블록 끝에 남긴다(원문 보존)
        i += 1
    return last


def insert_few_shots(path: str | Path, additions: Sequence[schema.FewShot],
                     *, normalizer: Optional[Normalizer] = None
                     ) -> tuple[list[str], list[str]]:
    """항목 YAML 의 few_shot 에 줄을 끼워 넣는다. 반환: (추가된 발화, 건너뛴 사유)."""
    p = Path(path)
    original = p.read_text(encoding="utf-8")
    item = schema.load_item(p)
    if item.derived is not None:
        return [], [f"{item.id}: 파생 항목에는 few_shot 을 넣지 않습니다(독립 판정을 하지 않습니다)"]

    norm = normalizer or Normalizer(prefer_morph=False)
    seen = {norm.normalize(fs.utterance).text for fs in item.few_shot}

    fresh: list[schema.FewShot] = []
    skipped: list[str] = []
    for fs in additions:
        key = norm.normalize(fs.utterance).text
        if not key:
            skipped.append(f"{item.id}: 빈 발화")
            continue
        if key in seen:
            skipped.append(f"{item.id}: 이미 있는 예시 \"{fs.utterance[:40]}\"")
            continue
        seen.add(key)
        fresh.append(fs)
    if not fresh:
        return [], skipped

    lines = original.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.rstrip() == "few_shot:"), None)
    if idx is None:
        # few_shot 블록이 없다 — judgment_hints 앞에 새로 연다(스펙의 키 순서를 따른다).
        anchor = next((i for i, l in enumerate(lines) if l.startswith("judgment_hints:")),
                      len(lines))
        block = ["few_shot:"] + [_entry_line(fs) for fs in fresh]
        lines[anchor:anchor] = block
    else:
        at = _block_end(lines, idx)
        lines[at:at] = [_entry_line(fs) for fs in fresh]

    updated = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
    p.write_text(updated, encoding="utf-8")
    try:
        reloaded = schema.load_item(p)
        if len(reloaded.few_shot) != len(item.few_shot) + len(fresh):
            raise HarvestError(
                f"{item.id}: few_shot 이 {len(item.few_shot)}→{len(reloaded.few_shot)} 로 "
                f"기대({len(item.few_shot) + len(fresh)})와 다릅니다")
    except Exception as exc:
        p.write_text(original, encoding="utf-8")          # 원문 복구 — 반쯤 고친 채 두지 않는다
        raise HarvestError(f"{p}: few_shot 삽입 후 스펙이 깨져 되돌렸습니다 — {exc}") from exc
    return [fs.utterance for fs in fresh], skipped


# ===========================================================================
# 진입점
# ===========================================================================

def run(queue_path: str | Path, resolved_path: str | Path, *,
        items_dir: str | Path = ITEMS_DIR, dry_run: bool = False) -> HarvestResult:
    """§8 harvest CLI 의 본체."""
    resolutions, warns = collect(queue_path, resolved_path)
    result = HarvestResult(warnings=list(warns))

    d = Path(items_dir)
    grouped: dict[str, list[schema.FewShot]] = {}
    for r in resolutions:
        p = d / f"{r.item_id}.yaml"
        if not p.exists():
            result.warnings.append(f"{r.item_id}: 항목 스펙 파일이 없습니다 ({p})")
            continue
        try:
            grouped.setdefault(r.item_id, []).append(r.to_few_shot())
        except Exception as exc:                          # pydantic 검증 실패
            result.warnings.append(f"{r.item_id}: few_shot 을 만들지 못했습니다 — {exc}")

    for item_id in sorted(grouped):
        p = d / f"{item_id}.yaml"
        if dry_run:
            result.added[item_id] = [fs.utterance for fs in grouped[item_id]]
            continue
        added, skipped = insert_few_shots(p, grouped[item_id])
        if added:
            result.added[item_id] = added
            result.files.append(str(p))
        if skipped:
            result.skipped[item_id] = skipped
    return result
