"""법령해석 위키 grounding·생애 검사 — 위키의 발이 raw 를 딛고 있는지.

    python scripts/expc_wiki_check.py

llm-wiki 의 check_evidence(기계 보고, 수정 없음)를 이 위키에 이식한 자리다.
위키는 손실 압축본이라 주장 자체는 사람/LLM 이 다시 읽어야 하지만,
**인용의 좌표와 구체 수치**는 기계로 검증된다. 검사 항목:

1. 본문의 #case/<일련번호> 링크가 색인(data/expc/index.json)에 실재하는가
2. [안건번호](#case/일련번호) 짝이 그 사례의 실제 안건번호와 일치하는가
3. Raw 필드의 상대 링크(../../raw/…)가 실재 파일에 닿는가
4. index.md 표와 아티클 파일이 서로 맞는가 (파일만 있고 목록에 없음 / 반대)
5. 충실도(fidelity) — 본문의 조문 표기(제N조…)·구체 수치(N%·N억…)가
   그 아티클의 Raw 파일 어딘가에 원문 그대로 있는가. 의심만 보고한다 —
   파생값·의도적 축약이 섞이므로 판정은 읽는 사람 몫이다 (check_evidence 규율).
6. 미참조 raw 재고 — 어느 아티클의 Raw 도 가리키지 않는 raw 파일.
   컴파일 밀린 소스의 백로그다 (중복 등재 쌍둥이는 여기 남는 게 정상).

수정은 하지 않는다 — 어긋남을 보고할 뿐이다 (관측을 고쳐 쓰지 않는다).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
WIKI_ROOT = REPO_ROOT / "01_DATA" / "wiki"
WIKI = WIKI_ROOT / "wiki"
RAW = WIKI_ROOT / "raw"
INDEX = REPO_ROOT / "01_DATA" / "expc" / "index.json"

CASE_LINK = re.compile(r"\[([^\]]+)\]\(#case/(\d+)\)")
RAW_LINK = re.compile(r"\[[^\]]*\]\((\.\./[^)]+\.md)\)")
INDEX_ROW = re.compile(r"^\|\s*\[[^\]]+\]\(([^)]+\.md)\)\s*\|", re.M)
CASE_NO = re.compile(r"^\d{2}-\d{4}$")
# 충실도 후보 — 닫힌 집합(check_evidence 규율: 새 형태는 목록에 늘린다):
# 조문 표기(제N조의N·제N항·제N호 연쇄)와 구체 수치(퍼센트·금액 단위).
ARTICLE_TOKEN = re.compile(r"제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?")
NUMBER_TOKEN = re.compile(r"\d[\d,.]*\s*(?:%|억\s*원|만\s*원|억|원)")
META_LINE = re.compile(r"^>\s")


def main() -> int:
    if not INDEX.is_file():
        print("색인이 없습니다 — lawrag/pipeline/ingest_expc.py 먼저", file=sys.stderr)
        return 2
    cases = {c["serial"]: c for c in json.loads(INDEX.read_text("utf-8"))["cases"]}
    problems: list[str] = []

    articles = [p for p in sorted(WIKI.glob("*/*.md"))]
    cited: set[str] = set()
    referenced_raws: set[Path] = set()
    suspects: list[str] = []
    n_links = n_raw = 0
    for p in articles:
        text = p.read_text("utf-8")
        rel = p.relative_to(WIKI)
        for label, serial in CASE_LINK.findall(text):
            n_links += 1
            cited.add(serial)
            c = cases.get(serial)
            if not c:
                problems.append(f"{rel}: #case/{serial} ({label}) — 색인에 없음")
            elif CASE_NO.fullmatch(label.strip()) and label.strip() != c["case_no"]:
                problems.append(f"{rel}: [{label}](#case/{serial}) — "
                                f"실제 안건번호는 {c['case_no']}")
        raw_texts: list[str] = []
        for href in RAW_LINK.findall(text):
            n_raw += 1
            target = (p.parent / href).resolve()
            if not target.is_file():
                problems.append(f"{rel}: Raw 링크 끊김 — {href}")
                continue
            referenced_raws.add(target)
            raw_texts.append(target.read_text("utf-8"))

        # 5) 충실도 — 본문(메타·표 제외)의 조문 표기·수치가 Raw 어딘가에 있는가.
        evidence = re.sub(r"\s+", "", "\n".join(raw_texts))
        body = "\n".join(line for line in text.splitlines()
                         if not META_LINE.match(line))
        for tok in sorted({*ARTICLE_TOKEN.findall(body),
                           *NUMBER_TOKEN.findall(body)}):
            if re.sub(r"\s+", "", tok) not in evidence:
                suspects.append(f"{rel}: '{tok}' — Raw 원문에서 못 찾음")

    idx_file = WIKI / "index.md"
    listed = set(INDEX_ROW.findall(idx_file.read_text("utf-8"))) \
        if idx_file.is_file() else set()
    have = {str(p.relative_to(WIKI)) for p in articles}
    for name in sorted(have - listed):
        problems.append(f"index.md: {name} — 파일은 있는데 표에 없음")
    for name in sorted(listed - have):
        problems.append(f"index.md: {name} — 표엔 있는데 파일이 없음")

    # 6) 미참조 raw 재고 — 컴파일 밀린 소스의 백로그 (수정 아님, 알림이다).
    #    소스가 커져서 주제별 요약으로 보인다 — 전량 나열은 신호를 묻는다.
    all_raws = {p.resolve() for p in RAW.glob("*/*.md")} if RAW.is_dir() else set()
    orphans = sorted(p.relative_to(WIKI_ROOT) for p in all_raws - referenced_raws)
    by_topic: dict[str, list] = {}
    for p in orphans:
        by_topic.setdefault(p.parts[1], []).append(p.name)

    print(f"아티클 {len(articles)}편 · 사례 링크 {n_links}개 · Raw 링크 {n_raw}개"
          f" · 서로 다른 사례 {len(cited)}건 / 색인 {len(cases)}건")
    if suspects:
        print(f"\n충실도 의심 {len(suspects)}건 — 판정은 사람 몫 (파생값일 수 있다):")
        for line in suspects:
            print(f"  ?? {line}")
    if orphans:
        print(f"\n미참조 raw {len(orphans)}건 — 컴파일 백로그:")
        for topic, files in sorted(by_topic.items()):
            head = " · ".join(files[:3]) + (" …" if len(files) > 3 else "")
            print(f"  .. {topic}/ {len(files)}건 — {head}")
    if problems:
        print(f"\n어긋남 {len(problems)}건:")
        for line in problems:
            print(f"  !! {line}")
        return 1
    print("\ngrounding 정상 — 모든 인용이 색인과 raw 에 닿는다"
          + (f" (충실도 의심 {len(suspects)}건은 위에)" if suspects else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
