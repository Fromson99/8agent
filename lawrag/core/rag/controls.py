"""RAG 성능 손잡이 등록부와 구조 충돌 감사.

검색 품질은 프롬프트만으로 결정되지 않는다. 후보를 몇 개 보여 주는지, 어느
점수 아래를 버리는지, 본문을 몇 자에서 자르는지가 회수율·오염·비용을 함께
바꾼다. 이 값들이 여러 모듈에 흩어지면 A/B 실행의 실제 차이를 재현할 수 없다.

이 모듈은 런타임 hot path의 자름·개수·문턱을 한 등록부로 모은다. 각 모듈은
``value(key)``를 통해 기본값을 받고, 평가 실행은 ``snapshot``과 ``fingerprint``를
결과에 박는다. ``audit``은 개별 값은 정상이어도 합류하면서 상한을 우회하는
구조적 충돌을 찾는다.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Control:
    """사람과 코드가 함께 읽는 성능 손잡이 한 개."""

    key: str
    default: int | float
    stage: str
    kind: str
    unit: str
    risk: str
    description: str
    owner: str
    env: str = ""
    diagram: bool = False


def _c(key: str, default: int | float, stage: str, kind: str, unit: str,
       risk: str, description: str, owner: str, *, env: str = "",
       diagram: bool = False) -> Control:
    return Control(key, default, stage, kind, unit, risk, description, owner,
                   env, diagram)


# 등록 순서가 스냅샷·문서 표의 순서다. 개수 제한은 ``*_max`` 또는 ``*_cap``,
# 점수 문턱은 ``*_min``으로 이름을 통일한다. 문자 표시용 자름은 제외하고 검색
# 집합·LLM 입력·최종 근거에 영향을 주는 값만 등록한다.
CONTROLS: tuple[Control, ...] = (
    _c("query_guide.mentions_max", 12, "DB 역매칭", "slice", "mentions",
       "recall/cost", "질문에 역으로 맞은 서로 다른 문자열 구간의 최대 수",
       "rag.queryguide", env="RAG_QUERY_GUIDE_MENTIONS_MAX", diagram=True),
    _c("query_guide.readings_per_mention_max", 12, "DB 역매칭", "slice",
       "readings/mention", "recall/precision/cost",
       "같은 질문 문자열에 제시하는 문서·구조·Concept·정의·본문 해석의 최대 수",
       "rag.queryguide", env="RAG_QUERY_GUIDE_READINGS_MAX", diagram=True),
    _c("query_guide.prompt_chars_max", 12000, "DB 역매칭", "chars", "chars",
       "recall/cost", "Span 분해기에 붙이는 DB 해석 후보 안내의 최대 문자 수",
       "rag.queryguide", env="RAG_QUERY_GUIDE_PROMPT_CHARS", diagram=True),
    _c("combination.lexicon_neighbors_max", 40, "지연 트리", "slice", "terms/span",
       "recall/cost", "역할 Span 하나를 같은 역할 Concept로 되돌릴 벡터 이웃 수",
       "rag.combinations", diagram=True),
    _c("combination.candidates_per_part_max", 10, "지연 트리", "slice",
       "concepts/span", "recall/precision/cost",
       "같은 질문 Span의 역할 가설을 합쳐 유지하는 Concept 가지 최대 수",
       "rag.combinations", diagram=True),
    _c("combination.surviving_states_max", 512, "지연 트리", "slice", "nodes",
       "recall/cost", "0 교집합 제거 후 깊이별로 유지하는 지연 트리 노드 최대 수",
       "rag.combinations", diagram=True),
    _c("combination.states_to_expand_max", 36, "지연 트리", "slice", "nodes",
       "recall/cost", "문서 계층의 원문 가지로 펼치는 생존 트리 노드 최대 수",
       "rag.combinations", diagram=True),
    _c("combination.coordinates_per_state_max", 3, "지연 트리", "slice",
       "sections/node", "recall/precision/cost",
       "넓은 트리 노드 좌표 안에서 Vector가 남기는 원문 구역 수",
       "rag.combinations", diagram=True),
    _c("combination.llm_options_max", 40, "지연 트리", "slice", "ranges",
       "recall/precision/cost", "최종 LLM에 보여 주는 문서 계층의 닫힌 원문 가지 수",
       "rag.combinations", diagram=True),
    _c("assertion_tree.page_size", 32, "Assertion 트리 실험", "slice", "options/call",
       "precision/cost", "한 번의 소형 LLM 닫힌 메뉴에 보여 주는 최대 가지 수",
       "rag.assertionfirst", diagram=True),
    _c("assertion_tree.family_candidates_max", 8, "Assertion 트리 실험", "slice",
       "document-families", "recall/precision/cost",
       "canonical 신호 커버리지로 결정론적으로 여는 문서군 최대 수",
       "rag.assertionfirst", diagram=True),
    _c("assertion_tree.families_max", 2, "Assertion 트리 실험", "slice", "families",
       "recall/precision/cost", "소형 LLM이 문서 단계로 여는 문서군 최대 수",
       "rag.assertionfirst", diagram=True),
    _c("assertion_tree.documents_max", 2, "Assertion 트리 실험", "slice", "documents",
       "recall/precision/cost", "문서 단계에서 실제 문서 트리로 여는 최대 가지 수",
       "rag.assertionfirst", diagram=True),
    _c("exploration.body_preview_chars_max", 360, "계층 탐색", "chars", "chars/provision",
       "recall/cost", "구조화 매칭 구간이 없을 때 선택기에 보여 주는 조·항 본문 첫머리",
       "rag.exploration", diagram=True),
    _c("exploration.match_context_chars_max", 180, "계층 탐색", "chars", "chars/match",
       "recall/cost", "ACTOR·PREDICATE 등 Concept 일치점 주변의 실제 원문 길이",
       "rag.exploration", diagram=True),
    _c("exploration.connected_ranges_max", 12, "계층 탐색", "slice", "provisions",
       "recall/precision/cost", "초기 회수 조·항의 실제 1-hop 입출력 간선으로 보충하는 가지 수",
       "rag.exploration", diagram=True),
    _c("entry.combination_sections_max", 4, "진입 합류", "count", "sections",
       "recall/precision/cost", "계층 탐색 선택기가 운영 RAG에 여는 조·항 가지 수",
       "rag.combinations", diagram=True),
    _c("landing.closed_menu_max", 24, "DB 값 착지", "slice", "objects/part",
       "recall/cost", "질문 조각의 DB 후보가 이 수 이하면 전부 닫힌 메뉴로 제시",
       "rag.landings", diagram=True),
    _c("landing.direct_sections_max", 4, "좌표 교집합", "threshold", "sections",
       "recall/precision/cost", "교집합 후보가 이 수 이하면 Vector/LLM 없이 전부 사용",
       "rag.landings", diagram=True),
    _c("landing.vector_shortlist_max", 12, "좌표 교집합", "slice", "sections",
       "recall/cost", "교집합이 넓을 때 Vector가 LLM 판정 전에 남기는 본문 후보 수",
       "rag.landings", diagram=True),
    _c("concept.query_spans_max", 12, "단서 분해", "slice", "spans",
       "recall/cost", "질문에서 유지하는 실제 문자열 단서 수", "domain_graph.spanparts",
       diagram=True),
    _c("concept.parts_per_span_max", 8, "개념 후보", "slice", "parts/span",
       "recall/precision/cost", "단서 하나에 Composer가 보는 닫힌 후보 수",
       "domain_graph.spanparts", diagram=True),
    _c("concept.raw_pool_factor", 5, "개념 후보", "multiplier", "times",
       "recall/cost", "후보 8개를 고르기 전에 벡터로 훑는 원시 풀 배수",
       "domain_graph.spanparts", diagram=True),
    _c("concept.semantic_cos_min", 0.45, "개념 후보", "threshold", "cosine",
       "recall/precision", "표준 개념 의미 후보의 최소 코사인", "domain_graph.spanparts",
       diagram=True),
    _c("concept.surface_score_min", 0.18, "개념 후보", "threshold", "score",
       "recall/precision", "스코프·벡터 근거가 없을 때 표면 후보 최소 점수",
       "domain_graph.spanparts"),
    _c("concept.predicate_surface_min", 0.50, "뜻 검문", "threshold", "score",
       "recall/precision/cost", "이보다 가까운 행위는 LLM 뜻 판별을 생략",
       "domain_graph.spanparts", diagram=True),
    _c("concept.occurrences_per_part_max", 5, "개념 후보", "slice", "occurrences/part",
       "recall/cost", "후보 카드 하나에 남기는 실제 사실 출현 수",
       "domain_graph.spanparts"),
    _c("concept.occurrence_context_chars", 260, "개념 후보", "chars", "chars",
       "recall/cost", "출현 사실 하나의 진단 문맥 길이", "domain_graph.spanparts"),
    _c("concept.prompt_context_chars", 160, "개념 조립", "chars", "chars",
       "recall/cost", "Composer에 보내는 후보 첫 문맥 길이", "domain_graph.spanparts",
       diagram=True),
    _c("concept.mappings_max", 10, "개념 조립", "slice", "mappings",
       "recall/precision", "모델 연결안에서 코드가 검증하는 최대 행 수",
       "domain_graph.spanparts"),
    _c("entry.concept_sections_max", 4, "진입 합류", "count", "sections",
       "recall/cost", "Concept/OQL 채널이 여는 근거 구역 수", "rag.conceptfirst",
       diagram=True),
    _c("entry.memory_sections_max", 4, "진입 합류", "count", "sections",
       "recall/precision/cost", "승인 질문 기억이 직행으로 여는 구역 수", "rag.promote",
       diagram=True),
    _c("entry.memory_cos_min", 0.80, "진입 합류", "threshold", "cosine",
       "recall/precision", "질문 기억 의미 일치 최소 코사인", "rag.promote",
       diagram=True),
    _c("entry.keyword_sections_max", 2, "진입 합류", "count", "sections",
       "recall/precision/cost", "승인 용어가 여는 진입 구역 수", "rag.vecfirst",
       diagram=True),
    _c("entry.frame_queries_max", 2, "프레임 진입", "slice", "frames",
       "recall/cost", "질문 하나에서 유지하는 프레임 수", "rag.framequery"),
    _c("entry.frame_picks_max", 3, "프레임 진입", "slice", "picks/frame",
       "recall/precision/cost", "프레임 하나가 고르는 닫힌 메뉴 번호 수",
       "rag.framequery"),
    _c("entry.frame_sections_per_query_max", 2, "프레임 진입", "count", "sections/frame",
       "recall/precision/cost", "프레임 하나에서 최종 진입하는 구역 수",
       "rag.framequery", diagram=True),
    _c("entry.frame_menu_max", 60, "프레임 진입", "slice", "rows",
       "recall/precision/cost", "프레임 LLM에 보여 주는 행위 어휘 메뉴 수",
       "rag.framequery"),
    _c("entry.frame_menu_occurrences_max", 8, "프레임 진입", "threshold", "rows/action",
       "recall/precision", "상투 행위로 보고 메뉴에서 제외하는 최대 출현 행 수",
       "rag.framequery"),
    _c("entry.vector_sections_max", 4, "진입 합류", "count", "sections",
       "recall/precision/cost", "다른 채널과 별도로 보장하는 벡터 진입 수",
       "rag.vecfirst", diagram=True),
    _c("entry.vector_prefetch_min", 8, "벡터 진입", "count", "rows",
       "recall/cost", "중복·진입 제외 전에 미리 읽는 최소 벡터 행 수", "rag.vecfirst"),
    _c("entry.vector_cos_min", 0.45, "벡터 진입", "threshold", "cosine",
       "recall/precision", "구역 벡터 검색의 최소 코사인", "rag.vector",
       env="RAG_VECTOR_MIN", diagram=True),
    _c("context.shared_sections_max", 12, "근거 합류", "count", "sections",
       "recall/cost", "일반 조립·바닥·참조 닫힘이 공유하는 목표 상한; 절대 상한 아님",
       "rag.answer", diagram=True),
    _c("context.section_chars", 6000, "근거 합류", "chars", "chars/section",
       "recall/cost", "일반 채널의 근거 구역 본문 길이(계층 탐색에서 고른 조·항은 하위 전체)", "rag.answer",
       diagram=True),
    _c("context.filter_summary_chars", 400, "관련성 필터", "chars", "chars/section",
       "recall/cost", "관련성 판정기가 보는 구역별 요약 길이", "rag.answer"),
    _c("context.term_sections_max", 4, "근거 합류", "count", "sections/term",
       "recall/cost", "용어 하나가 조립 단계에서 끌어오는 구역 수", "rag.answer"),
    _c("context.refs_per_section_max", 3, "참조 확장", "count", "refs/section",
       "recall/cost", "구역 하나가 한 걸음에 끌어오는 참조 수", "rag.answer",
       diagram=True),
    _c("context.filter_min_sections", 2, "관련성 필터", "threshold", "sections",
       "precision/cost", "관련성 필터를 호출하기 시작하는 최소 후보 수", "rag.answer"),
    _c("context.discard_excerpt_chars", 400, "관련성 필터", "chars", "chars",
       "audit/cost", "버린 근거를 감사 로그에 남기는 발췌 길이", "rag.answer"),
    _c("context.repair_refs_max", 4, "인용 교정", "count", "refs",
       "recall/cost", "답변 한 건에서 착지 교정을 시도하는 참조 수", "rag.answer"),
    _c("context.repair_children_max", 12, "인용 교정", "slice", "children/ref",
       "recall/cost", "교정할 참조 하나에 보여 주는 자손 후보 수", "rag.answer"),
    _c("expand.doc_companion_max", 20, "문서 동반", "count", "sections",
       "recall/precision/cost", "공유 상한 밖 별도 예산으로 붙는 문서 밖 인용 수",
       "rag.vecfirst", diagram=True),
    _c("expand.ref_depth_max", 3, "참조 확장", "hops", "hops",
       "recall/precision/cost", "참조 닫힘의 최대 깊이", "rag.vecfirst",
       env="RAG_REF_DEPTH", diagram=True),
    _c("expand.delegations_per_section_max", 3, "법적 바닥", "count", "sections/source",
       "recall/cost", "조 하나에서 무조건 동반하는 위임 목적지 수", "rag.expand"),
    _c("expand.navigation_hops_max", 2, "간선 항해", "hops", "hops",
       "recall/cost", "LLM 간선 항해의 최대 걸음", "rag.expand"),
    _c("expand.navigation_picks_max", 6, "간선 항해", "slice", "picks/hop",
       "recall/precision/cost", "간선 항해 한 걸음의 선택 수", "rag.expand"),
    _c("expand.navigation_cards_max", 24, "간선 항해", "slice", "cards/hop",
       "recall/cost", "간선 항해 한 걸음에 보여 주는 카드 수", "rag.expand"),
    _c("companion.terms_max", 40, "정의 동반", "slice", "terms",
       "recall/cost", "문서 정의 색인에서 유지하는 용어 수", "rag.definitions"),
    _c("companion.definitions_per_term_max", 4, "정의 동반", "count", "sections/term",
       "recall/cost", "용어 하나가 동반하는 정의 호 수", "rag.definitions"),
    _c("companion.definition_sections_max", 2, "법적 바닥", "count", "sections/source",
       "recall/cost", "착지 하나가 동반하는 정의 조 수", "rag.tags"),
    _c("companion.quantities_per_section_max", 8, "정량 태그", "slice", "values/section",
       "recall/cost", "구역 하나에서 추출·유지하는 정량 표기 수", "rag.tags"),
    _c("recover.confidence_min", 0.50, "회복", "threshold", "confidence",
       "recall/precision", "회복 판정 결과를 유지하는 최소 신뢰도", "rag.recover",
       env="RAG_RECOVER_MIN_CONF", diagram=True),
    _c("recover.funnel_steps_max", 5, "회복", "hops", "steps",
       "recall/cost", "구조 깔때기의 최대 반복 수", "rag.recover", diagram=True),
    _c("recover.funnel_picks_per_step_max", 4, "회복", "slice", "picks/step",
       "recall/cost", "구조 깔때기 한 걸음의 선택 수", "rag.recover"),
    _c("recover.funnel_keep_max", 12, "회복", "count", "sections",
       "recall/cost", "구조 깔때기가 최종 유지하는 구역 수", "rag.recover"),
    _c("recover.scout_hops_max", 3, "회복", "hops", "hops",
       "recall/cost", "그래프 수색대의 최대 걸음", "rag.recover"),
    _c("recover.scout_entries_max", 8, "회복", "count", "entries",
       "recall/cost", "그래프 수색대의 최대 시작점 수", "rag.recover"),
    _c("recover.surface_catalog_max", 24, "회복", "slice", "rows",
       "recall/cost", "회복 표면 카탈로그의 최대 행 수", "rag.recover"),
    _c("recover.fulltext_sections_max", 8, "회복", "count", "sections",
       "recall/cost", "원문 회복이 내는 최대 구역 수", "rag.recover", diagram=True),
    _c("recover.sense_catalog_max", 120, "회복", "slice", "rows",
       "recall/cost", "의미 해석기에 보여 주는 카탈로그 행 수", "rag.recover"),
    _c("recover.domain_coords_max", 8, "도메인 회복", "count", "coordinates",
       "recall/cost", "도메인 회복 단 하나가 내는 최대 좌표 수", "rag.recover_domains"),
    _c("recover.chapters_max", 2, "도메인 회복", "slice", "chapters",
       "recall/cost", "법령 계층 하강에서 고르는 장 수", "rag.recover_domains"),
    _c("recover.articles_per_chapter_max", 3, "도메인 회복", "slice", "articles/chapter",
       "recall/cost", "법령 계층 하강에서 장마다 고르는 조 수", "rag.recover_domains"),
    _c("recover.documents_max", 2, "도메인 회복", "slice", "documents",
       "recall/cost", "법령 스코프 깔때기가 고르는 문서 수", "rag.recover_domains"),
    _c("api.respot_sections_max", 6, "판정 재회수", "count", "sections",
       "recall/cost", "검색 후 쟁점 판정이 보충하는 구역 수", "api.routers.rag"),
    _c("review.facts_max", 8, "법률검토 사실", "slice", "facts",
       "recall/cost", "법률검토 입력에서 유지하는 사실 항목 수", "casereview.pipeline"),
    _c("review.facts_output_tokens", 1200, "법률검토 사실", "tokens", "tokens",
       "recall/cost", "사실 추출 LLM의 최대 출력 토큰", "casereview.pipeline"),
    _c("review.issues_max", 4, "법률검토 쟁점", "slice", "issues",
       "recall/precision/cost", "검토 하나에 유지하는 쟁점 수", "casereview.pipeline",
       diagram=True),
    _c("review.issue_probes_max", 2, "법률검토 회수", "slice", "probes",
       "recall/cost", "질문 하나에서 유지하는 조문 문체 재작성 수", "casereview.pipeline"),
    _c("review.probe_output_tokens", 300, "법률검토 회수", "tokens", "tokens",
       "recall/cost", "조문 문체 재작성 LLM의 최대 출력 토큰", "casereview.pipeline"),
    _c("review.net_triggers_min", 2, "법률검토 쟁점", "threshold", "triggers",
       "recall/precision", "결정론 쟁점 안전망이 서는 최소 카드 트리거 수",
       "casereview.pipeline"),
    _c("review.issue_output_tokens", 8000, "법률검토 쟁점", "tokens", "tokens",
       "recall/cost", "쟁점 도출 LLM의 최대 출력 토큰", "casereview.pipeline"),
    _c("review.norms_per_issue_max", 6, "법률검토 규범", "count", "norms/issue",
       "recall/precision/cost", "쟁점 하나에 조립할 규범 수", "casereview.pipeline"),
    _c("review.norms_total_max", 8, "법률검토 규범", "count", "norms",
       "recall/precision/cost", "검토 전체에서 유지하는 규범 수", "casereview.pipeline",
       diagram=True),
    _c("review.requirements_per_norm_max", 6, "법률검토 요건", "slice", "requirements/norm",
       "recall/precision/cost", "규범 하나에서 유지하는 요건 수", "casereview.pipeline",
       diagram=True),
    _c("review.sub_requirements_max", 18, "법률검토 포섭", "slice", "requirements/call",
       "recall/cost", "포섭 LLM 한 호출에 넘기는 잎 요건 수", "casereview.pipeline",
       diagram=True),
    _c("review.requirement_leaf_chars", 260, "법률검토 요건", "chars", "chars",
       "recall/precision/cost", "호·목 잎 요건의 본문 길이", "casereview.pipeline"),
    _c("review.requirement_stem_chars", 400, "법률검토 요건", "chars", "chars",
       "recall/precision/cost", "항·조 줄기 요건의 본문 길이", "casereview.pipeline"),
    _c("review.subsume_output_tokens", 12000, "법률검토 포섭", "tokens", "tokens",
       "recall/cost", "요건 포섭 LLM의 최대 출력 토큰", "casereview.pipeline"),
    _c("review.interpret_samples", 1, "법률검토 최종판정", "count", "calls",
       "variance/cost", "최종 방향 판정 표결 호출 수", "casereview.pipeline"),
    _c("review.interpret_output_tokens", 12000, "법률검토 최종판정", "tokens", "tokens",
       "recall/cost", "최종 방향 판정 LLM의 최대 출력 토큰", "casereview.pipeline"),
    _c("review.card_context_chars", 1500, "법률검토 최종판정", "chars", "chars/card",
       "precision/cost", "판정에 넣는 지식 카드 한 장의 배경 길이", "casereview.pipeline"),
    _c("review.card_context_max", 2, "법률검토 최종판정", "slice", "cards",
       "precision/cost", "최종 판정에 넣는 지식 카드 수", "casereview.pipeline"),
    _c("review.glossary_context_max", 3, "법률검토 최종판정", "slice", "definitions",
       "recall/cost", "최종 판정에 넣는 용어 정의 구역 수", "casereview.pipeline"),
    _c("review.unmet_context_max", 6, "법률검토 최종판정", "slice", "requirements",
       "precision/cost", "최종 판정에 참고로 넣는 불충족 요건 수", "casereview.pipeline"),
    _c("review.basis_max", 6, "법률검토 최종판정", "slice", "coordinates",
       "recall/precision", "최종 판정에서 유지하는 근거 좌표 수", "casereview.pipeline"),
    _c("review.inadequate_ratio", 0.80, "법률검토 되먹임", "threshold", "ratio",
       "recall/precision/cost", "회수 부적합으로 보고 다시 찾는 불명·해당없음 비율",
       "casereview.pipeline"),
    _c("review.refetch_norms_max", 3, "법률검토 되먹임", "count", "norms",
       "recall/cost", "깔때기 되먹임이 보충하는 규범 수", "casereview.pipeline"),
    _c("search.trigram_min", 0.50, "렉시컬 검색", "threshold", "score",
       "recall/precision", "부분 문자열 3-그램 매칭의 최소 점수", "rag.search"),
    _c("search.main_hits_max", 50, "렉시컬 검색", "slice", "hits",
       "recall/cost", "정확 검색이 유지하는 최대 히트 수", "rag.search"),
    _c("search.partial_hits_max", 100, "렉시컬 검색", "slice", "hits",
       "recall/cost", "부분 검색이 유지하는 최대 히트 수", "rag.search"),
    _c("search.block_hits_max", 12, "렉시컬 검색", "slice", "blocks",
       "recall/cost", "본문 블록 검색이 유지하는 최대 히트 수", "rag.search"),
    _c("wiki.article_chars", 4000, "질의 보강", "chars", "chars/article",
       "recall/cost", "위키 아티클 하나의 프롬프트 길이", "rag.wikictx"),
    _c("wiki.articles_max", 2, "질의 보강", "slice", "articles",
       "recall/precision/cost", "질의 하나에 붙이는 위키 아티클 수", "rag.wikictx"),
    _c("wiki.issue_cards_max", 2, "쟁점 분해", "slice", "cards",
       "recall/precision/cost", "질의 하나에 선택하는 쟁점 카드 수", "rag.wikictx"),
    _c("wiki.titles_per_card_max", 8, "쟁점 분해", "slice", "titles/card",
       "recall/cost", "쟁점 카드 하나에 싣는 조 제목 수", "rag.wikictx"),
    _c("oql.result_rows_ceiling", 500, "그래프 조회", "safety", "rows",
       "recall/cost", "OQL 패턴이 선언할 수 있는 결과 상한", "rag.oql"),
    _c("oql.render_rows_max", 16, "그래프 조회", "slice", "rows",
       "recall/cost", "OQL 결과 렌더링에서 유지하는 행 수", "rag.oql"),
    _c("oql.milestones_max", 24, "그래프 조회", "slice", "buckets",
       "recall/cost", "OQL 결과에서 유지하는 이정표 버킷 수", "rag.oql"),
)


_BY_KEY = {control.key: control for control in CONTROLS}
if len(_BY_KEY) != len(CONTROLS):  # pragma: no cover - import-time contract
    raise RuntimeError("RAG 성능 손잡이 key가 중복됨")


def spec(key: str) -> Control:
    try:
        return _BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"등록되지 않은 RAG 성능 손잡이: {key}") from exc


def value(key: str) -> int | float:
    """환경 override를 반영한 실제 값. 기본값의 숫자형을 보존한다."""
    control = spec(key)
    raw = os.environ.get(control.env) if control.env else None
    if raw is None or raw == "":
        return control.default
    try:
        return int(raw) if isinstance(control.default, int) else float(raw)
    except ValueError as exc:
        raise ValueError(f"{control.env}={raw!r}: {key}는 숫자여야 함") from exc


def snapshot(*, defaults: bool = False) -> list[dict[str, Any]]:
    """정렬이 안정적인 직렬화 목록. 평가 manifest와 다이어그램이 공유한다."""
    rows = []
    for control in CONTROLS:
        row = asdict(control)
        row["value"] = control.default if defaults else value(control.key)
        rows.append(row)
    return rows


def fingerprint(rows: Iterable[Mapping[str, Any]] | None = None, *,
                defaults: bool = False) -> str:
    """값뿐 아니라 뜻·소유자 변경도 잡는 재현 설정 지문."""
    payload = list(rows) if rows is not None else snapshot(defaults=defaults)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def values_by_key(rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    source = list(rows) if rows is not None else snapshot()
    return {str(row["key"]): row.get("value", row.get("default")) for row in source}


def audit(rows: Iterable[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """개별 상수가 아니라 합류 구조에서 생기는 성능 위험을 찾는다."""
    vals = values_by_key(rows)
    issues: list[dict[str, Any]] = []

    entry_max = (
        vals["entry.concept_sections_max"]
        + vals["entry.memory_sections_max"]
        + vals["entry.keyword_sections_max"]
        + vals["entry.frame_queries_max"]
        * vals["entry.frame_sections_per_query_max"]
        + vals["entry.vector_sections_max"]
    )
    shared = vals["context.shared_sections_max"]
    if entry_max > shared:
        issues.append({
            "code": "ENTRY_BUDGET_EXCEEDS_SHARED_CAP", "severity": "critical",
            "controls": [
                "entry.concept_sections_max", "entry.memory_sections_max",
                "entry.keyword_sections_max", "entry.frame_queries_max",
                "entry.frame_sections_per_query_max", "entry.vector_sections_max",
                "context.shared_sections_max",
            ],
            "observed": {"entry_theoretical_max": entry_max,
                         "shared_sections_max": shared},
            "message": ("진입 채널은 서로 자리를 보장해 이론상 "
                        f"{entry_max}구역까지 합쳐지지만 공유 상한은 {shared}다. "
                        "공유 상한을 최종 절대 상한으로 부르면 안 된다."),
        })

    companion = vals["expand.doc_companion_max"]
    if companion:
        issues.append({
            "code": "DOC_COMPANION_BYPASSES_SHARED_CAP", "severity": "critical",
            "controls": ["expand.doc_companion_max", "context.shared_sections_max"],
            "observed": {"separate_budget": companion, "shared_sections_max": shared,
                         "theoretical_final_sections": entry_max + companion},
            "message": (f"문서 동반 {companion}구역은 공유 상한 밖 별도 예산이다. "
                        "최종 컨텍스트 수·토큰·지연을 별도로 측정해야 한다."),
        })

    raw_concepts = (vals["concept.query_spans_max"]
                    * vals["concept.parts_per_span_max"]
                    * vals["concept.raw_pool_factor"])
    if raw_concepts >= 200:
        issues.append({
            "code": "CONCEPT_RAW_POOL_MULTIPLIES", "severity": "warning",
            "controls": ["concept.query_spans_max", "concept.parts_per_span_max",
                         "concept.raw_pool_factor"],
            "observed": {"raw_candidates_per_question": raw_concepts},
            "message": ("단서×후보×원시 풀 배수가 질문당 의미 후보 비교를 "
                        f"최대 {raw_concepts}행까지 키운다."),
        })

    worst_chars = ((entry_max + companion) * vals["context.section_chars"])
    if worst_chars > 120_000:
        issues.append({
            "code": "CONTEXT_CHAR_BUDGET_HIGH", "severity": "warning",
            "controls": ["context.section_chars", "expand.doc_companion_max",
                         "context.shared_sections_max"],
            "observed": {"coarse_worst_case_chars": worst_chars},
            "message": ("중복 제거 전 거친 최악치가 "
                        f"{worst_chars:,}자다. 실제 p50/p95 컨텍스트 글자와 "
                        "LLM 입력 토큰을 실행 manifest에 남겨야 한다."),
        })
    return issues


def diagram_controls() -> tuple[Control, ...]:
    return tuple(control for control in CONTROLS if control.diagram)


def validate_diagram(text: str) -> list[str]:
    """다이어그램 문서가 핵심 자름 값과 기본 설정 지문을 숨기지 않는지 검사."""
    errors = []
    marker = f"rag-controls-fingerprint: {fingerprint(defaults=True)}"
    if marker not in text:
        errors.append(f"기본 설정 지문 누락 또는 낡음: {marker}")
    for control in diagram_controls():
        if control.key not in text:
            errors.append(f"다이어그램 성능 손잡이 누락: {control.key}")
    return errors


def literal_limit_candidates(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """등록부 밖에 남은 숫자 자름 후보를 AST로 찾는다.

    숫자 슬라이스가 모두 검색 성능 손잡이는 아니다(``문자열[:80]``은 표시용일
    수 있다). 그래서 자동 등록하거나 실패시키지 않고 검토 원장으로 낸다. 반면
    사람이 grep을 다시 할 필요 없이 파일·줄·종류·값이 고정된 결과로 남는다.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]
    paths = sorted((root / "lawrag" / "core" / "rag").glob("*.py"))
    paths += [root / "lawrag" / "core" / "domain_graph" / "spanparts.py",
              root / "lawrag" / "api" / "routers" / "rag.py",
              root / "lawrag" / "core" / "casereview" / "pipeline.py"]
    ignored = {Path(__file__).resolve(),
               (root / "lawrag" / "core" / "rag" / "evaluation.py").resolve()}
    found: list[dict[str, Any]] = []

    def add(path: Path, node: ast.AST, kind: str, value: int | float,
            name: str = "") -> None:
        found.append({"path": str(path.relative_to(root)),
                      "line": int(getattr(node, "lineno", 0)),
                      "kind": kind, "name": name, "value": value})

    for path in paths:
        if not path.is_file() or path.resolve() in ignored:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                val = node.value
                if isinstance(val, ast.Constant) and isinstance(val.value, (int, float)):
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            add(path, node, "named_constant", val.value, target.id)
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
                upper = node.slice.upper
                if isinstance(upper, ast.Constant) and isinstance(upper.value, int) \
                        and upper.value > 1:
                    add(path, node, "literal_slice", upper.value)
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in {"cap", "topk", "k", "limit", "max_tokens"} \
                            and isinstance(kw.value, ast.Constant) \
                            and isinstance(kw.value.value, (int, float)):
                        add(path, kw.value, "call_budget", kw.value.value, kw.arg)
    found.sort(key=lambda row: (row["path"], row["line"], row["kind"], row["name"]))
    return found
