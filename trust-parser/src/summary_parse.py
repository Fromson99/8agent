"""T9. 요약서 파서 — Part A 의 파싱 스택을 재사용한다 (SPEC §B10 T9).

요약서는 "어느 정도 고정된 표/양식"이다(§B2). 값 추출은 규칙 기반 우선이고,
레이아웃이 흔들리는 부분만 LLM 보조를 붙일 자리를 남겨 둔다(현재 미사용).

출력은 `{label, value, page}` 목록이며, 이걸 fact.from_summary 가 Fact 로 만든다.
value_type 은 여기서 정하지 않는다 — 매핑이 끝나야 온톨로지에서 가져올 수 있다.
"""
from __future__ import annotations

from pathlib import Path

import recognizers as rec


def _from_markdown(path: Path) -> list[dict]:
    """`| 라벨 | 값 |` 파이프 표 + `**라벨** 값` 형태를 읽는다."""
    out: list[dict] = []
    bucket: dict[str, list[str]] = {}
    section = ""
    for line in path.read_text(encoding="utf-8").split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            section = s.lstrip("# ").strip()
            continue
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s[1:-1].split("|")]
            if len(cells) < 2:
                continue
            if all(set(c) <= set("-: ") for c in cells if c):
                continue                      # 구분선
            label, value = cells[0], " ".join(cells[1:]).strip()
            if not label or label in ("항목", "구분"):
                continue
            out.append({"label": label, "value": value, "page": 1, "section": section})
            if section:
                # 섹션 제목이 곧 필드명인 표(예: '### 중도해지수수료' 아래 구간별 요율)
                bucket.setdefault(section, []).append(f"{label} {value}")
        elif s.startswith("**") and "**" in s[2:]:
            end = s.index("**", 2)
            label = s[2:end].strip()
            value = s[end + 2:].strip()
            if label and value:
                out.append({"label": label, "value": value, "page": 1, "section": section})
    for name, rows in bucket.items():
        out.append({"label": name, "value": "\n".join(rows), "page": 1, "section": name})
    return out


def _from_pdf(path: Path) -> list[dict]:
    """PDF 요약서 — Part A 파싱 스택 재사용. 표는 행 단위, 그 외는 라벨:값 줄."""
    import parse_stage

    parsed = parse_stage.parse(path)
    out: list[dict] = []
    for e in parsed.elements:
        if e.furniture:
            continue
        if e.kind == "table" and e.table:
            for row in e.table:
                cells = [rec.normalize_ws(c) for c in row if rec.normalize_ws(c)]
                # 병합 셀 가로 복제 접기 (실측: 도클링이 값을 여러 열에 반복)
                folded: list[str] = []
                for c in cells:
                    if c not in folded:
                        folded.append(c)
                if len(folded) < 2:
                    continue
                out.append({"label": folded[0], "value": " ".join(folded[1:]),
                            "page": e.page, "bbox": e.bbox})
            continue
        line = rec.normalize_ws(e.content())
        if not line or ":" not in line:
            continue
        label, _, value = line.partition(":")
        if label.strip() and value.strip():
            out.append({"label": label.strip(), "value": value.strip(),
                        "page": e.page, "bbox": e.bbox})
    return out


def parse(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"요약서를 찾을 수 없습니다: {p}")
    if p.suffix.lower() in (".md", ".markdown", ".txt"):
        return _from_markdown(p)
    if p.suffix.lower() == ".pdf":
        return _from_pdf(p)
    raise ValueError(f"지원하지 않는 요약서 형식입니다: {p.suffix}")
