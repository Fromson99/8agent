"""Haiku 전용 법률 답변 후단 방법론 실험.

사례별 문구나 골든을 사용하지 않고, 문언 연산자·규범 위계·법률 삼단논법·
반대규칙 탐색이라는 일반 법률 해석 절차만 제공한다. 운영에는 배선하지 않는다.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

from lawrag.core.rag import wikictx
from lawrag.research.experiments.legal_answer_repair import (
    _claims_direct_rule_absence,
    should_preserve_interpretive_qualification,
)


HAIKU_MODEL = "claude-haiku-4-5-20251001"

METHODS = ("operator_one_pass", "matrix_render", "counterrule",
           "counterrule_wiki", "focused_direct", "focused_direct_wiki",
           "focused_fresh", "focused_fresh_wiki", "focused_rescue")

ERROR_TYPES = (
    "conclusion", "authority_scope", "condition", "exception", "modality",
    "quantity_formula", "temporal", "omission", "irrelevant_basis",
    "unsupported_inference",
)

_OPERATOR = re.compile(
    r"다만|에도 불구하고|제외|한정|각각|어느 하나|중 (?:적은|큰)|"
    r"하여야|해야|할 수 있|할 수 없|부터|까지|이내|이상|이하|초과|미만|"
    r"준용|정관|부칙|시행|경과조치|위임|대통령령|총리령|부령"
)

_ARTICLE = re.compile(r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?")
_SUBUNIT = re.compile(r"제\s*\d+\s*(?:항|호|목)")
_PATH_HISTORY = re.compile(r"\s*[<\[]\s*(?:신설|개정)[^>\]]*[>\]]")
_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_FOCUS_STOP = frozenset({
    "관한", "관련", "경우", "내용", "규정", "질문", "업무", "문맥", "대한",
    "따른", "있는", "하는", "어떻게", "무엇", "얼마", "기준", "해당",
})


def _packed(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _document_family(value: str) -> str:
    packed = _packed(value)
    return re.sub(r"(?:시행령|시행규칙|시행세칙)$", "", packed)


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _WORD.findall(str(value or ""))
            if token not in _FOCUS_STOP}


def _article_surfaces(value: str) -> set[str]:
    return {_packed(match.group(0)) for match in _ARTICLE.finditer(str(value or ""))}


def _unit_surfaces(value: str) -> set[str]:
    return (_article_surfaces(value)
            | {_packed(match.group(0)) for match in _SUBUNIT.finditer(
                str(value or ""))})


def provenance_path(path: str) -> tuple[str, list[str]]:
    """상위 편·장·절의 연혁을 해당 조문 연혁과 섞지 않는다."""
    parts = str(path or "").split(" ▸ ")
    if not parts:
        return str(path or ""), []
    ancestors, clean = [], []
    for position, part in enumerate(parts):
        histories = _PATH_HISTORY.findall(part)
        if histories and position < len(parts) - 1:
            ancestors.extend(value.strip() for value in histories)
            part = _PATH_HISTORY.sub("", part).strip()
        clean.append(part)
    return " ▸ ".join(clean), ancestors


def _focus_score(question: str, row: dict[str, Any], position: int) -> float:
    path = str(row.get("path") or "")
    document = str(row.get("document") or "")
    question_packed = _packed(question)
    path_packed = _packed(path)
    score = 2.0 / max(1, position)
    if _packed(document) and _packed(document) in question_packed:
        score += 10
    asked_articles = _article_surfaces(question)
    if asked_articles & _article_surfaces(path):
        score += 14
    overlap = _tokens(question) & _tokens(f"{document} {path}")
    score += min(12, 2 * len(overlap))
    role = str(row.get("role") or "")
    if role in {"exact-structural", "question_memory", "title"}:
        score += 2
    if any(kind in role for kind in ("배제", "준용", "위임", "수임", "정의")):
        score += 4
    return score


def focus_evidence(question: str, evidence: list[dict[str, Any]], *,
                   core_limit: int = 2, total_limit: int = 5) \
        -> list[dict[str, Any]]:
    """짧은 표제 관련도와 명시 참조로 원문을 압축한다.

    골든 좌표나 사례 ID를 보지 않는다. 상위 후보를 씨앗으로 고른 뒤 씨앗이
    가리키는 조문과 씨앗을 명시적으로 배제·준용하는 역방향 조문을 보존한다.
    D 채널 반례 때문에 supplemental-closure 최고점 한 건도 별도 안전망으로 둔다.
    """
    if len(evidence) <= core_limit:
        return list(evidence)
    ranked = sorted(enumerate(evidence), key=lambda pair: (
        -_focus_score(question, pair[1], pair[0] + 1), pair[0]))
    chosen = {position for position, _row in ranked[:core_limit]}

    def refs(row: dict[str, Any]) -> set[str]:
        return _article_surfaces(str(row.get("original_text") or ""))

    # 동일 문서의 명시 조문 참조를 양방향으로 보존한다. 배제·준용은 놓치면
    # 결론 방향 자체가 바뀌므로 역방향 원문도 포함한다.
    seed_articles = set().union(*(
        _article_surfaces(str(evidence[i].get("path") or "")) for i in chosen))
    seed_docs = {_document_family(str(evidence[i].get("document") or ""))
                 for i in chosen}
    companions = []
    for position, row in enumerate(evidence):
        if position in chosen:
            continue
        same_doc = _document_family(str(row.get("document") or "")) in seed_docs
        path_articles = _article_surfaces(str(row.get("path") or ""))
        text = str(row.get("original_text") or "")
        reverse = bool(same_doc and refs(row) & seed_articles and re.search(
            r"다만|에도 불구하고|적용하지 아니|제외|준용", text))
        if reverse:
            companions.append((position, _focus_score(question, row, position + 1)))
    for position, _score in sorted(companions, key=lambda value: (-value[1], value[0])):
        if len(chosen) >= total_limit:
            break
        chosen.add(position)

    supplemental = [(position, row) for position, row in enumerate(evidence)
                    if position not in chosen
                    and "supplemental-closure" in str(row.get("role") or "")]
    if supplemental and len(chosen) < total_limit:
        position, _row = max(supplemental, key=lambda pair: (
            _focus_score(question, pair[1], pair[0] + 1), -pair[0]))
        chosen.add(position)
    return [row for position, row in enumerate(evidence) if position in chosen]


def focused_excerpt(question: str, row: dict[str, Any], *, cap: int = 3500) -> str:
    """긴 subtree에서 질문 용어·항호·규범 연산자 주변만 보존한다."""
    text = str(row.get("original_text") or "")
    if len(text) <= cap:
        return text
    lines = text.splitlines()
    asked_tokens = _tokens(question)
    asked_units = _unit_surfaces(question)
    ranked = []
    for position, line in enumerate(lines):
        score = 0
        overlap = asked_tokens & _tokens(line)
        score += 3 * len(overlap)
        score += 8 * len(asked_units & _unit_surfaces(line))
        if _OPERATOR.search(line):
            score += 2
        if "기준금액" in question and "기준금액" in line:
            score += 10
        if score:
            ranked.append((score, position))
    keep = {0}
    for _score, position in sorted(ranked, key=lambda value: (-value[0], value[1]))[:14]:
        keep.update(range(max(0, position - 1), min(len(lines), position + 2)))
    excerpt = "\n".join(lines[position] for position in sorted(keep))
    if len(excerpt) > cap:
        excerpt = excerpt[:cap]
    return excerpt + "\n[긴 원문에서 질문 관련 절만 결정론 발췌]"


def compress_focused(question: str, evidence: list[dict[str, Any]]) \
        -> list[dict[str, Any]]:
    out = []
    for row in focus_evidence(question, evidence):
        copy = dict(row)
        copy["original_chars"] = len(str(row.get("original_text") or ""))
        copy["original_text"] = focused_excerpt(question, row)
        out.append(copy)
    return out


def authority_kind(document: str) -> str:
    """문서명만으로 최소한의 규범 종류를 표시한다. 우열 결론은 모델이 낸다."""
    name = " ".join(str(document or "").split())
    if any(value in name for value in (
            "가이드", "가이드라인", "체크리스트", "해설", "표준정관",
            "모범규준", "FAQ", "질의회신", "업무편람")):
        return "guidance_or_model_rule"
    if "판례" in name or "결정" in name:
        return "case_or_decision"
    if "시행령" in name:
        return "enforcement_decree"
    if "시행규칙" in name:
        return "enforcement_rule"
    if "시행세칙" in name:
        return "detailed_rule"
    if name.endswith("법") or " 법률" in name:
        return "statute"
    if "규정" in name or "세칙" in name:
        return "regulation"
    return "other_document"


def evidence_payload(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in evidence:
        path, ancestor_history = provenance_path(str(row.get("path") or ""))
        out.append({
            "id": str(row.get("id") or ""),
            "document": str(row.get("document") or ""),
            "authority_kind": authority_kind(str(row.get("document") or "")),
            "path": path,
            "ancestor_heading_history": ancestor_history,
            "provenance_warning": (
                "ancestor_heading_history는 상위 편·장·절·관의 연혁이며 해당 조문의 "
                "신설·개정일이 아님" if ancestor_history else ""),
            "document_revision": str(row.get("document_revision") or ""),
            "document_enforcement": str(row.get("document_enforcement") or ""),
            "document_current": bool(row.get("document_current", True)),
            "role": str(row.get("role") or ""),
            "text": str(row.get("original_text") or ""),
        })
    return out


def operator_ledger(evidence: list[dict[str, Any]], *, per_evidence: int = 5) \
        -> dict[str, Any]:
    """Haiku가 지나치기 쉬운 규범 연산자가 든 짧은 줄을 결정론으로 표시한다."""
    inventory = []
    cues = []
    for row in evidence:
        evidence_id = str(row.get("id") or "")
        document = str(row.get("document") or "")
        inventory.append({
            "id": evidence_id,
            "document": document,
            "authority_kind": authority_kind(document),
            "path": str(row.get("path") or ""),
        })
        seen = set()
        for raw in re.split(r"[\r\n]+", str(row.get("original_text") or "")):
            line = " ".join(raw.split())
            if not line or not _OPERATOR.search(line):
                continue
            excerpt = line[:500]
            if excerpt in seen:
                continue
            seen.add(excerpt)
            cues.append({"evidence_id": evidence_id, "excerpt": excerpt})
            if len(seen) >= per_evidence:
                break
    return {"authority_inventory": inventory, "operator_cues": cues}


def wiki_picks(question: str, evidence: list[dict[str, Any]], *, limit: int = 3) \
        -> list[dict[str, Any]]:
    """기존 llm-wiki 라우터로 쟁점·방법·해석 배경을 결정론 선택한다."""
    sections = []
    companion_kinds = ("정의", "제재", "위임", "수임", "준용", "배제")
    for position, row in enumerate(evidence, 1):
        text = str(row.get("original_text") or "")
        path = str(row.get("path") or "")
        role = str(row.get("role") or "")
        signal_text = " ".join((path, role, text[:3000]))
        kind = next((value for value in companion_kinds if value in signal_text), "")
        # 기존 methods_for의 단서 신호 형식과 맞춘다. 원문 자체는 바꾸지 않는다.
        method_text = text if "다만," in text else text.replace("다만 ", "다만, ")
        sections.append(SimpleNamespace(
            n=position, kind=kind, text=method_text,
            doc=str(row.get("document") or ""), path=path))
    picks = []
    have = set()
    candidates = (
        list(wikictx.spot(question))
        + list(wikictx.methods_for(sections))
        + list(wikictx.pick(
            question, {str(row.get("document") or "") for row in evidence}))
    )
    for pick in candidates:
        slug = str(pick.get("slug") or "")
        if not slug or slug in have:
            continue
        have.add(slug)
        picks.append(pick)
        if len(picks) >= limit:
            break
    return picks


def wiki_background(question: str, evidence: list[dict[str, Any]]) \
        -> tuple[list[dict[str, Any]], str]:
    picks = wiki_picks(question, evidence)
    if not picks:
        return [], ""
    safe = [{"slug": row.get("slug"), "title": row.get("title"),
             "why": row.get("why"), "text": row.get("text")}
            for row in picks]
    return picks, (
        "\n\n[LLM 위키 해석 배경 — 증거가 아님]\n"
        "아래 카드는 해석 순서와 주의점을 위한 배경이다. 카드 속 사례·수치·조문을 "
        "이번 질문의 사실이나 근거로 사용하지 말고, 결론은 반드시 회수 원문 E번호로 "
        "세운다.\n" + json.dumps(safe, ensure_ascii=False))


FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "requested_items": {"type": "array", "items": {"type": "string"}},
        "checks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "status": {"type": "string",
                           "enum": ["satisfied", "contradicted", "unknown"]},
                "finding": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["item", "status", "finding", "evidence_ids"],
            "additionalProperties": False,
        }},
        "errors": {"type": "array",
                   "items": {"type": "string", "enum": list(ERROR_TYPES)}},
        "action": {"type": "string", "enum": ["keep", "repair", "insufficient"]},
        "reason": {"type": "string"},
        "support_ids": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
    },
    "required": ["requested_items", "checks", "errors", "action", "reason",
                 "support_ids", "answer"],
    "additionalProperties": False,
}


MATRIX_SCHEMA = {
    "type": "object",
    "properties": {
        "question_scope": {"type": "string"},
        "requested_items": {"type": "array", "items": {"type": "string"}},
        "rules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": [
                    "governing", "definition", "condition", "exception",
                    "temporal", "procedure", "context"]},
                "statement": {"type": "string"},
                "modality": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["role", "statement", "modality", "evidence_ids"],
            "additionalProperties": False,
        }},
        "authority_conflicts": {"type": "array", "items": {"type": "string"}},
        "missing_links": {"type": "array", "items": {"type": "string"}},
        "provisional_conclusion": {"type": "string"},
    },
    "required": ["question_scope", "requested_items", "rules",
                 "authority_conflicts", "missing_links", "provisional_conclusion"],
    "additionalProperties": False,
}


LEGAL_METHOD = """공통 법률 해석 규율:
1. 질문이 지정한 법령·시장·주체·시점을 먼저 고정한다. 비슷한 다른 시장이나 문서를
   대신 답하지 않는다. 질문이 범위를 열어 둔 경우에만 서로 다른 정식 규범을 구분한다.
