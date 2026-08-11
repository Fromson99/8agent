"""T-A6.2 코퍼스 빌드 — 원문 → 라우터 → doc.json → 발췌 물질화 → manifest (AGENT6 §2).

    corpus/raw/{ID}.pdf|txt (+ {ID}.meta.yaml)
            ↓ build()            router.route(파일, doc_type=...)
    corpus/structured/{ID}.doc.json      코어와 동일한 doc.json
            ↓ 용어 앵커 해소 / section 좌표 lookup
    corpus/excerpts/{ID}/{좌표}.txt      런타임이 로드하는 최종 형태
    corpus/manifest.json                 해소/미해소 — **이것이 빌드 게이트다**

## 이 파일이 하는 일과 하지 않는 일

규정 문서도 계약서와 같은 파이프라인을 탄다. 그래서 여기에는 파싱도 구조화도 없다 —
`router.route()` 를 부르고, 나온 doc.json 에서 **체크리스트가 요구한 좌표만** 골라
발췌 파일로 굳힌다. 요구되지 않은 조문은 뽑지 않는다. 발췌는 "미리 연결"(§0 원칙 1)의
결과물이지 조문 덤프가 아니다.

## 좌표를 묻는 두 가지 방법

    { doc: KSB,     section: 제21조/제1호 }        번호를 이미 아는 문서 — 그대로 짚는다
    { doc: KOFIA-R, term: 고령투자자 }              용어 앵커 — doc.json 에서 자리를 찾는다
    { doc: KSB,     term: 단정적 판단, section: 제21조 }  그 구역 **안에서** 용어를 찾는다

용어 앵커의 해소는 `basis.resolve_term()` 이 한다(제목 매칭 → fact 매칭, 여럿이면
AMBIGUOUS). manifest 의 basis 행에는 **무엇을 물었나(asked)** 와 **어디로 해소됐나
(resolved)** 를 둘 다 남긴다. 법 개정으로 조 번호가 밀리면 resolved 만 바뀌고 asked 는
그대로다 — 그게 이 표기의 값이다. 발췌 파일 이름도 asked 로 짓는다(같은 이유).

## manifest 가 게이트인 이유

런타임 LLM 은 금소법을 읽지 않는다 — 컴파일 타임에 물질화된 발췌만 읽는다. 그러므로
발췌가 없으면 그 항목은 **근거 없이 판정**하게 된다. 근거 없는 판정은 틀린 판정보다
나쁘다(무엇을 근거로 틀렸는지조차 남지 않는다). 그래서 미해소 basis 는 manifest 에
MISSING 으로 남고, 그 좌표를 가진 항목은 `basis.blocked_items()` 로 **활성화가 차단된다**.

## 조용한 실패를 막는 자리 셋

1. provenance 없는 원문은 거부한다. 출처를 모르는 근거로 판정하는 것이 가장 위험하다.
2. `verification: SYNTHETIC` 은 기본 거부다(`--allow-synthetic` 로만 통과). 합성 조문이
   진짜 법령처럼 유통되는 것이 이 시스템의 최악 실패다(공통계약 §4).
3. 조 번호 결번을 보고한다. 파싱이 제30조를 통째로 놓쳐도 doc.json 은 멀쩡해 보인다 —
   결번만이 그 누락을 드러낸다.

또한 이전 빌드가 남긴 발췌 중 이번에 다시 물질화되지 않은 것은 **지운다.** 코퍼스가
회수됐는데(manifest MISSING) 예전 발췌 파일이 남아 있으면 런타임이 그것을 읽어 버린다.

CLI:
    python -m agents.agent6.src.corpus_build --raw ... --out ... [--allow-synthetic]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.agent6.src import basis as basis_mod              # noqa: E402
from agents.agent6.src import schema                           # noqa: E402
from core import glossary as glossary_mod                      # noqa: E402
from core import router                                        # noqa: E402
from core.structurize import Document, Section                 # noqa: E402

DEFAULT_RAW = ROOT / "agents/agent6/corpus/raw"
DEFAULT_OUT = ROOT / "agents/agent6/corpus"
DEFAULT_ITEMS = ROOT / "agents/agent6/checklist/items"

# 원문으로 볼 확장자. .hwp 는 라우터가 못 받으므로 여기서도 받지 않는다(변환 후 투입 —
# 레포 루트 convert.py). .docx 는 라우터가 받는다 — 출처 표기는 pdf 처럼 사이드카로.
RAW_SUFFIXES = (".pdf", ".docx", ".txt", ".md")
# 원문이 아닌 것 — 사이드카와 사람용 문서.
NOT_RAW_STEMS = {"README", "readme"}

VERIFICATIONS = ("VERIFIED", "UNVERIFIED", "SYNTHETIC")
REQUIRED_PROVENANCE = ("doc_id", "title", "source", "collected", "verification")

# --- 상태 어휘 (manifest 스키마의 일부) ---------------------------------------
# 코퍼스: 왜 이 코퍼스의 발췌가 없는지가 전부 여기서 갈린다.
OK = "OK"                          # 구조화·발췌 완료
MISSING_SOURCE = "MISSING_SOURCE"  # 체크리스트가 요구하는데 raw 에 원문이 없다
UNROUTABLE = "UNROUTABLE"          # 원문은 있으나 등록부에 route 가 없다(구조가 다른 문서)
REJECTED = "REJECTED"              # provenance·verification 문제로 거부
QUARANTINED = "QUARANTINED"        # 적합도 게이트 미달 — 형식과 다른 문서다
SKIPPED = "SKIPPED"                # 원문은 있으나 어느 항목도 요구하지 않는다
# basis 좌표 — 어휘는 basis.py 가 정본이다(쓰는 쪽과 읽는 쪽이 갈리면 안 된다)
RESOLVED = basis_mod.RESOLVED
AMBIGUOUS = basis_mod.AMBIGUOUS    # 용어가 여러 구역에 걸린다 — 추측하지 않는다
MISSING = basis_mod.MISSING

_CIRCLED = {i + 1: chr(0x2460 + i) for i in range(20)}          # 1→①  … 20→⑳
_UNCIRCLED = {v: k for k, v in _CIRCLED.items()}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CorpusBuildError(Exception):
    """빌드 전체를 세울 만한 오류 (입력 디렉터리 부재 등)."""


class ProvenanceError(CorpusBuildError):
    """원문의 출처 표기가 없거나 규약과 다르다 — 해당 코퍼스는 거부된다."""


# ===========================================================================
# provenance — 이 원문이 어디서 왔는가
# ===========================================================================

@dataclass
class Provenance:
    """원문 한 개의 출처 표기.

    txt 는 첫머리 주석에, pdf 는 같은 이름의 `.meta.yaml` 사이드카에 적는다
    (pdf 안에는 주석을 넣을 자리가 없다). 규약은 corpus/raw/README.md 참조.
    """
    doc_id: str
    title: str
    source: str
    collected: str
    verification: str
    doc_type: Optional[str] = None      # 라우터에 넘길 doc_type. 없으면 자동 판별
    partial: bool = False               # 발췌본인가 — 조 결번이 정상인 문서
    strip_patterns: list[str] = field(default_factory=list)   # 발췌에서 지울 줄(정규식)
    origin: str = ""                    # 어디서 읽었는가 (사이드카 / 첫머리 주석)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def superseded(self) -> bool:
        """현행이 아닌 판본인가. 사이드카가 스스로 신고하는 값이다."""
        return bool(self.extra.get("superseded", False))

    def edition(self) -> str:
        """판본 한 줄 — 발췌 머리글에 남긴다. 낡은 근거로 판정하지 않기 위해서다."""
        bits = []
        for key, label in (("revision", ""), ("enforced", "시행 "), ("revision_date", "개정 ")):
            if self.extra.get(key):
                bits.append(f"{label}{self.extra[key]}")
        return " / ".join(bits)

    def dump(self) -> dict[str, Any]:
        d = {"id": self.doc_id, "title": self.title, "source": self.source,
             "collected": self.collected, "verification": self.verification}
        if self.doc_type:
            d["doc_type"] = self.doc_type
        if self.partial:
            d["partial"] = True
        if self.superseded:
            d["superseded"] = True
        if self.edition():
            d["edition"] = self.edition()
        return d


def _header_comments(path: Path) -> dict[str, Any]:
    """텍스트 원문 첫머리의 `# key: value` 주석 블록. 본문이 시작되면 멈춘다."""
    out: dict[str, Any] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ProvenanceError(f"{path}: 읽지 못했습니다 — {exc}") from exc
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if not s.startswith("#"):
            break                                   # 본문 시작 — 헤더는 여기까지
        body = s.lstrip("#").strip()
        if ":" in body:
            k, _, v = body.partition(":")
            out.setdefault(k.strip(), _scalar(v.strip()))
    return out


def _scalar(v: str) -> Any:
    """주석 값의 형. 목록·참/거짓만 YAML 로 읽고 나머지는 문자열 그대로 둔다.

    전부 YAML 로 읽으면 '합성: 금소법' 같은 제목이 매핑으로 변한다 — 사이드카와 달리
    첫머리 주석은 사람이 대충 쓰는 자리라 관대한 파서가 오히려 위험하다.
    """
    if v.startswith(("[", "{")) or v.lower() in ("true", "false"):
        try:
            return yaml.safe_load(v)
        except yaml.YAMLError:
            return v
    return v


def strip_provenance_header(text: str) -> Optional[str]:
    """첫머리 `# key: value` 출처 표기 블록을 본문에서 뗀다. 없으면 None.

    출처 표기는 **메타데이터지 문서 내용이 아니다.** 떼지 않고 라우팅하면 `# doc_id:`
    같은 줄이 구조화 요소로 조문 JSON 에 섞이고, 게이트에는 "형식이 설명하지 못한
    잔여"로 잡힌다 — 잔여 지표가 살아나면서 드러난 잠복 버그다.

    doc_id 가 든 블록만 뗀다 — 사이드카를 쓰는 md 원문이 진짜 제목(`# 제1장`)으로
    시작하는 경우를 건드리지 않기 위해서다. 경계도 보수적으로 잡는다: 선두의
    빈 줄·`# key: value` 꼴 줄까지만이고, 콜론 없는 `#` 줄(markdown 제목일 수 있다)을
    만나면 거기서 멈춘다. 덜 떼는 쪽의 비용(잔여 몇 줄)이 본문을 떼는 쪽보다 싸다.
    """
    lines = text.splitlines(keepends=True)
    end = 0
    has_doc_id = False
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            end = i + 1
            continue
        if not s.startswith("#") or ":" not in s.lstrip("#"):
            break
        if s.lstrip("#").strip().startswith("doc_id"):
            has_doc_id = True
        end = i + 1
    if not has_doc_id:
        return None
    return "".join(lines[end:])


def read_provenance(path: str | Path) -> Provenance:
    """원문 하나의 출처 표기를 읽고 검증한다. 어긋나면 ProvenanceError.

    사이드카가 있으면 그것이 정본이다(pdf 는 그 길밖에 없다). 텍스트 원문에 첫머리
    주석과 사이드카가 **둘 다** 있으면 doc_id 가 같아야 한다 — 두 출처가 다른 말을
    하는 원문은 어느 쪽도 믿을 수 없다.
    """
    p = Path(path)
    if not p.exists():
        raise ProvenanceError(f"원문을 찾을 수 없습니다: {p}")
    sidecar = p.with_suffix(".meta.yaml")
    inline: dict[str, Any] = {}
    if p.suffix.lower() in (".txt", ".md"):
        inline = _header_comments(p)

    if sidecar.exists():
        try:
            data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ProvenanceError(f"{sidecar}: YAML 을 읽지 못했습니다 — {exc}") from exc
        if not isinstance(data, dict):
            raise ProvenanceError(f"{sidecar}: 사이드카는 매핑이어야 합니다")
        origin = str(sidecar.relative_to(sidecar.parent))
        if inline and inline.get("doc_id") and inline["doc_id"] != data.get("doc_id"):
            raise ProvenanceError(
                f"{p.name}: 첫머리 주석의 doc_id '{inline['doc_id']}' 와 "
                f"사이드카의 '{data.get('doc_id')}' 가 다릅니다")
    elif inline:
        data, origin = inline, "첫머리 주석"
    else:
        raise ProvenanceError(
            f"{p.name}: 출처 표기가 없습니다. "
            f"텍스트면 첫머리에 '# doc_id: …' 주석 블록을, PDF·DOCX 면 "
            f"'{p.stem}.meta.yaml' 사이드카를 두세요 (corpus/raw/README.md §2). "
            f"필수 항목: {', '.join(REQUIRED_PROVENANCE)}")

    missing = [k for k in REQUIRED_PROVENANCE if not str(data.get(k) or "").strip()]
    if missing:
        raise ProvenanceError(f"{p.name}: 출처 표기에 {', '.join(missing)} 가 없습니다 "
                              f"({origin})")

    doc_id = str(data["doc_id"]).strip()
    if doc_id != p.stem:
        raise ProvenanceError(
            f"{p.name}: doc_id '{doc_id}' 가 파일명과 다릅니다. "
            f"코퍼스 ID = 파일명이어야 basis 좌표('{doc_id}/제19조')가 원문을 찾습니다")
    if not schema.DOC_ID_RE.match(doc_id):
        raise ProvenanceError(f"{p.name}: doc_id '{doc_id}' 는 코퍼스 ID 형식"
                              f"(대문자·숫자·-)이어야 합니다")
    verification = str(data["verification"]).strip().upper()
    if verification not in VERIFICATIONS:
        raise ProvenanceError(f"{p.name}: verification '{data['verification']}' 는 "
                              f"{VERIFICATIONS} 중 하나여야 합니다")
    collected = str(data["collected"]).strip()
    if isinstance(data["collected"], date):
        collected = data["collected"].isoformat()
    if not _DATE_RE.match(collected):
        raise ProvenanceError(f"{p.name}: collected '{collected}' 는 YYYY-MM-DD 여야 합니다")

    patterns = data.get("strip_patterns") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    for pat in patterns:
        try:
            re.compile(pat)
        except re.error as exc:
            raise ProvenanceError(f"{p.name}: strip_patterns '{pat}' 가 정규식이 아닙니다 — {exc}")

    return Provenance(
        doc_id=doc_id, title=str(data["title"]).strip(), source=str(data["source"]).strip(),
        collected=collected, verification=verification,
        doc_type=(str(data["doc_type"]).strip() if data.get("doc_type") else None),
        partial=bool(data.get("partial", False)),
        strip_patterns=[str(x) for x in patterns], origin=origin,
        extra={k: v for k, v in data.items() if k not in REQUIRED_PROVENANCE})


# ===========================================================================
# 좌표 해소 — 체크리스트의 좌표를 doc.json 의 section 에 맞춘다
# ===========================================================================

def coordinate_variants(section_path: str) -> list[list[str]]:
    """체크리스트 좌표 → doc.json 이 실제로 쓸 법한 경로 후보들.

    법령 원문의 항은 원문자로 온다("제19조/제②항"). 체크리스트는 사람이 쓰므로
    "제19조/제2항" 이라고 적는다. 그 간극을 여기서 메운다 — 형식 파일의 label 은
    str.format 이라 ②를 2로 바꿀 수 없고(statute.format.json 주석), 바꿔서도 안 된다
    (원문 표기를 잃는다). **해소하는 쪽이 정규화한다.**
    """
    parts = [p.strip() for p in section_path.split("/") if p.strip()]
    per_part: list[list[str]] = []
    for part in parts:
        cands = [part]
        m = re.fullmatch(r"제(\d{1,2})항", part)
        if m and int(m.group(1)) in _CIRCLED:
            cands.append(f"제{_CIRCLED[int(m.group(1))]}항")
        m = re.fullmatch(r"제([①-⑳])항", part)
        if m:
            cands.append(f"제{_UNCIRCLED[m.group(1)]}항")
        per_part.append(cands)

    out: list[list[str]] = [[]]
    for cands in per_part:
        out = [prev + [c] for prev in out for c in cands]
    return out


def find_sections(doc: Document, section_path: str) -> list[Section]:
    """좌표에 걸리는 section 들(문서 순서). 둘 이상이면 호출자가 시끄럽게 알린다."""
    wanted = [tuple(v) for v in coordinate_variants(section_path)]
    return [s for s in doc.sections if tuple(s.path) in wanted]


def _subtree(doc: Document, head: Section) -> list[Section]:
    """head 와 그 자손 전부를 문서 순서로.

    조 좌표의 발췌는 조 본문만으로는 쓸모가 없다 — 항·호·목이 요건의 알맹이다.
    자손은 path 접두사가 아니라 children 링크로 모은다. 같은 이름의 구역이 둘 있을 때
    (본칙 제1조 / 부칙 제1조#2) path 로는 갈리지 않기 때문이다.
    """
    order = {s.section_id: i for i, s in enumerate(doc.sections)}
    by_id = {s.section_id: s for s in doc.sections}
    seen: list[Section] = []
    stack = [head]
    while stack:
        sec = stack.pop()
        if sec in seen:
            continue
        seen.append(sec)
        stack.extend(by_id[c] for c in sec.children if c in by_id)
    return sorted(seen, key=lambda s: order[s.section_id])


def _label_of(sec: Section) -> str:
    """구역 머리 표기 — "제19조(설명의무)" / "제1호" / "가목"."""
    tail = sec.path[-1] if sec.path else sec.section_id
    title = sec.marker.get("title")
    return f"{tail}({title})" if title else tail


def citation_chain(doc: Document, head: Section) -> list[dict[str, Any]]:
    """구조화 문서의 **parent 링크를 거슬러 올라간 조문 경로**. 루트 → 이 구역 순서.

    한 마디도 지어내지 않는다 — `label` 은 구조화기가 활성화한 마커 표면형이고
    `title` 은 그 구역의 이름이다(`core/structure/title.py` 가 뽑은 것). 여기서 하는
    일은 이미 doc 안에 있는 **간선을 따라 걷는 것**뿐이다.

    왜 필요한가: 내부 좌표(`KSB/제21조/제1호`)는 파일을 찾는 키일 뿐 인용이 아니다.
    판정자(LLM)에게 `KSB` 는 아무 뜻도 없는 글자이고, `제1호` 만으로는 무엇의 제1호인지
    알 수 없다. 호는 자기 조를 알아야 인용이 된다.
    """
    by_id = {s.section_id: s for s in doc.sections}
    chain: list[Section] = []
    cur: Optional[Section] = head
    seen: set[str] = set()
    while cur is not None and cur.section_id not in seen:
        seen.add(cur.section_id)
        chain.append(cur)
        cur = by_id.get(cur.parent) if cur.parent else None
    out: list[dict[str, Any]] = []
    for sec in reversed(chain):
        # 기본 구역(`본문` 같은 것)은 마커가 연 것이 아니므로 인용이 아니다.
        if sec.marker.get("kind") == "default":
            continue
        out.append({"section_id": sec.section_id,
                    "label": sec.path[-1] if sec.path else sec.section_id,
                    "title": sec.marker.get("title") or ""})
    return out


def citation_siblings(doc: Document, head: Section) -> list[str]:
    """같은 부모를 공유하는 형제 구역의 표면형 — children 간선에서 그대로 읽는다.

    `제21조 제1호` 를 근거로 줄 때 그 조에 호가 몇 개인지 함께 말해 주면, 판정자가
    "이 금지행위 하나만 있다" 고 오해하지 않는다.
    """
    if not head.parent:
        return []
    parent = doc.section(head.parent)
    if parent is None:
        return []
    out = []
    for cid in parent.children:
        sec = doc.section(cid)
        if sec is not None:
            out.append(sec.path[-1] if sec.path else cid)
    return out


def citation_of(doc: Document, head: Section) -> str:
    """조문 경로를 사람이 인용하는 한 줄로. `제21조(부당권유행위 금지) 제1호`."""
    return " ".join(
        f"{n['label']}({n['title']})" if n["title"] else n["label"]
        for n in citation_chain(doc, head))


def render_excerpt(doc: Document, head: Section, *,
                   strip: Iterable[re.Pattern] = ()) -> tuple[str, dict[str, Any]]:
    """구역 하나(자손 포함)를 사람이 읽는 발췌문으로. 반환: (본문, 통계).

    페이지 장식 제거는 두 층이다:
      · 파서가 page_header/page_footer 로 분류한 요소 — 문서 구조 신호이므로 **자동 제거**.
      · 그 밖의 반복 머리글(예: "법제처 7 국가법령정보센터"는 docling 이 본문으로 본다) —
        무엇이 장식인지는 문서마다 다르므로 코드가 정하지 않는다. 사이드카의
        `strip_patterns` 가 정한다. 미지정분은 `noise_candidates` 로 시끄럽게 보고한다.
    """
    lines: list[str] = []
    dropped = 0
    base = len(head.path)
    subtree = _subtree(doc, head)
    for sec in subtree:
        depth = max(0, len(sec.path) - base)
        indent = "  " * depth
        head_line = f"{indent}{_label_of(sec)}" if sec is not head else _label_of(sec)
        body: list[str] = []
        for item in sec.content:
            if item.get("type") == "table":
                body.append("[표]")
                continue
            text = (item.get("text") or "").strip()
            if not text:
                continue
            if item.get("element_type") in ("page_header", "page_footer"):
                dropped += 1
                continue
            if any(pat.search(text) for pat in strip):
                dropped += 1
                continue
            body.append(text)
        if body:
            lines.append(f"{head_line} {body[0]}")
            lines.extend(f"{indent}  {b}" for b in body[1:])
        else:
            lines.append(head_line)
    return "\n".join(lines), {"sections": len(subtree), "dropped": dropped}


def noise_candidates(doc: Document, *, min_hits: int = 5, max_chars: int = 40,
                     strip: Iterable[re.Pattern] = ()) -> list[dict[str, Any]]:
    """페이지 장식으로 보이는 반복 줄. **지우지는 않는다 — 보고만 한다.**

    "법제처 7 국가법령정보센터"처럼 페이지 번호만 다른 줄을 잡으려면 숫자를 지운 뒤
    세어야 한다. 그런데 같은 규칙이 "삭제 <2020. 3. 24.>" 같은 **진짜 본문**도 잡는다.
    그래서 자동 제거하지 않는다 — 사람이 사이드카에 strip_patterns 로 확정한다.
    """
    from collections import Counter
    counter: Counter[str] = Counter()
    sample: dict[str, str] = {}
    for sec in doc.sections:
        for item in sec.content:
            text = (item.get("text") or "").strip()
            if not text or len(text) > max_chars or item.get("type") == "table":
                continue
            if item.get("element_type") in ("page_header", "page_footer"):
                continue                   # 이미 자동 제거된다 — 다시 세면 헛경보가 된다
            if any(pat.search(text) for pat in strip):
                continue
            key = re.sub(r"\d+", "#", text)
            counter[key] += 1
            sample.setdefault(key, text)
    return [{"shape": k, "sample": sample[k], "hits": n,
             "suggest_pattern": "^" + re.escape(sample[k]).replace(r"\ ", r"\s") + "$"
             if not re.search(r"\d", sample[k]) else
             "^" + re.sub(r"\d+", r"\\d+", re.escape(sample[k])).replace(r"\ ", r"\s") + "$"}
            for k, n in counter.most_common() if n >= min_hits]


# ===========================================================================
# 빌드
# ===========================================================================

def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _basis_term(b: Any) -> Optional[str]:
    """basis 의 용어 앵커. 스키마에 term 필드가 없으면 **조용히 넘어가지 않는다.**

    pydantic 은 모르는 키를 기본으로 버린다 — 체크리스트에 `term: 고령투자자` 를 적었는데
    스키마가 그 필드를 모르면 용어 앵커가 로드 시점에 사라지고, 빌드는 "section 좌표가
    없다"는 엉뚱한 사유를 내며 항목을 차단한다. 그 오진을 여기서 막는다.
    """
    if "term" not in type(b).model_fields:
        raise CorpusBuildError(
            "schema.Basis 에 term 필드가 없습니다 — 체크리스트의 용어 앵커(term:)가 "
            "로드 시점에 조용히 버려집니다. agents/agent6/src/schema.py 의 Basis 에 "
            "term 을 선언하세요 (공통계약 '새 basis 표기')")
    return b.term


def _wanted(items: list[schema.ChecklistItem]) -> dict[str, dict[str, Any]]:
    """체크리스트가 요구하는 basis 좌표 표. **요구가 빌드를 이끈다.**

    요구되지 않은 조문은 뽑지 않는다(§2: 발췌는 "미리 연결"의 결과물이다). 꺼진 항목은
    요구에서 빠진다 — 쓰지 않는 항목 때문에 법령을 수집할 이유는 없다.

    좌표는 두 모양이다. `{doc, section}` 은 자리를 직접 짚은 것이고, `{doc, term}` 은
    용어로 자리를 **묻는** 것이다. 둘을 함께 적으면 "그 구역 안에서 그 용어"다.
    표에는 물은 그대로(`coord`) 담고, 어디로 갔는지는 해소 단계가 채운다.
    """
    table: dict[str, dict[str, Any]] = {}
    for item in items:
        if not item.enabled:
            continue
        for b in item.basis:
            rec = table.setdefault(b.coordinate(), {
                "coord": b.coordinate(), "doc": b.doc, "section": b.section,
                "term": _basis_term(b), "wanted_by": [], "notes": []})
            rec["wanted_by"].append(item.id)
            if b.note and b.note not in rec["notes"]:
                rec["notes"].append(b.note)
    return dict(sorted(table.items()))


def _article_check(doc: Document) -> dict[str, Any]:
    """조 번호의 결번 — 파싱 누락이 조용히 지나가지 않게 한다(T-A6.2 d).

    doc.json 은 제30조를 통째로 놓쳐도 멀쩡해 보인다. 결번만이 그것을 드러낸다.
    """
    nums: set[int] = set()
    branches: list[str] = []
    for sec in doc.sections:
        m = sec.marker
        if m.get("kind") != "regex":
            continue
        no = str(m.get("no") or "")
        if m.get("id") == "조" and no.isascii() and no.isdigit():
            nums.add(int(no))
        elif m.get("id") == "가지조":
            branches.append(sec.path[-1])
    if not nums:
        return {"count": 0, "range": None, "gaps": [], "branches": branches,
                "note": "조 마커가 하나도 검출되지 않았습니다"}
    lo, hi = min(nums), max(nums)
    gaps = [n for n in range(lo, hi + 1) if n not in nums]
    return {"count": len(nums), "range": [lo, hi], "gaps": gaps,
            "branches": sorted(set(branches))}


def _excerpt_path(out_dir: Path, coord: str) -> Path:
    """경로 규약은 basis.py 가 정한다 — 쓰는 쪽과 읽는 쪽이 갈리면 안 된다.

    이름은 **물은 좌표**로 짓는다. 개정으로 조 번호가 밀려도 런타임은 같은 파일을
    찾는다 — 용어 앵커를 두는 이유가 그것이다.
    """
    return basis_mod.excerpt_path(coord, corpus_dir=out_dir)


def _write_excerpt(path: Path, body: str, prov: Provenance, coord: str,
                   section_id: str, wanted_by: list[str],
                   anchor: Optional[basis_mod.Anchor] = None,
                   citation: str = "", siblings: Iterable[str] = ()) -> int:
    """발췌 파일 하나. 머리글은 `#` 주석이며 basis.load_excerpt() 가 걷어낸다.

    판본을 머리글에 박는 이유: 낡은 근거로 "적법"을 선언하는 것이 이 시스템에서 가장
    위험한 실패다. 발췌만 떼어 봐도 어느 판본인지 알 수 있어야 한다.

    용어 앵커면 **무엇을 물었고 어디로 갔는지**를 함께 남긴다. 개정 후 발췌를 다시
    뽑았을 때 좌표가 어디로 옮겨갔는지가 이 두 줄에서 바로 보인다.
    """
    head = [f"# 좌표: {coord}"]
    if anchor is not None:
        head.append(f"# 용어 앵커: {anchor.term} → {section_id} ({anchor.via} 매칭)")
    head += [f"# section_id: {section_id}"]
    if citation:
        # 런타임이 프롬프트에 싣는 줄이다 — `KSB/제21조/제1호` 가 아니라
        # `금융소비자 보호에 관한 법률 제21조(부당권유행위 금지) 제1호` 로 인용된다.
        # 구조화 문서의 parent 간선에서 걸어 나온 것이다(`citation_chain`).
        head.append(f"# 조문: {citation}")
    sibs = [s for s in siblings]
    if len(sibs) > 1:
        head.append(f"# 형제 구역: {', '.join(sibs)}")
    head += [f"# 코퍼스: {prov.title} — {prov.source}"]
    if prov.edition():
        head.append(f"# 판본: {prov.edition()}")
    head += [f"# verification: {prov.verification}",
             f"# 수집: {prov.collected}",
             f"# 요구 항목: {', '.join(wanted_by)}",
             f"# 물질화: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
             f" by agents.agent6.src.corpus_build"]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(head) + "\n\n" + body.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return len(body.strip())


def build(raw_dir: str | Path = DEFAULT_RAW, out_dir: str | Path = DEFAULT_OUT,
          items: str | Path | list[schema.ChecklistItem] = DEFAULT_ITEMS, *,
          allow_synthetic: bool = False) -> dict[str, Any]:
    """원문을 구조화하고 요구된 좌표만 발췌로 굳힌 뒤 manifest 를 돌려준다.

    반환값이 곧 `corpus/manifest.json` 의 내용이다(파일로도 쓴다).
    """
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    if not raw_dir.is_dir():
        raise CorpusBuildError(f"원문 디렉터리가 없습니다: {raw_dir}")
    items_dir = None
    if isinstance(items, (str, Path)):
        items_dir, items = Path(items), schema.load_items(items, warn=False)

    wanted = _wanted(items)
    wanted_docs: dict[str, list[str]] = {}
    for rec in wanted.values():
        wanted_docs.setdefault(rec["doc"], []).extend(rec["wanted_by"])

    # --- 원문 훑기 (요구 여부와 무관하게 provenance 는 전부 검사한다) -------------
    raws: dict[str, Path] = {}
    corpora: list[dict[str, Any]] = []
    provs: dict[str, Provenance] = {}
    claims: dict[str, list[tuple[Path, Provenance]]] = {}
    for p in sorted(raw_dir.iterdir()):
        if p.is_dir() or p.suffix.lower() not in RAW_SUFFIXES or p.stem in NOT_RAW_STEMS:
            continue
        if p.name.endswith(".meta.yaml"):
            continue
        try:
            prov = read_provenance(p)
        except ProvenanceError as exc:
            corpora.append({"id": p.stem, "raw": _rel(p), "status": REJECTED,
                            "reason": str(exc), "warnings": [],
                            "wanted_by": sorted(set(wanted_docs.get(p.stem, [])))})
            continue
        claims.setdefault(prov.doc_id, []).append((p, prov))

    for doc_id, cs in claims.items():
        if len(cs) == 1:
            raws[doc_id], provs[doc_id] = cs[0][0], cs[0][1]
            continue
        # 어느 원문이 근거인지 정해지지 않았다. 하나를 고르는 것(예: 이름순 첫 번째)이
        # 가장 위험하다 — 아무도 그 선택을 보지 못한 채 판정이 나간다. 전부 거부한다.
        names = ", ".join(_rel(p) for p, _ in cs)
        for p, _prov in cs:
            corpora.append({"id": doc_id, "raw": _rel(p), "status": REJECTED, "warnings": [],
                            "reason": f"코퍼스 ID '{doc_id}' 를 {len(cs)}개 파일이 주장합니다 "
                                      f"({names}) — 어느 원문이 근거인지 정해지지 않습니다",
                            "wanted_by": sorted(set(wanted_docs.get(doc_id, [])))})

    # --- 코퍼스별 구조화 --------------------------------------------------------
    built: dict[str, Document] = {}
    glossaries: dict[str, Any] = {}     # 용어 앵커 해소에 별칭까지 쓰려면 필요하다
    for doc_id, p in raws.items():
        prov = provs[doc_id]
        rec: dict[str, Any] = {"id": doc_id, **prov.dump(), "raw": _rel(p),
                               "wanted_by": sorted(set(wanted_docs.get(doc_id, []))),
                               "warnings": []}
        corpora.append(rec)

        if doc_id not in wanted_docs:
            rec["status"] = SKIPPED
            rec["reason"] = "어느 체크리스트 항목도 이 코퍼스를 근거로 삼지 않습니다 — 구조화하지 않았습니다"
            continue
        if prov.verification == "SYNTHETIC" and not allow_synthetic:
            rec["status"] = REJECTED
            rec["reason"] = ("verification: SYNTHETIC — 합성 코퍼스는 운영 빌드에서 거부됩니다 "
                             "(테스트는 --allow-synthetic)")
            continue
        if prov.verification == "UNVERIFIED":
            rec["warnings"].append(
                "verification: UNVERIFIED — 사람이 원문과 대조하지 않았습니다. "
                "판정 근거로 쓰이기 전에 검수하세요")
        if prov.superseded:
            # 낡은 판본으로 "적법"을 선언하는 것은 이 시스템에서 가장 위험한 실패다.
            rec["warnings"].append(
                "superseded: true — 현행 판본이 아닙니다. 이 발췌를 근거로 오늘의 판매를 "
                "판정하면 안 됩니다 (현행본을 수집해 교체하세요)")

        # 출처 표기 블록은 문서 내용이 아니다 — 떼고 라우팅한다. 같은 파일명으로
        # out/stripped/ 에 두어 doc.json 의 source_file 이 바뀌지 않게 한다.
        route_input = p
        if p.suffix.lower() in (".txt", ".md"):
            from core.parse_adapter import decode_text
            body = strip_provenance_header(decode_text(p))
            if body is not None:
                sp = out_dir / "stripped" / p.name
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(body, encoding="utf-8")
                route_input = sp
        try:
            routed = router.route(route_input, doc_type=prov.doc_type)
        except router.RoutingError as exc:
            rec["status"] = UNROUTABLE
            rec["reason"] = str(exc)
            continue
        rec["doc_type"] = routed.doc_type
        # 용어집은 라우터가 실어 준 것을 그대로 쓴다 — 여기서 다시 싣지 않는다.
        # 다시 실으면 "어느 용어집을 쓸지 에이전트가 고른다"가 되어 등록부 강제가 뚫린다.
        glossaries[doc_id] = routed.glossary
        gp = routed.route.glossary_path()
        if gp:
            rec["glossary"] = _rel(gp)
        rec["elements"] = len(routed.parsed.elements)
        rec["sections"] = len(routed.doc.sections)
        rec["residual"] = len(routed.doc.residual)
        rec["fitness"] = {"passed": routed.fitness.passed,
                          "score": round(routed.fitness.score, 3)}
        rec["articles"] = _article_check(routed.doc)

        structured = out_dir / "structured" / f"{doc_id}.doc.json"
        structured.parent.mkdir(parents=True, exist_ok=True)
        structured.write_text(
            json.dumps(routed.doc.dump(), ensure_ascii=False, indent=1), encoding="utf-8")
        rec["structured"] = _rel(structured)

        if routed.quarantined:
            # 형식과 다른 문서를 그럴듯한 발췌로 내보내는 것이 가장 위험하다(SPEC §3.4).
            rec["status"] = QUARANTINED
            rec["reason"] = (f"적합도 {routed.fitness.score:.0%} < 임계 "
                             f"{routed.route.threshold:.0%} — 형식이 맞지 않습니다. "
                             f"{routed.fitness.warnings[0] if routed.fitness.warnings else ''}")
            continue

        rec["status"] = OK
        rec["reason"] = None
        built[doc_id] = routed.doc

        gaps = rec["articles"]["gaps"]
        if gaps and not prov.partial:
            rec["warnings"].append(
                f"조 번호 결번 {len(gaps)}개: {gaps[:20]}{' …' if len(gaps) > 20 else ''} — "
                f"파싱이 조문을 놓쳤을 수 있습니다 (발췌본이면 사이드카에 partial: true)")
        elif gaps:
            rec["warnings"].append(f"조 번호 결번 {len(gaps)}개 (partial 선언됨 — 발췌본)")
        strip = [re.compile(x) for x in prov.strip_patterns]
        cands = noise_candidates(routed.doc, strip=strip)
        if cands:
            rec["noise_candidates"] = cands[:10]
            rec["warnings"].append(
                f"반복 머리글로 보이는 줄 {len(cands)}종이 본문에 섞여 있습니다 — "
                f"발췌를 더럽힙니다. {raw_dir.name}/{doc_id}.meta.yaml 의 strip_patterns 로 "
                f"확정하세요 (예: {cands[0]['suggest_pattern']})")

    # --- 발췌 물질화 ------------------------------------------------------------
    excerpt_root = out_dir / "excerpts"
    stale = {p for p in excerpt_root.rglob("*.txt")} if excerpt_root.exists() else set()
    by_id = {c["id"]: c for c in corpora}
    basis_rows: list[dict[str, Any]] = []

    for coord, rec in wanted.items():
        doc_id, section_path, term = rec["doc"], rec["section"], rec["term"]
        # asked/resolved 를 둘 다 남기는 것이 이 설계의 값이다 — 법 개정으로 조 번호가
        # 바뀌면 resolved 만 바뀌고 asked 는 그대로여야 한다.
        row: dict[str, Any] = {"coord": coord, "asked": coord, "resolved": None,
                               "doc": doc_id, "section": section_path, "term": term,
                               "wanted_by": sorted(set(rec["wanted_by"])),
                               "status": MISSING, "reason": None,
                               "excerpt": None, "chars": 0, "section_id": None}
        basis_rows.append(row)

        crec = by_id.get(doc_id)
        if crec is None:
            row["reason"] = f"코퍼스 '{doc_id}' 의 원문이 {_rel(raw_dir)} 에 없습니다 (수집 대기)"
            corpora.append({"id": doc_id, "status": MISSING_SOURCE, "raw": None,
                            "wanted_by": sorted(set(wanted_docs.get(doc_id, []))),
                            "reason": row["reason"], "warnings": []})
            by_id[doc_id] = corpora[-1]
            continue
        if crec["status"] != OK:
            row["reason"] = f"코퍼스 '{doc_id}' 상태 {crec['status']}: {crec.get('reason') or ''}"
            continue
        if not section_path and not term:
            # 좌표가 아직 확정되지 않은 basis — 원문은 있어도 어디를 인용할지 모른다.
            row["reason"] = ("basis 에 용어(term)도 조문 좌표(section)도 없습니다 — "
                             "체크리스트에서 근거의 자리를 확정해야 발췌가 물질화됩니다")
            continue

        doc = built[doc_id]
        head: Optional[Section] = None
        anchor: Optional[basis_mod.Anchor] = None

        # section 이 있으면 먼저 그 좌표를 찾는다. term 이 함께 있으면 그 구역은
        # **범위**이고, 없으면 그 구역 자체가 답이다.
        hits: list[Section] = []
        if section_path:
            hits = find_sections(doc, section_path)
            if not hits:
                row["reason"] = _lookup_failure(doc_id, section_path)
                crec["warnings"].append(f"{coord}: {row['reason']}")
                continue
            if len(hits) > 1 and not term:
                crec["warnings"].append(
                    f"{coord}: section 이 {len(hits)}개 걸립니다 "
                    f"({', '.join(h.section_id for h in hits)}) — 첫 번째를 씁니다")
            if not term:
                head = hits[0]

        if term:
            scope = (basis_mod.subtree_ids(doc, [h.section_id for h in hits])
                     if hits else None)
            anchor = basis_mod.resolve_term(doc, term, scope=scope,
                                            glossary=glossaries.get(doc_id))
            row["anchor"] = anchor.dump()
            for w in anchor.warnings:
                crec["warnings"].append(f"{coord}: {w}")
            if not anchor.resolved:
                row["status"] = anchor.status          # AMBIGUOUS 또는 MISSING
                row["reason"] = anchor.reason
                crec["warnings"].append(f"{coord}: {anchor.reason}")
                continue
            head = doc.section(anchor.section_id)
            if head is None:                            # doc.json 과 해소기가 어긋났다
                row["reason"] = (f"해소된 section '{anchor.section_id}' 를 doc.json 에서 "
                                 f"찾지 못했습니다 — 코퍼스 빌드가 반쪽입니다")
                crec["warnings"].append(f"{coord}: {row['reason']}")
                continue

        prov = provs[doc_id]
        body, stats = render_excerpt(doc, head,
                                     strip=[re.compile(x) for x in prov.strip_patterns])
        if not body.strip():
            row["reason"] = f"section '{head.section_id}' 의 본문이 비어 있습니다"
            crec["warnings"].append(f"{coord}: {row['reason']}")
            continue
        path = _excerpt_path(out_dir, coord)
        # 인용 경로는 구조화 문서의 간선에서 걸어 나온다 — manifest 에는 마디째,
        # 발췌 머리글에는 한 줄로 굳힌다. 둘이 같은 함수에서 나오므로 어긋나지 않는다.
        chain = citation_chain(doc, head)
        siblings = citation_siblings(doc, head)
        citation = citation_of(doc, head)
        row["chars"] = _write_excerpt(path, body, prov, coord, head.section_id,
                                      row["wanted_by"], anchor,
                                      citation=citation, siblings=siblings)
        row["excerpt"] = _rel(path)
        row["section_id"] = head.section_id
        row["citation"] = f"{prov.title} {citation}".strip()
        row["citation_path"] = chain
        row["siblings"] = siblings
        row["resolved"] = f"{doc_id}/{head.section_id}"
        row["status"] = RESOLVED
        row["sections"] = stats["sections"]
        stale.discard(path)
        crec["excerpts"] = crec.get("excerpts", 0) + 1

    # 이번에 다시 물질화되지 않은 발췌는 지운다 — 회수된 코퍼스의 잔재가 런타임에
    # 읽히면 manifest 가 MISSING 이라고 말해도 소용이 없다.
    removed = []
    for p in sorted(stale):
        p.unlink()
        removed.append(_rel(p))

    # --- manifest ---------------------------------------------------------------
    resolved = sum(1 for r in basis_rows if r["status"] == RESOLVED)
    ambiguous = sum(1 for r in basis_rows if r["status"] == AMBIGUOUS)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder": "agents.agent6.src.corpus_build",
        "raw_dir": _rel(raw_dir), "out_dir": _rel(out_dir),
        "checklist": {"dir": _rel(items_dir) if items_dir else None,
                      "items": len(items),
                      "enabled": sum(1 for i in items if i.enabled)},
        "allow_synthetic": allow_synthetic,
        "corpora": sorted(corpora, key=lambda c: c["id"]),
        "basis": basis_rows,
        "removed_excerpts": removed,
        # missing 은 "해소되지 않은 좌표 전부"다(AMBIGUOUS 포함) — --strict 게이트와
        # blocked_items 가 같은 수를 봐야 한다.
        "stats": {"resolved": resolved, "missing": len(basis_rows) - resolved,
                  "ambiguous": ambiguous,
                  "anchored": sum(1 for r in basis_rows if r.get("term")),
                  "corpora": len(corpora),
                  "corpora_ok": sum(1 for c in corpora if c["status"] == OK)},
    }
    manifest["blocked_items"] = basis_mod.blocked_items(items, manifest)
    manifest["stats"]["blocked_items"] = len(manifest["blocked_items"])

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def _lookup_failure(doc_id: str, section_path: str) -> str:
    """좌표를 못 찾았을 때 무엇을 고치면 되는지까지 말한다."""
    base = f"'{doc_id}' 의 doc.json 에 좌표 '{section_path}' 가 없습니다"
    if re.search(r"(^|/)제1항$", section_path):
        return (base + " — 법령 원문에서 제1항(①)은 조 제목 줄에 붙어 와 별도 section 이 "
                       "되지 못합니다. 조 좌표로 인용하세요(그 조의 발췌에 ① 본문이 들어갑니다)")
    return base + " — 조문 번호가 맞는지, 원문에 그 조항이 실제로 있는지 확인하세요"


# ===========================================================================
# 보고 — 미해소는 반드시 눈에 띄어야 한다
# ===========================================================================

def render_report(manifest: dict[str, Any]) -> str:
    lines: list[str] = []
    st = manifest["stats"]
    lines.append(f"코퍼스 빌드  {manifest['raw_dir']} → {manifest['out_dir']}"
                 f"  ({manifest['generated_at']})")
    lines.append("")
    lines.append("[코퍼스]")
    for c in manifest["corpora"]:
        mark = "OK " if c["status"] == OK else "!  "
        detail = ""
        if c["status"] == OK:
            a = c.get("articles") or {}
            rng = f"제{a['range'][0]}조~제{a['range'][1]}조" if a.get("range") else "조 없음"
            detail = (f"section {c['sections']}, 잔여 {c['residual']}, {rng}, "
                      f"결번 {len(a.get('gaps') or [])}, 적합도 {c['fitness']['score']:.0%}, "
                      f"발췌 {c.get('excerpts', 0)}")
        else:
            detail = c.get("reason") or ""
        lines.append(f"  {mark}{c['id']:<12} {c['status']:<15} {detail}")
        for w in c.get("warnings") or []:
            lines.append(f"       · {w}")

    lines.append("")
    anchored = st.get("anchored", 0)
    lines.append(f"[basis 좌표]  해소 {st['resolved']} / 미해소 {st['missing']}"
                 f" (그중 모호 {st.get('ambiguous', 0)})  ·  용어 앵커 {anchored}개")
    for r in manifest["basis"]:
        if r["status"] != RESOLVED:
            continue
        # 물은 것과 해소된 곳을 함께 보인다 — 개정 후 어디로 옮겨갔는지가 여기서 보인다.
        moved = (f" → {r['resolved']}" if r.get("resolved")
                 and r["resolved"] != r["coord"] else "")
        lines.append(f"  OK {r['coord']}{moved}")
        lines.append(f"       {r['chars']:>6}자  {(r.get('anchor') or {}).get('via', '좌표')} 매칭"
                     f"  ← {', '.join(r['wanted_by'])}")
    missing = [r for r in manifest["basis"] if r["status"] != RESOLVED]
    if missing:
        lines.append("")
        lines.append(f"  ##### 미해소 basis {len(missing)}개 — 아래 좌표에는 근거 발췌가 없습니다 #####")
        for r in missing:
            lines.append(f"  !! [{r['status']}] {r['coord']} ← {', '.join(r['wanted_by'])}")
            lines.append(f"       {r['reason']}")
            for c in ((r.get("anchor") or {}).get("candidates") or [])[:8]:
                title = f"  {c['title'][:44]}" if c.get("title") else ""
                lines.append(f"         후보 {c['section_id']}{title}")

    blocked = manifest.get("blocked_items") or {}
    lines.append("")
    if blocked:
        lines.append(f"  ##### 활성화 차단 항목 {len(blocked)}개 — 근거 없이 판정하지 않는다 #####")
        for item_id, reason in sorted(blocked.items()):
            lines.append(f"  !! {item_id}  {reason}")
    else:
        lines.append("  차단 항목 없음 — 모든 항목의 basis 가 해소됐습니다")
    if manifest.get("removed_excerpts"):
        lines.append("")
        lines.append(f"  [정리] 이번 빌드에서 물질화되지 않아 지운 발췌 "
                     f"{len(manifest['removed_excerpts'])}개")
        for p in manifest["removed_excerpts"][:10]:
            lines.append(f"       - {p}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m agents.agent6.src.corpus_build",
        description="근거 코퍼스 빌드 — 원문을 구조화하고 체크리스트가 요구한 좌표만 발췌로 굳힌다")
    ap.add_argument("--raw", default=str(DEFAULT_RAW), help="원문 디렉터리")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="산출 디렉터리 (structured/ excerpts/ manifest.json 이 여기 생긴다)")
    ap.add_argument("--items", default=str(DEFAULT_ITEMS), help="체크리스트 항목 디렉터리")
    ap.add_argument("--allow-synthetic", action="store_true",
                    help="verification: SYNTHETIC 코퍼스를 통과시킨다 (테스트 전용)")
    ap.add_argument("--strict", action="store_true",
                    help="미해소 basis 가 하나라도 있으면 실패로 끝낸다 (CI 게이트)")
    args = ap.parse_args(argv)

    manifest = build(args.raw, args.out, args.items, allow_synthetic=args.allow_synthetic)
    print(render_report(manifest))
    if args.strict and manifest["stats"]["missing"]:
        print(f"\n--strict: 미해소 basis {manifest['stats']['missing']}개 — 빌드 실패")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
