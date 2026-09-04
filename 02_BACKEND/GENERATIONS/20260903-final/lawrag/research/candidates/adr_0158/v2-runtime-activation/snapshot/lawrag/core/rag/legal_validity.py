"""법률 근거의 시점과 법원성 메타데이터를 보수적으로 검증한다.

이 모듈은 우열을 확정하는 법률판단기가 아니다. 문서 종류와 현재 보유한 시행일·
개정일·판본 메타로 검증 가능한 것과 검증 불가능한 것을 분리해 답변기에 넘긴다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass


_ISO_DATE = re.compile(r"(?<!\d)(?P<y>19\d{2}|20\d{2})[-./](?P<m>0?[1-9]|1[0-2])[-./](?P<d>0?[1-9]|[12]\d|3[01])(?!\d)")
_KOREAN_DATE = re.compile(r"(?<!\d)(?P<y>19\d{2}|20\d{2})\s*년\s*(?P<m>0?[1-9]|1[0-2])\s*월\s*(?P<d>0?[1-9]|[12]\d|3[01])\s*일")


@dataclass(frozen=True)
class ValidityFinding:
    doc_id: str
    document: str
    authority_class: str
    authority_rank: int
    as_of: str = ""
    temporal_status: str = "not_requested"
    enforce: str = ""
    revised: str = ""
    current_version: bool = True
    warning: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _date(value: str | None) -> dt.date | None:
    packed = re.sub(r"\D", "", str(value or ""))
    if len(packed) != 8:
        return None
    try:
        return dt.date(int(packed[:4]), int(packed[4:6]), int(packed[6:]))
    except ValueError:
        return None


def parse_as_of(question: str) -> dt.date | None:
    """질문에 명시된 완전한 날짜만 읽는다. 연도만으로 시점을 추측하지 않는다."""
    for pattern in (_KOREAN_DATE, _ISO_DATE):
        match = pattern.search(question or "")
        if match:
            try:
                return dt.date(*(int(match.group(key)) for key in ("y", "m", "d")))
            except ValueError:
                return None
    return None


def authority(view) -> tuple[str, int]:
    """문서 메타 기반의 표시용 등급. 같은 등급 내 충돌 해결에는 쓰지 않는다."""
    name = re.sub(r"\s+", "", str(getattr(view, "name", "") or ""))
    kind = str(getattr(view, "kind", "") or "").casefold()
    if "헌법" == name or kind == "constitution":
        return "constitution", 0
    if name.endswith("시행령") or kind in {"presidential-decree", "decree"}:
        return "presidential_decree", 20
    if name.endswith(("시행규칙", "규칙")) and kind == "law":
        return "ministerial_or_other_rule", 30
    if kind == "law":
        return "statute", 10
    if kind == "admrul":
        return "administrative_rule", 40
    if kind in {"krx-rule", "kofia-rule"}:
        return "self_regulatory_rule", 50
    if kind == "internal":
        return "internal_rule", 60
    if kind.endswith("-form") or kind in {"krx-form", "klca-model"}:
        return "form_or_model", 70
    return "unclassified", 90


def validate_document(view, as_of: dt.date | None = None) -> ValidityFinding:
    klass, rank = authority(view)
    enforce = _date(getattr(view, "enforce", ""))
    revised = _date(getattr(view, "revised", ""))
    current = bool(getattr(view, "is_current", True))
    status = "not_requested"
    warning = ""
    if as_of is not None:
        if enforce is None:
            status = "unknown_effective_date"
            warning = "시행일 메타데이터가 없어 해당 시점의 효력을 확인할 수 없음"
        elif enforce > as_of:
            status = "not_yet_effective"
            warning = "질문 기준일보다 문서 시행일이 늦음"
        elif not current:
            status = "historical_version_candidate"
            warning = "구판이지만 적용 종료일 메타데이터가 없어 기준일 유효성을 확정할 수 없음"
        elif revised is not None and revised > as_of:
            status = "unverifiable_historical_text"
            warning = "현행 원문만 보유하여 기준일 당시 조문 문언을 재현할 수 없음"
        else:
            status = "effective_current_text"
    return ValidityFinding(
        doc_id=str(getattr(view, "doc_id", "") or ""),
        document=str(getattr(view, "name", "") or ""),
        authority_class=klass,
        authority_rank=rank,
        as_of=as_of.isoformat() if as_of else "",
        temporal_status=status,
        enforce=str(getattr(view, "enforce", "") or ""),
        revised=str(getattr(view, "revised", "") or ""),
        current_version=current,
        warning=warning,
    )


def validate_coordinates(index, coordinates, question: str = "") -> list[ValidityFinding]:
    as_of = parse_as_of(question)
    findings = []
    for doc_id, _node in dict.fromkeys(coordinates):
        view = index.docs.get(str(doc_id))
        if view is not None:
            findings.append(validate_document(view, as_of))
    return sorted(findings, key=lambda row: (row.authority_rank, row.document, row.doc_id))