2. 법률→시행령→시행규칙·정식 규정·세칙의 위계를 보되, 특별규정은 일반규정보다
   우선하고 명시적 준용·위임 범위를 넘지 않는다. 가이드·체크리스트·표준안은 법령에
   해당 문언이 있다는 근거가 아니다.
3. 주체·행위·대상·조건·법적 효과를 원문대로 분리한다. '하여야 한다'와 '할 수
   있다', '각각'과 합산, '또는'과 누적, '중 적은/큰 금액'을 바꾸지 않는다.
4. 본문과 단서, 예외와 재예외, 정의의 적용 범위, 시행일·부칙·경과조치를 한 세트로
   읽는다. 질문이 요구한 수치·기간·산식·대안은 모두 답한다.
5. 원문에 직접 답이 있으면 회피하지 않는다. 반대로 검색 표본에 문구가 없다는 것만으로
   전체 법체계에 규정이 없다고 단정하지 않는다.
6. 초안이 질문에 정확히 답했다면 더 자세히 쓸 수 있다는 이유로 고치지 않는다.
   교정 답변은 질문 범위 안에서 결론부터 간결하게 쓴다."""


ONE_PASS_SYSTEM = f"""너는 법률 답변의 문언 감사자다.
{LEGAL_METHOD}

코드가 [규범 연산자 장부]에 위험 문언을 표시했다. 장부는 주의 신호일 뿐 결론이
아니다. 질문의 요청 항목을 원자적으로 적고, 회수 원문으로 독립 판단한 뒤 마지막에
초안과 비교한다. 핵심 오류가 없으면 keep하고 초안을 그대로 보존한다. E번호만
근거로 쓰고, 내부 E번호는 최종 answer에 쓰지 않는다."""


MATRIX_SYSTEM = f"""너는 법률 답변을 쓰기 전의 규칙 컴파일러다.
{LEGAL_METHOD}

