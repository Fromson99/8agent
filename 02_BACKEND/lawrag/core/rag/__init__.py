"""RAG — 구조화 산출 위의 질의응답. DB 서버 없이.

기존 RAG(DELTAFlow)의 질의 경로를 이 저장소의 결로 옮긴 것이다. 그쪽의
실제 검색은 벡터가 아니라 **결정론 키워드 검색 + 그래프 연결**이었고, 그
역할을 여기서는 파일이 대신한다 — 색인은 구조화 산출(result.json)과 용어집
(glossary.json)에서 메모리로 세우고, 좌표(doc·node·block·page)로 근거를
되짚는다.

    index.py    색인 — 마디 제목 + 사람이 더한 용어, 그리고 블록 본문
    search.py   검색 사다리 — 정확 → 부분(trigram) → 본문. 결정론.
    refs.py     조문 상호참조 — 본문의 "제4조를 참고한다" 를 구역 간선으로.
                문서 안은 전부 결정론, 문서 사이는 이름 대조가 닿는 데까지
                확정하고 나머지는 보류로 돌려준다.
    judge.py    닫힌 목록 링크 판정 — 보류된 연결의 소수만 LLM 이 고른다.
                도메인 무관(candidates 중 cid 고르기)이라 재사용된다.
    answer.py   관련성 필터 + 답변 합성 — LLM 은 여기에만 있고, 인용은
                닫힌 번호 목록으로만 한다.

판정 경로가 아니다. agent6 의 "런타임에 검색 없음" 원칙(basis.py)과 충돌하지
않도록 별도 패키지로 두었다 — 검색이 허용되는 자리는 저작·질의 화면이다.
"""

from lawrag.core.rag.index import Index, current
from lawrag.core.rag.search import SearchResult, search
from lawrag.core.rag.answer import (Answer, Section, assemble, filter_sections,
                             synthesize)

__all__ = ["Index", "current", "SearchResult", "search",
           "Answer", "Section", "assemble", "filter_sections", "synthesize"]
