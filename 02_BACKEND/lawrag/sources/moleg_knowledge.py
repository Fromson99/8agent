"""국가법령정보센터 법령지식 OPEN API의 호출 계약과 순수 XML 파서.

인증값(OC)은 호출 시에만 사용하며 URL, 산출물, 예외 메시지에 기록하지 않는다.
공식 응답의 한글 필드명은 ``fields``에 원형 보존하고, 자주 쓰는 좌표만 공통
필드로 투영한다. 새 필드가 추가되어도 원문 XML과 ``fields``가 손실을 막는다.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import logging
import re
import xml.etree.ElementTree as ET
from typing import Iterable, Mapping
from urllib.parse import quote, quote_plus

from .common import HttpClient


BASE = "https://www.law.go.kr/DRF"
RELATION_CODES = {
    "synonym": "140301",
    "antonym": "140302",
    "broader": "140303",
    "narrower": "140304",
    "related": "140305",
}


@dataclass(frozen=True)
class EndpointSpec:
    key: str
    target: str
    operation: str
    item_tags: tuple[str, ...]
    required: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    paged: bool = True
    description: str = ""

    @property
    def url(self) -> str:
        return f"{BASE}/{self.operation}"


ENDPOINTS: dict[str, EndpointSpec] = {
    "legal_terms": EndpointSpec(
        "legal_terms", "lstrm", "lawSearch.do", ("lstrm",),
        optional=("query", "sort", "regDt", "gana", "dicKndCd"),
        description="법령용어 목록",
    ),
    "legal_term_detail": EndpointSpec(
        "legal_term_detail", "lstrm", "lawService.do",
        ("LsTrmService", "lstrm", "법령용어"),
        required_any=("query", "trmSeqs"), paged=False,
        description="법령용어 본문/정의",
    ),
    "knowledge_terms": EndpointSpec(
        "knowledge_terms", "lstrmAI", "lawSearch.do", ("법령용어",),
        optional=("query", "homonymYn"), description="법령지식 용어 목록",
    ),
    "everyday_terms": EndpointSpec(
        "everyday_terms", "dlytrm", "lawSearch.do", ("일상용어",),
        optional=("query",), description="일상용어 목록",
    ),
    "legal_term_relations": EndpointSpec(
        "legal_term_relations", "lstrmRlt", "lawService.do", ("연계용어",),
        required_any=("query", "MST"), optional=("relation",),
        paged=False, description="법령용어 관계(동의/반의/상위/하위/관련)",
    ),
    "everyday_term_relations": EndpointSpec(
        "everyday_term_relations", "dlytrmRlt", "lawService.do", ("연계용어",),
        required_any=("query", "MST"), optional=("relation",), paged=False,
        description="일상용어 관계",
    ),
    "term_articles": EndpointSpec(
        "term_articles", "lstrmRltJo", "lawService.do", ("연계법령",),
        required_any=("query", "MST"), paged=False,
        description="법령용어에서 관련 조문 조회",
    ),
    "article_terms": EndpointSpec(
        "article_terms", "joRltLstrm", "lawService.do", ("연계용어", "법령용어"),
        required=("JO",), required_any=("ID", "query"),
        paged=False, description="법령 조문에서 관련 용어 조회(JO는 6자리)",
    ),
}


@dataclass(frozen=True)
class ParsedPage:
    total_count: int
    page: int
    display: int
    records: tuple[dict[str, object], ...]

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(self.total_count / max(1, self.display)))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _flat_fields(element: ET.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for node in element.iter():
        if node is element or list(node):
            continue
        value = (node.text or "").strip()
        if not value:
            continue
        key = _local(node.tag)
        if key in fields:
            fields[key] = f"{fields[key]} | {value}"
        else:
            fields[key] = value
    return fields


def _first(fields: Mapping[str, str], candidates: Iterable[str]) -> str:
    for name in candidates:
        value = fields.get(name, "").strip()
        if value:
            return value
    return ""


def catalog_identity(record: Mapping) -> str:
    """Keep official IDs intact while distinguishing lstrm spelling/catalog rows."""
    import hashlib
    import json
    kind, source_id = record['entity_type'], record['source_id']
    identity = f'moleg:{kind}:{source_id}'
    if kind == 'legal_terms':
        fields = record.get('fields', {})
        variant = [record['label'], fields.get('사전구분코드', ''),
                   fields.get('법령종류코드', '')]
        identity += ':' + hashlib.sha256(json.dumps(variant, ensure_ascii=False).encode()).hexdigest()
    return identity


def _record(spec: EndpointSpec, fields: dict[str, str]) -> dict[str, object]:
    source_id = _first(fields, (
        "법령용어ID", "법령용어일련번호", "용어ID", "일상용어ID", "MST",
        "법령일련번호", "법령ID",
    ))
    if not source_id:
        links = " ".join(value for key, value in fields.items() if "링크" in key)
        match = re.search(r"(?:[?&]|&amp;)MST=(\d+)", links, flags=re.IGNORECASE)
        if match:
            source_id = match.group(1)
    label = _first(fields, (
        "법령용어명", "법령용어명_한글", "법령용어", "용어명", "일상용어명", "일상용어",
        "관련법령용어명", "관련일상용어명", "법령명",
    ))
    definition = _first(fields, (
        "법령용어정의", "용어정의", "정의", "설명", "법령용어내용", "내용",
    ))
    return {
        "schema_version": "moleg-knowledge-record-v1",
        "entity_type": spec.key,
        "source_id": source_id,
        "label": label,
        "definition": definition,
        "hanja": _first(fields, ("법령용어한자", "법령용어명_한자", "용어한자", "한자")),
        "source": _first(fields, ("출처", "법령용어출처", "일상용어출처")),
        "dictionary_kind": _first(fields, ("법령용어사전구분", "법령용어코드명", "사전구분")),
        "fields": fields,
    }


def parse_xml_page(xml_text: str, spec: EndpointSpec, *, requested_page: int = 1,
                   requested_display: int = 100) -> ParsedPage:
    """응답 XML을 공통 레코드로 변환하고 API 오류 응답을 거부한다."""
    root = ET.fromstring(xml_text)
    if root.tag.lower().endswith('html'):
        raise ValueError('API가 XML 데이터 대신 HTML을 반환했습니다')
    root_fields = _flat_fields(root)
    error = _first(root_fields, ("resultMsg", "메시지", "message", "error"))
    result_code = _first(root_fields, ("resultCode", "코드", "code"))
    if error and result_code and result_code not in {"00", "0", "SUCCESS"}:
        raise RuntimeError(f"법제처 API 오류 {result_code}: {error}")

    tags = set(spec.item_tags)
    elements = [node for node in root.iter() if _local(node.tag) in tags]
    if _local(root.tag) in tags and not elements:
        elements = [root]
    if spec.key == "legal_term_detail":
        # Nested response containers are not additional definitions. Keep each
        # source-scoped record separately instead of flattening homonyms together.
        elements = [node for node in elements if not any(
            child is not node and _local(child.tag) in tags for child in node.iter())]
    parent_label = ""
    parent_context: dict[str, str] = {}
    if spec.key in {"legal_term_relations", "term_articles"}:
        parent = next((node for node in root.iter() if _local(node.tag) == "법령용어"), None)
        if parent is not None:
            parent_label = _first(_flat_fields(parent), ("법령용어명",))
    elif spec.key == "everyday_term_relations":
        parent = next((node for node in root.iter() if _local(node.tag) == "일상용어"), None)
        if parent is not None:
            parent_label = _first(_flat_fields(parent), ("일상용어명",))
    elif spec.key == "article_terms":
        parent = next((node for node in root.iter() if _local(node.tag) == "법령조문"), None)
        if parent is not None:
            parent_fields = _flat_fields(parent)
            for source, target in (
                ("법령명", "_기준법령명"),
                ("조번호", "_기준조번호"),
                ("조가지번호", "_기준조가지번호"),
            ):
                if parent_fields.get(source):
                    parent_context[target] = parent_fields[source]
    rows: list[dict[str, object]] = []
    for node in elements:
        fields = _flat_fields(node)
        if parent_label:
            fields["_기준용어명"] = parent_label
        fields.update(parent_context)
        rows.append(_record(spec, fields))
    records = tuple(rows)
    if spec.paged and not any(k in root_fields for k in ('totalCnt', 'totalCount', '총건수', '검색결과개수')):
        raise ValueError('목록 응답에 총건수가 없습니다')

    def number(names: tuple[str, ...], fallback: int) -> int:
        raw = _first(root_fields, names)
        match = re.search(r"\d+", raw)
        return int(match.group()) if match else fallback

    total = number(("totalCnt", "totalCount", "총건수", "검색결과개수"), len(records))
    page = number(("page", "pageNo", "페이지"), requested_page)
    display = number(("display", "numOfRows", "목록수"), requested_display)
    return ParsedPage(total_count=total, page=page, display=display, records=records)


class MolegKnowledgeClient:
    """인증정보를 산출물에 섞지 않는 직렬 법령지식 API 클라이언트."""

    def __init__(self, client: HttpClient, oc: str) -> None:
        if not oc.strip():
            raise ValueError("OC 인증값이 비어 있습니다")
        self.client = client
        self._oc = oc.strip()
        if hasattr(client, 'logger'):
            secrets = (self._oc, quote(self._oc, safe=''), quote_plus(self._oc))
            class Redact(logging.Filter):
                def filter(self, record):
                    message = record.getMessage()
                    for secret in secrets:
                        message = message.replace(secret, 'REDACTED')
                    record.msg, record.args = message, ()
                    return True
            client.logger.addFilter(Redact())

    def params(self, endpoint: str, values: Mapping[str, str] | None = None, *,
               page: int = 1, display: int = 100) -> dict[str, str]:
        spec = ENDPOINTS[endpoint]
        supplied = {str(k): str(v).strip() for k, v in (values or {}).items()
                    if str(v).strip()}
        allowed = set(spec.required) | set(spec.required_any) | set(spec.optional)
        unknown = sorted(set(supplied) - allowed)
        if unknown:
            raise ValueError(f"{endpoint}: 허용되지 않은 파라미터: {', '.join(unknown)}")
        missing = [name for name in spec.required if not supplied.get(name)]
        if missing:
            raise ValueError(f"{endpoint}: 필수 파라미터 누락: {', '.join(missing)}")
        if spec.required_any and not any(supplied.get(name) for name in spec.required_any):
            raise ValueError(
                f"{endpoint}: 다음 중 하나가 필요합니다: {', '.join(spec.required_any)}"
            )
        if endpoint == "article_terms" and supplied.get("JO") and not re.fullmatch(r"\d{6}", supplied["JO"]):
            raise ValueError("article_terms: JO는 6자리 숫자여야 합니다 (예: 000100)")
        if "relation" in supplied and supplied["relation"] in RELATION_CODES:
            supplied["relation"] = RELATION_CODES[supplied["relation"]]
        params = {"OC": self._oc, "target": spec.target, "type": "XML", **supplied}
        if spec.paged:
            if not 1 <= display <= 100:
                raise ValueError("display는 1~100이어야 합니다")
            params.update(page=str(page), display=str(display))
        return params

    def fetch(self, endpoint: str, values: Mapping[str, str] | None = None, *,
              page: int = 1, display: int = 100) -> tuple[str, ParsedPage]:
        spec = ENDPOINTS[endpoint]
        params = self.params(endpoint, values, page=page, display=display)
        try:
            response = self.client.get(spec.url, params=params, allow_redirects=False)
            if response.status_code != 200:
                raise RuntimeError('non-200')
        except Exception:
            raise RuntimeError(f'{endpoint}: API 요청 실패; 인증 및 제한 상태를 확인하십시오') from None
        # 검색 결과의 상세 링크가 OC를 되비추므로 원문 보존 전에 반드시 제거한다.
        safe_text = re.sub(
            r"(?i)((?:[?&]|&amp;)OC=)[^&<\"'\s]+", r"\1REDACTED", response.text
        )
        parsed = parse_xml_page(safe_text, spec, requested_page=page,
                                requested_display=display)
        return safe_text, parsed


def public_request_plan(endpoint: str, values: Mapping[str, str] | None = None, *,
                        display: int = 100) -> dict[str, object]:
    """OC를 포함하지 않는 검토/영수증용 호출 계획."""
    spec = ENDPOINTS[endpoint]
    supplied = {str(k): str(v) for k, v in (values or {}).items()}
    return {
        "endpoint": endpoint,
        "description": spec.description,
        "operation": spec.operation,
        "target": spec.target,
        "required": list(spec.required),
        "required_any": list(spec.required_any),
        "optional": list(spec.optional),
        "paged": spec.paged,
        "display": display if spec.paged else None,
        "parameters": supplied,
        "authentication": "OC from environment (never persisted)",
    }