답변 문장을 작성하거나 초안을 보지 않는다. 질문 범위를 고정하고, 요청 항목별로
지배규범·정의·요건·예외·시점·절차를 제공된 원문 E번호에 묶어 법률 삼단논법의
규칙표만 만든다. 서로 다른 권위나 시장이 섞이면 authority_conflicts에 적고,
원문 연결이 비면 missing_links에 남긴다."""


RENDER_SYSTEM = f"""너는 컴파일된 법률 규칙표로 초안을 교정하는 편집자다.
{LEGAL_METHOD}

규칙표 밖의 법률 지식을 추가하지 않는다. 질문이 요구한 각 항목이 표에 있는지,
초안의 결론·조건·예외·강행성·수치·시점이 표와 맞는지 확인한다. 핵심 오류가 없으면
keep한다. E번호는 최종 answer에 쓰지 않는다."""


COUNTER_SYSTEM = f"""너는 법률 답변의 반대규칙 심사자다.
{LEGAL_METHOD}

규칙표의 잠정 결론과 초안을 그대로 믿지 말고, 회수 원문에서 그 결론을 깨는 단서,
적용배제, 특별규정, 다른 시점, 다른 시장·주체, 강행/임의 양태, 빠진 산식 항목을 먼저
찾는다. 실제 반대규칙이 없으면 억지로 만들지 않는다. 마지막에만 keep/repair/
insufficient를 정하고 간결한 최종 answer를 쓴다. E번호는 answer에 쓰지 않는다."""


FOCUSED_SYSTEM = f"""너는 좁혀진 법률 원문으로 기존 답변을 감사하는 변호사다.
{LEGAL_METHOD}

