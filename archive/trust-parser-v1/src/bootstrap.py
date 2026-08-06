"""온톨로지 부트스트랩 — VLM 1차 스캔으로 초안을 만들고 수정을 제안한다.

## 왜 필요한가

새 문서 종류를 붙일 때 사용자가 `fields`(14개 × 5키), `parts`, `aliases` 를 손으로 쓰는 건
부담이 크다. 그런데 그 정보는 **대부분 문서에 이미 인쇄되어 있다** —
별지 표의 라벨, 값 자리표시자(`금 ___ 원정`), 우측 `계약서제N조` 열.

## 왜 VLM 인가 (텍스트만으로 안 되는 이유 — 실측)

별지는 병합 셀·체크박스 그리드라 텍스트 추출이 구조를 잃는다. ss2207 에서 실제로:
  · `기본보수` 의 값 자리에 옆 칸 주석("※ 수령처 우편인 경우라도…")이 붙었다
  · 필드명 하나가 `[ ] 해지 신탁금의 ( )% × …` 라는 값 문장으로 잡혔다
  · 운용방법 1~24 가 24개 조각으로 흩어졌다
페이지를 **이미지로 보면** 이 배치가 그대로 보인다. 그래서 텍스트와 이미지를 함께 준다.

## 무엇을 하지 않는가

**자동 적용하지 않는다.** 초안 YAML 을 내고 기존 온톨로지와의 차이를 보여줄 뿐,
사람이 검토해 반영한다. 온톨로지는 도메인 지식의 단일 출처이고,
그 출처를 기계가 조용히 바꾸면 안 된다(§C5 "사람이 확정").
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import yaml

VALUE_TYPES = ["number", "percent", "date", "date_range", "duration",
               "account_no", "option_set", "range_tiers", "text"]

SYSTEM = """당신은 한국 금융 계약서의 **별지(입력 양식) 페이지**를 보고,
정합성 검증에 쓸 필드 정의 초안을 만드는 도구다.

입력
- images: 별지 페이지 이미지 (표 배치·병합 셀·체크박스가 보인다)
- text: 같은 페이지에서 뽑은 텍스트 (순서가 흐트러져 있을 수 있다)
- value_types: 허용된 값 유형. **이 밖의 값을 만들지 마라.**
- known_fields: 이미 온톨로지에 있는 필드명 (있으면 중복 제안하지 마라)

무엇을 뽑는가
1. **파트 마커** — 이 페이지가 어느 별지인지 알려주는 제목. 예 `[별지1]`, `[별표2] 운용지시서`
2. **필드** — 사용자가 값을 채우는 칸마다 하나씩
   - name        표에 인쇄된 라벨 그대로 (예: "신탁금액", "중도해지수수료")
   - value_type  그 칸에 들어갈 값의 성격. **자리표시자를 보고 판단한다**
                 `금 ___ 원정 (₩ ___)`            → number
                 `20 년 월 일부터 20 년 월 일까지`  → date_range
                 `( )%`, `연 ( )%`                → percent
                 `[ ] A  [ ] B` 선택지 여러 개      → option_set
                 구간별 요율이 여러 줄              → range_tiers
                 계좌번호                          → account_no
                 그 외 서술                        → text
   - article     같은 행 오른쪽에 `계약서제N조` 가 있으면 그 값 (예: "제2조"). 없으면 null
   - template    값 자리표시자 원문 (사람이 검증할 근거)
   - aliases     이 필드를 요약서가 다르게 부를 만한 이름 추측 (2~4개)

주의
- **라벨과 값을 헷갈리지 마라.** `[ ] 해지 신탁금의 ( )% × …` 는 필드명이 아니라 값 선택지다.
  그 행의 라벨은 왼쪽 칸에 있다(예: "중도해지수수료").
- 옆 칸 주석(`※ …`)을 값 자리표시자로 착각하지 마라.
- 서명란·안내문·페이지 번호는 필드가 아니다.
- 확신이 없으면 confidence 를 낮춰라. 억지로 만들지 마라.

출력은 아래 JSON 객체 하나만. 코드펜스나 설명 문장을 붙이지 않는다.

