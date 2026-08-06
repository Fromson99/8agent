"""section 으로 범위를 좁혀 **증거 표**를 만든다 (결정론).

## 왜 범위를 좁히는가

세부 규칙으로 값 하나를 정확히 집어내려 들면 문서마다 규칙이 늘어난다. 대신
**section 좌표로 범위를 먼저 좁히고**, 그 안의 값들을 표로 정리해 판단에 넘긴다.
"총 보수"는 설명서에 여러 번 나오지만 `제2부/13. 보수 및 수수료에 관한 사항` 안에서는
후보가 손에 꼽는다 — 좁히는 일은 좌표가, 고르는 일은 판단이 한다.

## 증거 ID 가 핵심이다

표의 모든 행에 `e-001` 같은 ID 를 붙여 넘긴다. 판단자는 **그 ID 로만** 근거를 가리킬 수
있고, 우리는 ID 를 실제 출처(page/bbox/cell)로 되돌린다. 판단자가 페이지 번호나 문구를
지어내도 리포트에는 들어갈 수 없다 — 출처의 신뢰는 판단자가 아니라 이 대응표가 만든다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.glossary import Glossary, normalize          # noqa: E402
from core.parse_adapter import Cell                    # noqa: E402
from core.structurize import Document, Section         # noqa: E402

MAX_ROWS = 80              # 한 범위에서 판단자에게 넘길 최대 행 수
MAX_CELL_CHARS = 90


@dataclass
class Evidence:
    """증거 한 줄 — 판단자가 ID 로 가리키고, 우리가 출처로 되돌린다."""
    ev_id: str
    section_id: str
    page: int
    kind: str                       # text | table_row
    text: str
    bbox: Optional[list[float]] = None
    cell: Optional[list[int]] = None
    header: Optional[str] = None    # 표 행이면 그 표의 헤더 줄

    def source(self) -> dict:
        d = {"section_id": self.section_id, "page": self.page, "kind": self.kind}
        if self.bbox:
            d["bbox"] = self.bbox
        if self.cell:
            d["cell"] = self.cell
        return d

    def dump(self) -> dict:
        return {"ev_id": self.ev_id, **self.source(), "text": self.text,
                **({"header": self.header} if self.header else {})}


@dataclass
class Scope:
    """좁혀진 범위 하나 — 어느 문서의 어느 구역을 봤고 무엇이 있었는가."""
    doc_label: str
    section_paths: list[str]
    matched_sections: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    truncated: int = 0              # 상한을 넘어 잘라낸 행 수

    def by_id(self) -> dict[str, Evidence]:
        return {e.ev_id: e for e in self.evidence}

    def dump(self) -> dict:
        return {"doc": self.doc_label, "section_paths": self.section_paths,
                "matched_sections": self.matched_sections,
                "evidence": [e.dump() for e in self.evidence],
                "truncated": self.truncated}


# ---------------------------------------------------------------------------

def _matches(section_id: str, wanted: str) -> bool:
    """완전 일치 또는 **접두 일치**(하위 구역 포함) 또는 경로 성분 일치."""
    if section_id == wanted or section_id.startswith(wanted + "/"):
        return True
    return wanted in section_id.split("/")


def _rebuild_rows(cells_dump: dict) -> list[list[Cell]]:
    cells = [Cell(**c) for c in cells_dump.get("cells", [])]
    rows: list[list[Cell]] = [[] for _ in range(cells_dump.get("n_rows", 0))]
    for c in cells:
        if 0 <= c.row < len(rows):
            rows[c.row].append(c)
    for r in rows:
        r.sort(key=lambda c: c.col)
    return rows


def _header_line(rows: list[list[Cell]]) -> str:
    """헤더 줄 — 첫 데이터 행 이전의 비수치 행들을 이어 붙인다.

    병합 2단 헤더(`클래스종류 | 지급비율(연간,%)` + `… | 총 보수 | …`)를
    forward-fill 로 복원할 필요가 없다. docling 이 논리 셀 + span 을 주므로
    부모 라벨이 이미 한 셀로 있고, 자식 행이 열 이름을 준다 — 둘을 이어 붙이면 된다.
    """
    out = []
    for row in rows[:2]:
        texts = [c.text for c in row if c.text]
        if not texts:
            continue
        numeric = sum(1 for t in texts if t.replace(".", "").replace("-", "").isdigit())
        if numeric > len(texts) / 2:
            break                     # 숫자 행 = 데이터 시작
        out.append(" | ".join(t[:MAX_CELL_CHARS] for t in texts))
    return "  /  ".join(out)


def _is_layout_box(rows: list[list[Cell]], n_cols: int,
                   empty_ratio: float = 0.70, max_cols: int = 15) -> bool:
    """표가 아니라 레이아웃 박스인가 (AGENT1_SPEC §4-2단).

    빈 셀 비율이 높거나 열이 비정상으로 많으면 표 구조가 아니라 배치용 격자다.
    이런 격자에서 행×열 앵커를 잡으면 엉뚱한 셀이 나온다 — 표 취급을 포기하고
    셀 텍스트를 이어 붙여 한 줄로 강등한다.
    """
    total = sum(len(r) for r in rows)
    if not total:
        return True
    filled = sum(1 for r in rows for c in r if c.text.strip())
    grid = max(1, len(rows) * max(1, n_cols))
    return (1 - filled / grid) > empty_ratio or n_cols > max_cols


def build(doc: Document, doc_label: str, section_paths: list[str],
          terms: Optional[list[str]] = None,
          glossary: Optional[Glossary] = None,
          max_rows: int = MAX_ROWS) -> Scope:
    """지정한 구역들의 내용을 증거 표로 편다.

    terms 가 주어지면 그 용어(+aliases)가 든 행을 **우선** 담는다. 상한에 걸려도
    관련 행이 먼저 들어가게 하려는 것이고, 남는 자리는 문맥 행으로 채운다.
    """
    scope = Scope(doc_label=doc_label, section_paths=section_paths)
    surfaces: list[str] = []
    if terms and glossary:
        for t in terms:
            surfaces += [normalize(s) for s in glossary.surfaces_of(t)]
    elif terms:
        surfaces = [normalize(t) for t in terms]

    primary: list[Evidence] = []
    context: list[Evidence] = []
    seq = 0

    for sec in doc.sections:
        if not any(_matches(sec.section_id, w) for w in section_paths):
            continue
        scope.matched_sections.append(sec.section_id)

        for item in sec.content:
            page = item.get("page", 1)
            if item.get("type") == "table":
                rows = _rebuild_rows(item["cells"])
                n_cols = item["cells"].get("n_cols", 0)
                if _is_layout_box(rows, n_cols):
                    text = " ".join(c.text for r in rows for c in r if c.text).strip()
                    if not text:
                        continue
                    seq += 1
                    ev = Evidence(f"e-{seq:03d}", sec.section_id, page, "text",
                                  text[:400], bbox=_cells_bbox(
                                      [c for r in rows for c in r]))
                    (primary if _hits(text, surfaces) else context).append(ev)
                    continue

                header = _header_line(rows)
                for row in rows:
                    text = " | ".join(c.text[:MAX_CELL_CHARS] for c in row if c.text)
                    if not text.strip():
                        continue
                    seq += 1
                    first = row[0]
                    ev = Evidence(f"e-{seq:03d}", sec.section_id, page, "table_row",
                                  text, bbox=_row_bbox(row), cell=[first.row, first.col],
                                  header=header)
                    (primary if _hits(text + header, surfaces) else context).append(ev)
            else:
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                seq += 1
                ev = Evidence(f"e-{seq:03d}", sec.section_id, page, "text", text[:400],
                              bbox=item.get("bbox"))
                (primary if _hits(text, surfaces) else context).append(ev)

    chosen = primary[:max_rows]
    room = max_rows - len(chosen)
    chosen += context[:room]
    scope.truncated = (len(primary) + len(context)) - len(chosen)
    scope.evidence = sorted(chosen, key=lambda e: int(e.ev_id.split("-")[1]))
    return scope


def _cells_bbox(cells: list[Cell]) -> Optional[list[float]]:
    """여러 셀을 감싸는 사각형. 셀 bbox 는 TOPLEFT 기준이다."""
    boxes = [c.bbox for c in cells if c.bbox]
    if not boxes:
        return None
    return [round(min(b[0] for b in boxes), 2), round(min(b[1] for b in boxes), 2),
            round(max(b[2] for b in boxes), 2), round(max(b[3] for b in boxes), 2)]


def _row_bbox(row: list[Cell]) -> Optional[list[float]]:
    return _cells_bbox(row)


def _hits(text: str, surfaces: list[str]) -> bool:
    if not surfaces:
        return True
    n = normalize(text)
    return any(s and s in n for s in surfaces)


def to_table(scope: Scope) -> str:
    """판단자에게 넘길 표 — 모든 줄에 증거 ID 가 붙는다."""
    if not scope.evidence:
        return f"({scope.doc_label}: {scope.section_paths} 범위에서 내용을 찾지 못했습니다)"
    lines = [f"[{scope.doc_label}] 범위: {', '.join(scope.matched_sections) or '없음'}"]
    header_shown: set[str] = set()
    lines.append("| 증거ID | 쪽 | 위치 | 내용 |")
    lines.append("|---|---|---|---|")
    for e in scope.evidence:
        if e.header and e.header not in header_shown:
            header_shown.add(e.header)
            lines.append(f"|  | p{e.page} | 표 헤더 | {e.header} |")
        loc = "표" if e.kind == "table_row" else "본문"
        lines.append(f"| {e.ev_id} | p{e.page} | {loc} | {e.text.replace('|', '/')} |")
    if scope.truncated:
        lines.append(f"| … | | | (상한을 넘겨 {scope.truncated}행 생략) |")
    return "\n".join(lines)