코드가 문서명·조문번호·표제 관련도와 명시 참조로 원문을 좁혔다. 질문에 답하는
문언을 먼저 그대로 식별하고 결론을 낸 뒤 초안과 비교한다. '각각', '어느 하나',
'중 적은/큰 금액', 본문·단서·예외, 의무·재량 양태를 문언대로 연산한다.
ancestor_heading_history는 상위 편·장·절·관의 연혁일 뿐 해당 조문의 연혁이 아니다.
문서 revision/enforcement는 판본 메타이며, 그것만으로 특정 조문의 신설일이라고
단정하지 않는다. 초안의 핵심 결론·조건·예외·수치·시점이 맞으면 keep, 틀리면
repair한다. 최종 answer에는 E번호를 쓰지 않는다."""


FRESH_SYSTEM = f"""너는 좁혀진 법률 원문으로 답하는 변호사다.
{LEGAL_METHOD}

기존 답변은 보지 않는다. 질문의 요청 항목만 원자적으로 정리하고, 좁혀진 원문에서
지배규범과 직접 연결된 예외를 확인한 뒤 그 예외를 사안에 실제 적용한 최종 결론부터
간결하게 답한다. 예외가 명시되면 '가능성이 있다'로 약화하지 않는다. '각각',
'어느 하나', '중 적은/큰 금액', 본문·단서·예외, 의무·재량 양태를 문언 그대로
연산한다. 묻지 않은 인접 제도·절차는 답에 덧붙이지 않는다.
ancestor_heading_history는 상위 편·장·절·관의 연혁일 뿐 해당 조문의 연혁이 아니다.
문서 revision/enforcement는 판본 메타이며, 그것만으로 특정 조문의 신설일이라고
단정하지 않는다. 모든 핵심 명제는 제공된 E번호의 원문으로 지지되어야 하며 최종
answer에는 E번호를 쓰지 않는다."""


FRESH_SCHEMA = {
    "type": "object",
    "properties": {
        "requested_items": {"type": "array", "items": {"type": "string"}},
        "support_ids": {"type": "array", "items": {"type": "string"}},
        "answerable": {"type": "boolean"},
        "reason": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["requested_items", "support_ids", "answerable", "reason", "answer"],
    "additionalProperties": False,
}


RESCUE_SCHEMA = {
    "type": "object",
    "properties": {
        "choice": {"type": "string", "enum": ["baseline", "candidate"]},
        "support_ids": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["choice", "support_ids", "reason"],
    "additionalProperties": False,
}


RESCUE_SYSTEM = f"""너는 두 법률 답변 중 안전한 하나만 고르는 선택기다.
{LEGAL_METHOD}