{
  "part_marker": {"text": "[별지1]", "appendix_no": 1, "confidence": 0.9},
  "fields": [
    {"name": "신탁금액", "value_type": "number", "article": "제2조",
     "template": "금 ___ 원정 (₩ ___)", "aliases": ["<이 필드의 다른 이름들>"],
     "confidence": 0.95}
  ],
  "notes": ["사람이 확인해야 할 점"]
}"""


def render_pages(pdf_path: str | Path, pages: list[int], dpi: int = 140) -> list[bytes]:
    """지정 페이지를 PNG 로 렌더한다 (1-based)."""
    import fitz

    doc = fitz.open(str(pdf_path))
    out = []
    for pno in pages:
        if not (1 <= pno <= doc.page_count):
            continue
        pix = doc[pno - 1].get_pixmap(dpi=dpi)
        out.append(pix.tobytes("png"))
    doc.close()
    return out


def find_appendix_pages(parsed) -> list[int]:
    """별지가 시작되는 페이지를 찾는다. 못 찾으면 표가 있는 페이지로 대체."""
    import recognizers as rec

    pages = []
    for e in parsed.elements:
        if e.kind == "table" and e.page not in pages:
            pages.append(e.page)
        m = rec.appendix_marker(e.content()) if e.kind != "table" else None
        if m and len(rec.normalize_ws(e.content())) <= 40 and e.page not in pages:
            pages.append(e.page)
    return sorted(pages)


def scan(pdf_path: str | Path, parsed, llm, onto=None,
         max_pages: int = 3) -> tuple[dict, list[str]]:
    """VLM 1차 스캔 → 필드 초안. (제안, 경고)"""
    pages = find_appendix_pages(parsed)[:max_pages]
    if not pages:
        return {}, ["별지로 보이는 페이지를 찾지 못했습니다"]

    images = render_pages(pdf_path, pages)
    text = "\n".join(e.content() for e in parsed.elements
                     if e.page in pages)[:6000]
    known = list(onto.fields) if onto else []

    content: list[dict] = []
    for img in images:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.b64encode(img).decode()}})
    content.append({"type": "text", "content": ""} if False else {
        "type": "text",
        "text": json.dumps({"value_types": VALUE_TYPES, "known_fields": known,
                            "pages": pages, "text": text},
                           ensure_ascii=False, indent=2)})

    res = llm.call_multimodal("bootstrap_ontology", SYSTEM, content, max_tokens=8192)
    if not res:
        return {}, ["VLM 응답을 파싱하지 못했습니다 — llm_log 를 확인하세요"]

    warnings = []
    fields = []
    for f in res.get("fields") or []:
        vt = f.get("value_type")
        if vt not in VALUE_TYPES:
            warnings.append(f"{f.get('name')}: 허용 밖 value_type '{vt}' — 버림")
            continue
        if not f.get("name"):
            continue
        fields.append(f)
    res["fields"] = fields
    res["scanned_pages"] = pages
    return res, warnings


def to_yaml(proposal: dict, onto=None) -> str:
    """온톨로지에 붙여 넣을 초안. 기존과 겹치는 것은 표시만 한다."""
    known = set(onto.fields) if onto else set()
    lines = [
        "# VLM 부트스트랩 초안 — 검토 후 ontology/*.yaml 에 반영하세요.",
        "# 자동 적용되지 않습니다 (§C5: 사람이 확정).",
        f"# 스캔한 페이지: {proposal.get('scanned_pages')}",
        "",
    ]
    pm = proposal.get("part_marker")
    if pm:
        lines += ["# 파트 마커 제안",
                  "parts:",
                  "  - { role: 약관본문,   default: true }",
                  f"  - {{ role: 별지1_입력, starts_at: \"{pm.get('text')}\", "
                  f"appendix_no: {pm.get('appendix_no', 1)} }}   "
                  f"# confidence {pm.get('confidence', 0)}",
                  ""]
    lines.append("fields:")
    for f in sorted(proposal.get("fields", []), key=lambda x: -x.get("confidence", 0)):
        dup = "   # 이미 온톨로지에 있음" if f["name"] in known else ""
        lines += [
            f"  {f['name']}:{dup}",
            f"    value_type: {f['value_type']}",
        ]
        if f.get("article"):
            lines.append(f"    article: {f['article']}")
        lines.append("    source_of_truth: 별지1_입력")
        lines.append(f"    equals: 요약서.{f['name']}")
        al = f.get("aliases") or []
        lines.append(f"    aliases: [{', '.join(al)}]")
        if f.get("template"):
            lines.append(f"    # 근거 자리표시자: {str(f['template'])[:70]}")
        lines.append(f"    # confidence: {f.get('confidence', 0)}")
    for n in proposal.get("notes") or []:
        lines.append(f"# 확인 필요: {n}")
    return "\n".join(lines)


def diff_against(proposal: dict, onto) -> dict:
    """기존 온톨로지와의 차이 — 무엇이 새로 제안됐고 무엇이 빠졌는지."""
    proposed = {f["name"]: f for f in proposal.get("fields", [])}
    known = set(onto.fields)
    new = sorted(set(proposed) - known)
    missing = sorted(known - set(proposed))
    changed = []
    for name in sorted(set(proposed) & known):
        cur = onto.fields[name]
        p = proposed[name]
        if p["value_type"] != cur.value_type:
            changed.append(f"{name}: value_type {cur.value_type} → {p['value_type']}")
        if p.get("article") and cur.article and p["article"] != cur.article:
            changed.append(f"{name}: article {cur.article} → {p['article']}")
    return {"new_fields": new, "not_seen": missing, "changed": changed}
