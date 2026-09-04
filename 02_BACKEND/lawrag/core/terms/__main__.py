"""`python -m lawrag.core.terms <명령>` — 용어층 컴파일 CLI.

    transcribe       Tier 1 전사 (정의조항·정의술어·괄호별칭 → glossary.json)
    build            Tier 2+3 (통계 깔때기 → 임베딩 군집 → LLM 판정 → 게이트 등재)
    embed-sections   구역 벡터 색인 컴파일 (검색 벡터 단이 읽는다)
    suggest          질의 로그 특이 키워드 → 신규 용어·별칭 추천 (검수 큐 유입)
"""

from __future__ import annotations

import sys


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    from lawrag.core import logbook
    logbook.setup("terms")
    cmd, rest = args[0], args[1:]
    if cmd == "transcribe":
        from lawrag.core.terms import transcribe
        return transcribe.main(rest)
    if cmd == "build":
        from lawrag.core.terms import build
        return build.main(rest)
    if cmd == "embed-sections":
        from lawrag.core.terms import embed_sections
        return embed_sections.main(rest)
    if cmd == "suggest":
        from lawrag.core.terms import suggest
        return suggest.main(rest)
    print(f"모르는 명령입니다: {cmd}\n\n{__doc__.strip()}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