문장을 새로 쓰지 않는다. 질문과 좁혀진 원문을 기준으로 baseline과 candidate 중
핵심 결론·조건·예외·수치가 더 정확한 답을 선택한다. baseline이 '회수되지 않았다'
고 말해도 원문에 직접 답하는 문언이 있으면 candidate를 고른다. 반대로 질문이
명시적 조정·예외의 존재 여부를 묻고 원문이 그 조정을 두지 않은 것이 결론이라면,
부재를 밝힌 baseline을 회피라고 오인하지 않는다. 확신이 같거나 원문만으로 후보의
적극 결론을 지지할 수 없으면 baseline을 보존한다."""


_ABSTENTION = re.compile(
    r"회수된 자료(?:에서는|에는)?.{0,45}?(?:없|찾을 수 없)|"
    r"판단할 수 없|확인할 수 없|명확하지 않|불명확|불분명|추가 자료.{0,20}필요"
)


def is_abstaining_answer(answer: str) -> bool:
    return bool(_ABSTENTION.search(str(answer or "")))


def _user(question: str, evidence: list[dict[str, Any]], draft: str = "") -> str:
    body = (f"[질문]\n{question}\n\n[회수 원문]\n"
            + json.dumps(evidence_payload(evidence), ensure_ascii=False)
            + "\n\n[규범 연산자 장부]\n"
            + json.dumps(operator_ledger(evidence), ensure_ascii=False))
    if draft:
        body += f"\n\n[기존 초안]\n{draft}"
    return body


def _guard(raw: dict[str, Any] | None, evidence: list[dict[str, Any]],
           draft: str) -> dict[str, Any]:
    if raw is None:
        return {"action": "keep", "answer": draft, "guard": "llm_failed"}
    out = dict(raw)
    valid = {str(row.get("id") or "") for row in evidence}
    support = list(dict.fromkeys(
        str(value) for value in out.get("support_ids") or [] if str(value) in valid))
    invalid = [str(value) for value in out.get("support_ids") or []
               if str(value) not in valid]
    out["support_ids"] = support
    action = str(out.get("action") or "keep")
    answer = str(out.get("answer") or "").strip()
    unresolved = any(str(row.get("status")) == "unknown"
                     for row in out.get("checks") or [])
    if action == "keep":
        final, guard = draft, "keep_exact_draft"
    elif unresolved and _claims_direct_rule_absence(draft):
        action, final, guard = "keep", draft, "unresolved_absence"
    elif should_preserve_interpretive_qualification(draft, answer):
        action, final, guard = "keep", draft, "preserve_interpretive_qualification"
    elif not answer or invalid or (evidence and not support):
        action, final, guard = "keep", draft, "invalid_repair"
    else:
        final, guard = answer, "accepted"
    out["action"] = action
    return {"action": action, "answer": final, "guard": guard, "raw": out}


def operator_one_pass(llm, question: str, evidence: list[dict[str, Any]],
                      draft: str) -> dict[str, Any]:
    raw = llm.structured(
        "rag.answer.haiku.operator_one_pass.experimental", ONE_PASS_SYSTEM,
        _user(question, evidence, draft), FINAL_SCHEMA, max_tokens=3500,
        effort="low", model=HAIKU_MODEL)
    return _guard(raw, evidence, draft)


def compile_matrix(llm, question: str, evidence: list[dict[str, Any]],
                   wiki: str = "") \
        -> dict[str, Any] | None:
    return llm.structured(
        "rag.answer.haiku.legal_matrix.experimental", MATRIX_SYSTEM,
        _user(question, evidence) + wiki, MATRIX_SCHEMA, max_tokens=3500,
        effort="low", model=HAIKU_MODEL)


def _matrix_final(llm, kind: str, system: str, question: str,
                  evidence: list[dict[str, Any]], draft: str,
                  matrix: dict[str, Any] | None, *, include_evidence: bool,
                  wiki: str = "") \
        -> dict[str, Any]:
    if matrix is None:
        return {"action": "keep", "answer": draft,
                "guard": "matrix_failed", "matrix": None}
    user = (f"[질문]\n{question}\n\n[법률 규칙표]\n"
            f"{json.dumps(matrix, ensure_ascii=False)}\n\n[기존 초안]\n{draft}")
    if include_evidence:
        user += ("\n\n[회수 원문 재검사]\n"
                 + json.dumps(evidence_payload(evidence), ensure_ascii=False)
                 + "\n\n[규범 연산자 장부]\n"
                 + json.dumps(operator_ledger(evidence), ensure_ascii=False))
    user += wiki
    raw = llm.structured(kind, system, user, FINAL_SCHEMA, max_tokens=3500,
                         effort="low", model=HAIKU_MODEL)
    result = _guard(raw, evidence, draft)
    result["matrix"] = matrix
    return result


def matrix_render(llm, question: str, evidence: list[dict[str, Any]],
                  draft: str) -> dict[str, Any]:
    matrix = compile_matrix(llm, question, evidence)
    return _matrix_final(
        llm, "rag.answer.haiku.matrix_render.experimental", RENDER_SYSTEM,
        question, evidence, draft, matrix, include_evidence=False)


def counterrule(llm, question: str, evidence: list[dict[str, Any]],
                draft: str) -> dict[str, Any]:
    matrix = compile_matrix(llm, question, evidence)
    return _matrix_final(
        llm, "rag.answer.haiku.counterrule.experimental", COUNTER_SYSTEM,
        question, evidence, draft, matrix, include_evidence=True)


def counterrule_wiki(llm, question: str, evidence: list[dict[str, Any]],
                     draft: str) -> dict[str, Any]:
    picks, wiki = wiki_background(question, evidence)
    matrix = compile_matrix(llm, question, evidence, wiki=wiki)
    result = _matrix_final(
        llm, "rag.answer.haiku.counterrule_wiki.experimental", COUNTER_SYSTEM,
        question, evidence, draft, matrix, include_evidence=True, wiki=wiki)
    result["wiki"] = [{"slug": row.get("slug"), "title": row.get("title"),
                       "why": row.get("why")} for row in picks]
    return result


def _focused_direct(llm, question: str, evidence: list[dict[str, Any]],
                    draft: str, *, with_wiki: bool) -> dict[str, Any]:
    focused = compress_focused(question, evidence)
    picks, wiki = wiki_background(question, focused) if with_wiki else ([], "")
    raw = llm.structured(
        "rag.answer.haiku.focused_direct_wiki.experimental" if with_wiki else
        "rag.answer.haiku.focused_direct.experimental",
        FOCUSED_SYSTEM, _user(question, focused, draft) + wiki,
        FINAL_SCHEMA, max_tokens=3500, effort="low", model=HAIKU_MODEL)
    result = _guard(raw, focused, draft)
    result["focused_ids"] = [str(row.get("id") or "") for row in focused]
    result["focused_chars"] = sum(
        len(str(row.get("original_text") or "")) for row in focused)
    if with_wiki:
        result["wiki"] = [{"slug": row.get("slug"), "title": row.get("title"),
                           "why": row.get("why")} for row in picks]
    return result


def _focused_fresh(llm, question: str, evidence: list[dict[str, Any]],
                   draft: str, *, with_wiki: bool) -> dict[str, Any]:
    focused = compress_focused(question, evidence)
    picks, wiki = wiki_background(question, focused) if with_wiki else ([], "")
    raw = llm.structured(
        "rag.answer.haiku.focused_fresh_wiki.experimental" if with_wiki else
        "rag.answer.haiku.focused_fresh.experimental",
        FRESH_SYSTEM, _user(question, focused) + wiki,
        FRESH_SCHEMA, max_tokens=3000, effort="low", model=HAIKU_MODEL)
    valid = {str(row.get("id") or "") for row in focused}
    support = list(dict.fromkeys(
        str(value) for value in (raw or {}).get("support_ids") or []
        if str(value) in valid))
    answer = str((raw or {}).get("answer") or "").strip()
    accepted = bool((raw or {}).get("answerable")) and bool(answer) and bool(support)
    result = {
        "action": "repair" if accepted else "keep",
        "answer": answer if accepted else draft,
        "guard": "accepted_fresh" if accepted else "fresh_failed",
        "raw": raw, "focused_ids": [str(row.get("id") or "") for row in focused],
        "focused_chars": sum(len(str(row.get("original_text") or ""))
                             for row in focused),
    }
    if with_wiki:
        result["wiki"] = [{"slug": row.get("slug"), "title": row.get("title"),
                           "why": row.get("why")} for row in picks]
    return result


def focused_direct(llm, question: str, evidence: list[dict[str, Any]],
                   draft: str) -> dict[str, Any]:
    return _focused_direct(llm, question, evidence, draft, with_wiki=False)


def focused_direct_wiki(llm, question: str, evidence: list[dict[str, Any]],
                        draft: str) -> dict[str, Any]:
    return _focused_direct(llm, question, evidence, draft, with_wiki=True)


def focused_fresh(llm, question: str, evidence: list[dict[str, Any]],
                  draft: str) -> dict[str, Any]:
    return _focused_fresh(llm, question, evidence, draft, with_wiki=False)


def focused_fresh_wiki(llm, question: str, evidence: list[dict[str, Any]],
                       draft: str) -> dict[str, Any]:
    return _focused_fresh(llm, question, evidence, draft, with_wiki=True)


def focused_rescue(llm, question: str, evidence: list[dict[str, Any]],
                   draft: str) -> dict[str, Any]:
    """회피 신호가 있는 답만 신규답과 비교한다. 나머지는 무호출 보존한다."""
    if not is_abstaining_answer(draft):
        return {"action": "keep", "answer": draft, "guard": "not_abstaining"}
    fresh = _focused_fresh(llm, question, evidence, draft, with_wiki=False)
    candidate = str(fresh.get("answer") or draft)
    if candidate == draft:
        return {**fresh, "action": "keep", "answer": draft,
                "guard": "fresh_unavailable"}
    focused = compress_focused(question, evidence)
    user = (f"[질문]\n{question}\n\n[좁혀진 원문]\n"
            f"{json.dumps(evidence_payload(focused), ensure_ascii=False)}\n\n"
            f"[baseline]\n{draft}\n\n[candidate]\n{candidate}")
    raw = llm.structured(
        "rag.answer.haiku.focused_rescue.experimental", RESCUE_SYSTEM, user,
        RESCUE_SCHEMA, max_tokens=1200, effort="low", model=HAIKU_MODEL)
    valid = {str(row.get("id") or "") for row in focused}
    support = [str(value) for value in (raw or {}).get("support_ids") or []
               if str(value) in valid]
    choice = str((raw or {}).get("choice") or "baseline")
    accepted = choice == "candidate" and bool(support)
    return {
        "action": "repair" if accepted else "keep",
        "answer": candidate if accepted else draft,
        "guard": "rescue_candidate" if accepted else "rescue_baseline",
        "raw": raw, "fresh": fresh.get("raw"),
        "focused_ids": [str(row.get("id") or "") for row in focused],
        "focused_chars": sum(len(str(row.get("original_text") or ""))
                             for row in focused),
    }


RUNNERS = {
    "operator_one_pass": operator_one_pass,
    "matrix_render": matrix_render,
    "counterrule": counterrule,
    "counterrule_wiki": counterrule_wiki,
    "focused_direct": focused_direct,
    "focused_direct_wiki": focused_direct_wiki,
    "focused_fresh": focused_fresh,
    "focused_fresh_wiki": focused_fresh_wiki,
    "focused_rescue": focused_rescue,
}
