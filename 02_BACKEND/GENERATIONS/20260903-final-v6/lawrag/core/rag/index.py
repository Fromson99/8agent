"""검색 색인 — 이미 구조화된 결과에서 그대로 세운다.

DB 서버가 없다. 원본(DELTAFlow RAG)은 Postgres `glossary_index` 라는 평평한
표(값 하나가 한 줄)를 검색했다. 여기서는 그 표를 **메모리에서** 만든다 —
재료는 구조화 산출(`result.json`)의 마디 제목과, 사람이 더한 용어
(`glossary.json`)다. 문서 몇십 건 규모에서 이걸 서버로 만드는 것은 과잉이다.

색인 한 줄(Entry)은 "이 표면형이 이 좌표에 있다"다. 검색(search.py)은 이
줄들을 훑고, 좌표(doc_id·node·block·page)로 곧장 되돌아간다 — 좌표 없는
매칭은 근거가 될 수 없다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Mapping, Optional

from lawrag.core.rag.content_snapshot import (
    ArtifactProvenance,
    ContentSnapshot,
    ContentSnapshotError,
    current_content_snapshot,
)
from lawrag.platform.paths import runtime_path

log = logging.getLogger("lawrag.core.rag.index")

LEXICAL_IDENTITY_SCHEMA = "rag-lexical-index-identity-v1"


def _snapshot_adapter_enabled() -> bool:
    """Read the independently promoted adapter switch without import cycles."""

    from lawrag.core.rag import switches as switches_mod

    return switches_mod.is_on("sourceset_content_snapshot")


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable_regular_bytes(path: Path) -> bytes:
    """Read one release artifact without following or racing a replacement."""

    try:
        before = path.lstat()
    except OSError as exc:
        raise ContentSnapshotError(
            f"cannot stat lexical identity artifact {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContentSnapshotError("lexical identity artifact must be a regular file")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ContentSnapshotError("lexical identity reads require no-follow opens")
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow
        )
    except OSError as exc:
        raise ContentSnapshotError(
            f"cannot safely open lexical identity artifact: {exc}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        identity = lambda info: (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise ContentSnapshotError("lexical identity changed before read")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if identity(opened) != identity(os.fstat(descriptor)):
            raise ContentSnapshotError("lexical identity changed during read")
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _load_lexical_identity(snapshot: ContentSnapshot) -> Mapping[str, object]:
    binding = snapshot.index_binding("lexical")
    path = snapshot.runtime_artifact_path("index.lexical")
    raw = _stable_regular_bytes(path)
    if hashlib.sha256(raw).hexdigest() != binding.artifact_sha256:
        raise ContentSnapshotError("lexical identity artifact hash mismatch")
    try:
        blob = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentSnapshotError("lexical identity is not valid UTF-8 JSON") from exc
    allowed = {
        "schema_version",
        "artifact_id",
        "source_set_id",
        "source_set_generation",
        "source_set_sha256",
        "semantic_generation",
        "authority_generation",
        "build_fingerprint",
        "document_ids",
        "structure_artifacts",
        "entry_count",
        "identity_sha256",
    }
    if not isinstance(blob, Mapping) or set(blob) != allowed:
        raise ContentSnapshotError("lexical identity is incomplete or unexpected")
    core = dict(blob)
    declared_identity = core.pop("identity_sha256", None)
    if not isinstance(declared_identity, str) or _canonical_digest(core) != declared_identity:
        raise ContentSnapshotError("lexical identity self-hash mismatch")
    expected = {
        "schema_version": LEXICAL_IDENTITY_SCHEMA,
        "artifact_id": binding.artifact_id,
        "source_set_id": snapshot.source_set_id,
        "source_set_generation": snapshot.source_set_generation,
        "source_set_sha256": snapshot.source_set_sha256,
        "semantic_generation": snapshot.semantic_generation,
        "authority_generation": snapshot.authority_generation,
        "build_fingerprint": binding.build_fingerprint,
    }
    mismatches = [key for key, value in expected.items() if blob.get(key) != value]
    document_ids = blob.get("document_ids")
    if (
        not isinstance(document_ids, list)
        or document_ids != sorted(snapshot.document_ids())
        or len(document_ids) != len(set(document_ids))
    ):
        mismatches.append("document_ids")
    expected_structures = [
        {
            "document_id": row.document_id,
            "qualified_id": row.qualified_id,
            "sha256": row.artifact_sha256,
        }
        for row in snapshot.artifacts
        if row.role == "structure"
    ]
    expected_structures.sort(key=lambda row: str(row["document_id"]))
    if blob.get("structure_artifacts") != expected_structures:
        mismatches.append("structure_artifacts")
    entry_count = blob.get("entry_count")
    if isinstance(entry_count, bool) or not isinstance(entry_count, int) or entry_count < 0:
        mismatches.append("entry_count")
    if mismatches:
        raise ContentSnapshotError(
            "lexical index identity does not match the content snapshot: "
            + ", ".join(mismatches)
        )
    return blob

# 저장소 경로 — lawrag/api/routers/glossary.py 와 같은 규약. env 가 정본이고,
# 없으면 CLI 산출 자리를 본다.
def store_path() -> Path:
    return Path(
        os.environ.get("STRUCTURE_STORE")
        or runtime_path("out", "structure", "viewer")
    )


def terms_path() -> Path:
    return Path(os.environ.get("GLOSSARY_STORE", store_path().parent / "glossary.json"))


def links_path() -> Path:
    """판정으로 고정된 문서 간 참조 링크 — glossary.json 과 같은 자리 규약."""
    return Path(os.environ.get("RAG_LINKS_STORE", store_path().parent / "links.json"))


def norm(s: str) -> str:
    """묶음 키 — 공백만 지우고 대소문자를 접는다. `민원 처리` 와 `민원처리`,
    `RFQ` 와 `rfq` 가 갈리면 안 된다. 괄호·쉼표는 뜻을 가르므로 남긴다."""
    return re.sub(r"\s+", "", s or "").casefold()


# 색인에 올리지 않을 제목 — glossary 라우터와 같은 기준. 번호만 있는 것과
# 문장 꼬리는 이름이 아니다.
MAX_NAME = 40
_ORDINAL_ONLY = re.compile(r"^[\d\s.,()①-⑳가-힣]{0,3}$")
_SENTENCE_TAIL = ("다.", "요.", "니다", "습니다", "됩니다", "합니다", "바랍니다")


def _is_name(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > MAX_NAME:
        return False
    if _ORDINAL_ONLY.fullmatch(t):
        return False
    if t.endswith(_SENTENCE_TAIL):
        return False
    return bool(re.search(r"[가-힣A-Za-z]", t))


# 내규·외규·서식 축 — kind(인제스트 출처별 값)를 접는 표. kind 는 출처가
# 늘 때마다 값이 느는데(law·admrul·krx-rule·kofia-rule·krx-form·klca-model·
# internal…) 스코프·비교가 보는 축은 셋뿐이다. 새 kind 가 오면 여기 한 줄.
INTERNAL_KINDS = frozenset({"internal"})
FORM_KINDS = frozenset({"krx-form", "klca-model"})


def scope_kind_of(kind: str) -> str:
    """kind → "내규" | "서식" | "외규". 모르는 kind(빈 값 포함)는 외규로 본다 —
    법령·규정이 이 스토어의 기본 재료라서다."""
    k = (kind or "").strip()
    if k in INTERNAL_KINDS:
        return "내규"
    if k in FORM_KINDS or k.endswith("-form"):
        return "서식"
    return "외규"


@dataclass
class Entry:
    """색인 한 줄. `target` 이 병합 단위다 — 같은 대상을 다른 표면형으로
    여러 번 잡아도 히트는 하나여야 한다."""
    value: str                    # 표면형 (제목 그대로, 또는 용어)
    key: str                      # norm(value)
    kind: str                     # "제목" | "용어"
    target: str                   # "doc:{doc_id}:{node}" | "term:{key}"
    doc_id: str = ""
    doc: str = ""
    node: Optional[int] = None
    occurrences: list = field(default_factory=list)   # 용어일 때 — 이미 좌표가 있다
    content_provenance: ArtifactProvenance | None = None


@dataclass
class DocView:
    """문서 하나의 조회 창. 검색이 좌표를 되짚을 때 쓰는 것 전부."""
    doc_id: str
    name: str
    nodes: list
    blocks: list
    by_id: dict = field(default_factory=dict)
    block_by_idx: dict = field(default_factory=dict)
    _owner: dict = field(default_factory=dict)
    _path_cache: dict = field(default_factory=dict)
    # 문서 수준 시간 메타 — 관측용(응답 context 행의 시행일). 조문 수준
    # 이력은 구법 원문이 코퍼스에 없어 아직 자리만 있다 (docs/REVIEW.md
    # "필드는 최종 크기, 구현은 지금 크기").
    enforce: str = ""              # 시행일 YYYYMMDD (law.go.kr 메타)
    revised: str = ""              # 최종 개정일 YYYYMMDD
    # 문서 태그 — 인제스트가 meta.json 에 찍은 것을 그대로 든다. 색인이 이걸
    # 읽어야 "내규만 / 이 외규들만" 스코프와 컨텍스트의 내규·외규 표식이 선다.
    kind: str = ""                 # law·admrul·krx-rule·kofia-rule·krx-form·internal …
    folder: str = ""               # 관리 라벨 (스코프의 단위가 아니다 — 스코프는 scopes.yml)
    status: str = ""               # 내규: 현행 | 구판 (빈 값 = 현행으로 본다)
    series: str = ""               # 내규 문서군 키 — 신구 대비의 짝
    version: str = ""              # 내규 판 표식 (v1·v2 …)
    # SourceSet adapter에서만 채워진다. OFF 경로의 객체 모양과 결과에는
    # 관여하지 않고, 근거 행이 원본 package 좌표를 되짚을 때 사용한다.
    artifact_provenance: ArtifactProvenance | None = None
    artifact_provenances: tuple[ArtifactProvenance, ...] = ()

    @property
    def content_provenance(self) -> ArtifactProvenance | None:
        """Canonical structure artifact backing this document's coordinates."""

        return self.artifact_provenance

    @property
    def scope_kind(self) -> str:
        """내규·외규·서식 — kind(출처별 값)를 한 단계 위 축으로 접는다.
        비교·스코프 코드는 kind 문자열을 직접 보지 말고 이 축을 본다."""
        return scope_kind_of(self.kind)

    @property
    def is_current(self) -> bool:
        """구판이 아닌가 — status 가 비어 있으면 현행이다(외규는 status 가 없다)."""
        return (self.status or "현행") != "구판"

    @classmethod
    def build(
        cls,
        doc_id: str,
        meta: dict,
        res: dict,
        *,
        apply_structure_fixes: bool = True,
    ) -> "DocView":
        if apply_structure_fixes:
            from lawrag.core import structure_fixes       # 지연 — 순환 회피

            # Legacy OFF mode keeps the mutable correction overlay exactly as-is.
            nodes = structure_fixes.apply(doc_id, res.get("nodes", []))
        else:
            # SourceSet artifacts already represent the compiled generation; a
            # mutable sibling correction file must not alter pinned bytes.
            nodes = list(res.get("nodes", []))
        v = cls(doc_id=doc_id, name=meta.get("name", doc_id),
                nodes=nodes, blocks=res.get("blocks", []),
                enforce=str(meta.get("enforce") or ""),
                revised=str(meta.get("revised") or ""),
                kind=str(meta.get("kind") or ""),
                folder=str(meta.get("folder") or ""),
                status=str(meta.get("status") or ""),
                series=str(meta.get("series") or ""),
                version=str(meta.get("version") or ""))
        v.by_id = {n.get("id"): n for n in v.nodes}
        v.block_by_idx = {b.get("idx"): b for b in v.blocks}
        # 블록 → 그 블록을 덮는 가장 깊은 마디 (glossary._scan 과 같은 규칙)
        for n in v.nodes:
            s = n.get("span") or [0, 0]
            for b in range(s[0], max(s[1], s[0] + 1)):
                cur = v._owner.get(b)
                if cur is None or n.get("level", 0) > cur.get("level", 0):
                    v._owner[b] = n
        return v

    def owner(self, block_idx: int) -> Optional[dict]:
        return self._owner.get(block_idx)

    def addendum_kind(self, node_id: Optional[int]) -> str:
        """부칙 조의 **종류** — 본문이면 빈 문자열.

        부칙 한 묶음(`부칙 <제N호, 날짜>`)에는 성격이 아주 다른 조가 섞여
        있다: 언제부터인가(시행일) · 옛 사람·회사를 어떻게 대우하나(경과조치·
        적용례) · 남의 법 문구를 이렇게 고쳐라(다른 법령의 개정). 앞의 둘은
        권리·의무를 정하지만 뒤의 것은 문구 치환 목록이라 대개 질의의 답이
        아니다.

        조 제목이 정형이라 문자열로 갈린다 — 법제처 입안·심사 기준이 규격화한
        표현이고, 문서별 상수가 아니라 코퍼스 전역 신호다(실측 38문서·부칙
        마디 3,993개: 개정 1,880 · 시행일 895 · 경과조치 691 · 적용례 519).

        **판정은 여기서 하지 않는다 — 이름표만 붙인다.** 어떤 질문에 어떤
        종류가 답인지는 질문마다 다르다("언제 시행되나요"의 답은 시행일 조다).
        회수에서 특정 종류를 걸러내는 규칙은 데이터가 쌓이기 전에 박지 않는다
        (샘플 과적합 금지). 지금은 진단 튜플에 관측으로만 남는다.
        """
        p = self.path(node_id)
        if "부칙" not in p:
            return ""
        for k in ("다른 법령의 개정", "다른 법률의 개정", "다른 법령의 폐지",
                  "다른 법률의 폐지"):
            if k in p:
                return "개정·폐지"
        for k in ("경과조치", "경과 조치"):
            if k in p:
                return "경과조치"
        if "적용례" in p:
            return "적용례"
        if "시행일" in p:
            return "시행일"
        return "부칙기타"

    def coordinate_scope(self, node_id: Optional[int]) -> str:
        node = self.by_id.get(node_id)
        if node is None:
            return ""
        stored = str(node.get("coordinate_scope") or "")
        if stored:
            return stored
        path = self.path(node_id)
        if "부칙" in path:
            return "addendum"
        if "별지" in path or "서식" in path:
            return "form"
        if "별표" in path or "부록" in path:
            return "annex"
        return "body"

    def path(self, node_id: Optional[int]) -> str:
        """마디의 조상 사슬 — `제2장 ▸ 제19조 ▸ 제3항`. 이것이 인용 좌표의
        사람이 읽는 형태다.

        표면(마커)과 제목을 **둘 다** 쓴다 — 제목만 쓰면 "제22조 (광고 관련
        준수사항)"이 "광고 관련 준수사항"으로 떠서, 참조 검수 화면에서 제22조
        마디가 계층에 없는 것처럼 읽힌다(실측 2026-08-12: 멀쩡한 구조를 계층
        결손으로 오판하게 했다)."""
        if node_id in self._path_cache:
            return self._path_cache[node_id]
        parts: list[str] = []
        seen: set[int] = set()
        n = self.by_id.get(node_id)
        while n is not None and n.get("id") not in seen:
            seen.add(n.get("id"))
            surf = (n.get("surface") or "").strip()
            title = (n.get("title") or "").strip()
            label = f"{surf} {title}" if surf and title and surf not in title \
                else (title or surf)
            if label:
                parts.append(label)
            n = self.by_id.get(n.get("parent"))
        value = " ▸ ".join(reversed(parts))
        self._path_cache[node_id] = value
        return value

    def section_outline(self, node: dict, cap: int = 6000) -> str:
        """구역 본문을 **계층 그대로** — 자손 마디를 들여쓰기로 세워 넘긴다.

        평평하게 이어 붙이면 "장을 찾았는데 그 아래 조·절이 어떻게 매달렸는지"가
        컨텍스트에서 사라진다. 그러면 LLM 은 계층이 어긋난 것을 볼 수 없고(볼 것이
        없으니), 우리는 구조화 오류를 영영 사후에 못 잡는다.

        마디 줄에는 `▸` 를 붙여 본문과 가른다 — 모델이 "이건 우리 해석이 세운
        제목이고 저건 원문 줄"을 구별할 수 있어야 계층을 의심할 수 있다.
        """
        root_id = node.get("id")
        root_lv = node.get("level") or 0
        s = node.get("span") or [0, 0]
        lo, hi = s[0], max(s[1], s[0] + 1)

        # 이 구역이 덮는 자손 마디 — 블록 시작점마다 어느 마디가 여는지 표시한다
        opens: dict[int, list[dict]] = {}
        for n in self.nodes:
            if n.get("id") == root_id:
                continue
            ns = n.get("span") or [0, 0]
            if lo <= ns[0] < hi:
                opens.setdefault(ns[0], []).append(n)
        for v in opens.values():
            v.sort(key=lambda n: n.get("level") or 0)

        # 층을 **실제 나타난 것끼리** 0,1,2… 로 접는다. 원래 레벨 차를 그대로 쓰면
        # 편(L0) 아래 조(L4) 가 공백 8칸으로 들어가 눈에도 나쁘고 토큰도 버린다.
        seen_lv = sorted({(n.get("level") or 0) for v in opens.values() for n in v}
                         | {root_lv})
        rank = {lv: i for i, lv in enumerate(seen_lv)}
        depth_of = lambda lv: max(0, rank.get(lv, 0) - rank.get(root_lv, 0))

        parts: list[str] = []
        total, cut = 0, False
        for b in range(lo, hi):
            blk_head = ((self.block_by_idx.get(b) or {}).get("text") or "").lstrip()
            for n in opens.get(b, []):
                depth = depth_of(n.get("level") or 0)
                surf = (n.get("surface") or "").strip()
                title = (n.get("title") or "").strip()
                label = " ".join(x for x in [surf, title] if x)
                # 표면만 있는 마디(①·1.)는 본문 첫머리에 같은 표식이 이미
                # 보인다 — 중복 줄을 세우지 않는다(들여쓰기가 계층을 말한다).
                if not title and surf and surf in blk_head[:100]:
                    continue
                if label:
                    line = "  " * depth + "▸ " + label
                    parts.append(line)
                    total += len(line)
            blk = self.block_by_idx.get(b)
            if blk is None:
                continue
            t = (blk.get("text") or "").strip()
            if not t:
                continue
            # 본문은 그 자리를 여는 마디의 깊이만큼 들여쓴다 — 원문의 층이 눈에 보인다
            here = opens.get(b)
            depth = depth_of((here[-1].get("level") if here else root_lv) or 0)
            line = "  " * depth + t
            parts.append(line)
            total += len(line)
            if total >= cap:
                cut = b + 1 < hi
                break
        out = "\n".join(parts)
        if len(out) > cap:
            out, cut = out[:cap], True
        if cut:
            out += "\n…(구역이 길어 여기서 잘림 — 이후 내용 있음)"
        return out

    def section_text(self, node: dict, cap: int = 6000) -> str:
        """구역 본문. cap 은 폭주 방지다(실측: 구역 p50 80자·p99 5.7k·최대 68k —
        부칙 전체 같은 부모 구역이 문서 절반을 들 수 있다). 잘리면 **표시한다** —
        모델이 '구역이 끝났다'와 '잘렸다'를 구별하지 못하면 부재 단정으로 샌다."""
        s = node.get("span") or [0, 0]
        parts = []
        total = 0
        cut = False
        for b in range(s[0], max(s[1], s[0] + 1)):
            blk = self.block_by_idx.get(b)
            if blk is None:
                continue
            t = (blk.get("text") or "").strip()
            if not t:
                continue
            parts.append(t)
            total += len(t)
            if total >= cap:
                cut = b + 1 < s[1]
                break
        out = "\n".join(parts)
        if len(out) > cap:
            out, cut = out[:cap], True
        if cut:
            out += "\n…(구역이 길어 여기서 잘림 — 이후 내용 있음)"
        return out


def _lex_terms(text: str) -> list[str]:
    """본문 색인용 토큰 — 옛 v1 chunk_search 와 같은 꼴.
    한글·영숫자 연속만 남기고, 한 글자는 버린다."""
    out, buf = [], ""
    for ch in text:
        if ch.isalnum() or "가" <= ch <= "힣":
            buf += ch
        else:
            if len(buf) > 1:
                out.append(buf.casefold())
            buf = ""
    if len(buf) > 1:
        out.append(buf.casefold())
    return out


@dataclass
class Index:
    docs: dict                     # doc_id -> DocView — **스토어 전부** (스코프와 무관)
    entries: list                  # Entry 목록 (제목 + 용어) — 스코프가 있으면 그 안만
    saved_links: list = field(default_factory=list)   # links.json — 판정으로 고정된 링크
    rel_fixes: list = field(default_factory=list)     # links.json — 사람이 고친 관계 라벨
    # 질의 스코프 — None 이면 전부. 있으면 **진입**(제목·용어·본문·벡터·기억·
    # 회복)은 이 안에서만 일어나고, 동반(배제·위임·준용·수임·정의·제재)과 참조
    # 확장은 밖으로 나갈 수 있다(2026-08-19 사용자 결정 — 배제를 놓치면 반대
    # 답이 나가므로). 밖으로 나간 구역은 호출부가 표식을 붙인다(scope_out).
    scope: Optional[frozenset] = None
    scope_name: str = ""           # 표시용 — 어느 스코프였나 (응답·튜플에 남는다)
    canonical_doc_ids: Optional[frozenset] = None  # 공식 법령 세대의 유일한 진입판
    authority_generation: str = ""
    authority_as_of: str = ""
    content_snapshot: ContentSnapshot | None = None
    content_snapshot_sha256: str = ""
    content_fingerprint: str = ""
    _postings: Optional[dict] = None
    _n_blocks: int = 0
    _refs: Optional[dict] = None
    _cross: Optional[tuple] = None
    _cross_from: Optional[dict] = None
    _cross_to: Optional[dict] = None
    _unified_relation_cache: dict = field(default_factory=dict)
    _scoped: dict = field(default_factory=dict)     # (frozenset, 표시명) → 불변 스코프 사본
    # Index is shared by API/golden worker threads.  Lazy caches must never
    # publish a partially built dictionary to another caller.
    _cache_lock: object = field(default_factory=RLock, repr=False, compare=False)

    # ------------------------------------------------------------- 스코프
    def in_scope(self, doc_id: str) -> bool:
        return self.scope is None or doc_id in self.scope

    def dataset_id_for_document(self, doc_id: str) -> str:
        view = self.docs.get(doc_id)
        provenance = view.content_provenance if view is not None else None
        return provenance.dataset_id if provenance is not None else ""

    def relation_allowed(self, src_doc: str, dst_doc: str) -> bool:
        """Apply the immutable SourceSet relation boundary in one place.

        Legacy indexes have no SourceSet policy and retain their historical
        behaviour.  A proof-bound snapshot may explicitly allow relations
        across datasets.  Otherwise, a cross-document edge is admissible only
        when both endpoints have non-empty, identical dataset identities.
        Missing provenance fails closed instead of making two empty strings
        look like the same dataset.
        """

        if not src_doc or not dst_doc or src_doc == dst_doc:
            return True
        if self.content_snapshot is None:
            return True
        if self.content_snapshot.cross_dataset_relations:
            return True
        src_dataset = self.dataset_id_for_document(src_doc)
        dst_dataset = self.dataset_id_for_document(dst_doc)
        return bool(src_dataset and dst_dataset and src_dataset == dst_dataset)

    @property
    def entry_docs(self) -> dict:
        """진입 후보 문서 — 스코프 안(없으면 전부). **문서를 훑는 채널은 이것을
        돌아야 한다**(용어집·프레임·정의·회복·둘러보기). docs 는 좌표 되짚기용이다."""
        if self.scope is None:
            return self.docs
        return {d: v for d, v in self.docs.items() if d in self.scope}

    def default_scope(self) -> Optional[frozenset]:
        """명시 스코프가 없을 때의 기본 진입 범위 — 구판(내규 status=구판)은
        뺀다. 신구 대비는 구판을 스코프로 **명시**해서 연다. 구판이 없으면
        None(제한 없음) — 비용 0."""
        canonical = set(self.canonical_doc_ids or ())
        old = [d for d, v in self.docs.items()
               if (not v.is_current
                   or (canonical and v.kind in {"law", "admrul"} and d not in canonical))]
        if not old:
            return None
        return frozenset(d for d in self.docs if d not in set(old))

    def scoped(self, doc_ids: Optional[set], name: str = "") -> "Index":
        with self._cache_lock:
            return self._scoped_unlocked(doc_ids, name)

    def _scoped_unlocked(self, doc_ids: Optional[set], name: str = "") -> "Index":
        """스코프를 씌운 얕은 사본 — docs·간선·링크는 공유하고 entries 만
        거른다(진입 표면형). postings 는 새로 세워 스코프 안만 든다.
        doc_ids 가 None 이면 기본 스코프(구판 제외)를 쓴다."""
        if doc_ids is None:
            doc_ids = self.default_scope()
            if doc_ids is None:
                return self
        ids = frozenset(doc_ids)
        cache_key = (ids, str(name or ""))
        hit = self._scoped.get(cache_key)
        if hit is not None:                     # 같은 스코프·표시명의 다음 질의
            return hit
        ents: list = []
        for e in self.entries:
            if e.kind == "용어":
                occ = [o for o in e.occurrences if o.get("doc_id") in ids]
                if occ:
                    ents.append(Entry(value=e.value, key=e.key, kind=e.kind,
                                      target=e.target, occurrences=occ))
            elif e.doc_id in ids:
                ents.append(e)
        sub = Index(docs=self.docs, entries=ents, saved_links=self.saved_links,
                    rel_fixes=self.rel_fixes, scope=ids, scope_name=name,
                    canonical_doc_ids=self.canonical_doc_ids,
                    authority_generation=self.authority_generation,
                    authority_as_of=self.authority_as_of,
                    content_snapshot=self.content_snapshot,
                    content_snapshot_sha256=self.content_snapshot_sha256,
                    content_fingerprint=self.content_fingerprint)
        # 간선은 스토어 전체 것을 그대로 — 동반이 스코프 밖으로 나갈 수 있어야
        # 한다. 원본에서 한 번 세워 공유한다(사본마다 다시 세우면 질의마다 값).
        self.ref_edges(); self.cross_refs()
        sub._refs, sub._cross = self._refs, self._cross
        sub._unified_relation_cache = self._unified_relation_cache
        if len(self._scoped) >= 16:             # 스코프는 몇 개 안 된다 — 폭주만 막는다
            self._scoped.clear()
        self._scoped[cache_key] = sub
        return sub

    # ------------------------------------------------------------- 구성
    @classmethod
    def from_docs(cls, docs: list[tuple[str, dict, dict]],
                  user_terms: Optional[list[dict]] = None,
                  saved_links: Optional[list[dict]] = None,
                  rel_fixes: Optional[list[dict]] = None,
                  canonical_doc_ids: Optional[set[str]] = None,
                  authority_generation: str = "",
                  authority_as_of: str = "",
                  document_provenance: Optional[
                      Mapping[str, tuple[ArtifactProvenance, ...]]
                  ] = None,
                  content_snapshot: ContentSnapshot | None = None,
                  content_fingerprint: str = "",
                  apply_structure_fixes: bool = True) -> "Index":
        """(doc_id, meta, result) 목록에서 색인을 세운다. 파일이 아니라 값을
        받는다 — 시험이 저장소 없이 색인을 만들 수 있어야 한다."""
        views: dict[str, DocView] = {}
        entries: list[Entry] = []
        for doc_id, meta, res in docs:
            v = DocView.build(
                doc_id,
                meta,
                res,
                apply_structure_fixes=apply_structure_fixes,
            )
            if document_provenance is not None:
                rows = tuple(document_provenance.get(doc_id, ()))
                if not rows:
                    raise ContentSnapshotError(
                        f"indexed document has no SourceSet provenance: {doc_id}"
                    )
                v.artifact_provenances = rows
                if content_snapshot is None:
                    raise ContentSnapshotError(
                        "document provenance requires a content snapshot"
                    )
                v.artifact_provenance = content_snapshot.provenance_for_document(doc_id)
            views[doc_id] = v
            for n in v.nodes:
                label = (n.get("title") or "").strip() or (n.get("surface") or "").strip()
                if not _is_name(label):
                    continue
                entries.append(Entry(
                    value=label, key=norm(label), kind="제목",
                    target=f"doc:{doc_id}:{n.get('id')}",
                    doc_id=doc_id, doc=v.name, node=n.get("id"),
                    content_provenance=v.artifact_provenance))
        # 저장된 용어 — 출현 좌표가 이미 붙어 있다(glossary 라우터가 훑어 둔다).
        # **승인된(활성) 용어만 검색에 참여한다** (2026-08-10 사용자 결정:
        # 전문 용어는 keyword 가 맞지만, 일반어가 섞이는 문제는 승인으로 푼다).
        # 잠정은 검수 큐 대기 — 색인 밖. tombstone 은 기각 — 역시 밖.
        # status 없는 옛 행은 수기 입력이므로 활성으로 본다.
        # 표면형(별칭 포함)마다 줄을 하나씩 낸다 — "PSV" 로 물어도 "안전밸브" 의
        # 좌표에 닿아야 한다. target 이 같으므로 히트는 하나로 병합된다.
        for t in user_terms or []:
            if t.get("status") not in (None, "활성"):
                continue
            key = t.get("key") or norm(t.get("term", ""))
            if not key:
                continue
            surfaces = t.get("surfaces") or [t.get("term", key)]
            for sfc in surfaces:
                skey = norm(sfc)
                if not skey:
                    continue
                entries.append(Entry(
                    value=sfc, key=skey, kind="용어",
                    target=f"term:{key}", occurrences=t.get("occurrences", [])))
        return cls(docs=views, entries=entries, saved_links=saved_links or [],
                   rel_fixes=rel_fixes or [],
                   canonical_doc_ids=(frozenset(canonical_doc_ids)
                                      if canonical_doc_ids is not None else None),
                   authority_generation=authority_generation,
                   authority_as_of=authority_as_of,
                   content_snapshot=content_snapshot,
                   content_snapshot_sha256=(
                       content_snapshot.content_snapshot_sha256
                       if content_snapshot is not None else ""
                   ),
                   content_fingerprint=content_fingerprint)

    @classmethod
    def load_from_content_snapshot(cls, snapshot: ContentSnapshot) -> "Index":
        """Build only from the exact artifacts selected by a pinned SourceSet.

        Unlike the legacy directory scan, this path never skips malformed files
        and never discovers an unlisted document.  Every document has exactly
        one self-contained ``rag-structure-artifact-v1`` whose selected bytes
        prove both metadata and the indexed node/block result.
        """

        snapshot.require_materialized()
        # Requiring this binding makes lexical cache identity part of admission,
        # rather than an optional diagnostic attached after the index is built.
        content_fingerprint = snapshot.content_fingerprint("lexical")
        lexical_identity = _load_lexical_identity(snapshot)
        docs: list[tuple[str, dict, dict]] = []
        document_provenance: dict[str, tuple[ArtifactProvenance, ...]] = {}
        meta_by_id: dict[str, dict] = {}
        for document_id in snapshot.document_ids():
            provenance = snapshot.provenances_for_document(document_id)
            structure = [row for row in provenance if row.role == "structure"]
            if len(structure) != 1:
                raise ContentSnapshotError(
                    "SourceSet document requires exactly one structure artifact: "
                    f"{document_id}"
                )
            payload = structure[0].verified_json()
            if set(payload) != {"schema_version", "document_id", "meta", "result"}:
                raise ContentSnapshotError(
                    f"structure artifact is incomplete or unexpected: {document_id}"
                )
            if payload.get("schema_version") != "rag-structure-artifact-v1":
                raise ContentSnapshotError(
                    f"unsupported structure artifact schema: {document_id}"
                )
            if payload.get("document_id") != document_id:
                raise ContentSnapshotError(
                    f"structure artifact document_id mismatch: {document_id}"
                )
            raw_meta, raw_result = payload.get("meta"), payload.get("result")
            if not isinstance(raw_meta, Mapping) or not isinstance(raw_result, Mapping):
                raise ContentSnapshotError(
                    f"structure artifact meta/result must be objects: {document_id}"
                )
            if (
                not isinstance(raw_result.get("nodes"), list)
                or not isinstance(raw_result.get("blocks"), list)
                or any(
                    not isinstance(row, Mapping)
                    for row in raw_result.get("nodes", [])
                )
                or any(
                    not isinstance(row, Mapping)
                    for row in raw_result.get("blocks", [])
                )
            ):
                raise ContentSnapshotError(
                    f"structure artifact result needs nodes and blocks: {document_id}"
                )
            meta = dict(raw_meta)
            result = dict(raw_result)
            docs.append((document_id, meta, result))
            meta_by_id[document_id] = meta
            document_provenance[document_id] = provenance

        if not docs:
            raise ContentSnapshotError("SourceSet contains no retrievable structure documents")

        # Optional global inputs are composed deterministically in qualified-ID
        # order.  A malformed selected artifact is fatal; ON mode never silently
        # drops a glossary or relation file and continues with a partial corpus.
        terms: list[dict] = []
        links: list[dict] = []
        rel_fixes: list[dict] = []
        for artifact in snapshot.artifacts:
            leaf = Path(artifact.source_path).name
            if leaf == "glossary.json":
                blob = artifact.verified_json()
                rows = blob.get("terms")
                if not isinstance(rows, list) or any(
                    not isinstance(row, Mapping) for row in rows
                ):
                    raise ContentSnapshotError(
                        f"invalid glossary artifact: {artifact.qualified_id}"
                    )
                terms.extend(dict(row) for row in rows)
            elif leaf == "links.json":
                blob = artifact.verified_json()
                link_rows = blob.get("links", [])
                fix_rows = blob.get("rel_fixes", [])
                if (
                    not isinstance(link_rows, list)
                    or not isinstance(fix_rows, list)
                    or any(not isinstance(row, Mapping) for row in link_rows)
                    or any(not isinstance(row, Mapping) for row in fix_rows)
                ):
                    raise ContentSnapshotError(
                        f"invalid relation artifact: {artifact.qualified_id}"
                    )
                links.extend(dict(row) for row in link_rows)
                rel_fixes.extend(dict(row) for row in fix_rows)

        authority_artifacts = [
            artifact
            for artifact in snapshot.artifacts
            if Path(artifact.source_path).name == "law_index.json"
        ]
        if len(authority_artifacts) > 1:
            raise ContentSnapshotError("SourceSet has ambiguous legal authority indexes")
        canonical_ids: set[str] | None = None
        authority_as_of = ""
        if authority_artifacts:
            authority = authority_artifacts[0].verified_json()
            if authority.get("schema_version") != "legal-authority-generation-v1":
                raise ContentSnapshotError("unsupported legal authority index schema")
            if str(authority.get("generation_id") or "") != snapshot.authority_generation:
                raise ContentSnapshotError("legal authority generation is stale")
            raw_ids = authority.get("canonical_document_ids")
            if (
                not isinstance(raw_ids, list)
                or any(not isinstance(value, str) or not value for value in raw_ids)
                or len(raw_ids) != len(set(raw_ids))
            ):
                raise ContentSnapshotError("legal authority canonical IDs are invalid")
            canonical_ids = set(raw_ids)
            missing = canonical_ids - set(meta_by_id)
            if missing:
                raise ContentSnapshotError(
                    f"legal authority canonical documents are missing: {sorted(missing)}"
                )
            authority_as_of = str(authority.get("as_of") or "")

        stale: list[str] = []
        for document_id, meta in meta_by_id.items():
            declared_generation = str(meta.get("authority_generation") or "")
            legally_versioned = str(meta.get("kind") or "") in {"law", "admrul"}
            if declared_generation and declared_generation != snapshot.authority_generation:
                stale.append(document_id)
            elif legally_versioned and declared_generation != snapshot.authority_generation:
                stale.append(document_id)
            if canonical_ids is not None and document_id in canonical_ids and (
                meta.get("status") != "현행" or not meta.get("canonical")
            ):
                stale.append(document_id)
        if stale:
            raise ContentSnapshotError(
                "structure/authority generation mismatch: " + ", ".join(sorted(set(stale)))
            )

        built = cls.from_docs(
            docs,
            terms,
            links,
            rel_fixes,
            canonical_doc_ids=canonical_ids,
            authority_generation=snapshot.authority_generation,
            authority_as_of=authority_as_of,
            document_provenance=document_provenance,
            content_snapshot=snapshot,
            content_fingerprint=content_fingerprint,
            apply_structure_fixes=False,
        )
        if len(built.entries) != lexical_identity["entry_count"]:
            raise ContentSnapshotError(
                "lexical index entry count disagrees with its release identity"
            )
        return built

    @classmethod
    def from_content_snapshot(cls, snapshot: ContentSnapshot) -> "Index":
        """Compatibility alias for the explicit serving loader."""

        return cls.load_from_content_snapshot(snapshot)

    @classmethod
    def load(cls, store: Optional[Path] = None,
             terms_file: Optional[Path] = None,
             links_file: Optional[Path] = None,
             *,
             content_snapshot: ContentSnapshot | None = None) -> "Index":
        """저장소에서 색인을 세운다. 해석 산출이 있는 문서만 싣는다."""
        if content_snapshot is None and _snapshot_adapter_enabled():
            content_snapshot = current_content_snapshot(required=True)
        if content_snapshot is not None:
            return cls.load_from_content_snapshot(content_snapshot)
        store = store or store_path()
        terms_file = terms_file or terms_path()
        links_file = links_file or links_path()
        docs: list[tuple[str, dict, dict]] = []
        if store.exists():
            for d in sorted(store.iterdir()):
                rj, mj = d / "result.json", d / "meta.json"
                if not (rj.exists() and mj.exists()):
                    continue
                try:
                    docs.append((d.name,
                                 json.loads(mj.read_text(encoding="utf-8")),
                                 json.loads(rj.read_text(encoding="utf-8"))))
                except Exception:
                    continue
        terms: list[dict] = []
        if terms_file.exists():
            try:
                terms = json.loads(terms_file.read_text(encoding="utf-8")).get("terms", [])
            except Exception:
                terms = []
        links: list[dict] = []
        rel_fixes: list[dict] = []
        if links_file.exists():
            try:
                blob = json.loads(links_file.read_text(encoding="utf-8"))
                links = blob.get("links", [])
                rel_fixes = blob.get("rel_fixes", [])
            except Exception:
                links = []
        canonical_ids: set[str] | None = None
        authority_generation = authority_as_of = ""
        law_index_file = Path(os.environ.get(
            "RAG_LAW_INDEX_STORE", store.parent / "law_index.json"))
        if law_index_file.is_file():
            try:
                authority = json.loads(law_index_file.read_text(encoding="utf-8"))
            except Exception:
                authority = {}
            if authority.get("schema_version") == "legal-authority-generation-v1":
                canonical_ids = set(authority.get("canonical_document_ids") or ())
                authority_generation = str(authority.get("generation_id") or "")
                authority_as_of = str(authority.get("as_of") or "")
                meta_by_id = {doc_id: meta for doc_id, meta, _res in docs}
                missing = canonical_ids - set(meta_by_id)
                if missing:
                    raise RuntimeError(f"law_index canonical structure 누락: {sorted(missing)}")
                bad = [doc_id for doc_id in sorted(canonical_ids)
                       if (meta_by_id[doc_id].get("authority_generation")
                           != authority_generation
                           or meta_by_id[doc_id].get("status") != "현행"
                           or not meta_by_id[doc_id].get("canonical"))]
                if bad:
                    raise RuntimeError(f"law_index/meta authority generation 불일치: {bad}")
        return cls.from_docs(docs, terms, links, rel_fixes,
                             canonical_doc_ids=canonical_ids,
                             authority_generation=authority_generation,
                             authority_as_of=authority_as_of)

    # ------------------------------------------------------------- 본문 색인
    def postings(self) -> dict:
        """블록 본문의 렉시컬 색인 — 제목·용어가 다 빗나갔을 때의 마지막 단.
        쓰일 때 처음 세운다(문서가 많아도 첫 폴백 전까지는 공짜)."""
        with self._cache_lock:
            if self._postings is None:
                postings: dict = {}
                n = 0
                for doc_id, v in self.entry_docs.items():
                    for b in v.blocks:
                        n += 1
                        for t in _lex_terms(b.get("text") or ""):
                            postings.setdefault(t, {}).setdefault(
                                (doc_id, b.get("idx")), 0)
                            postings[t][(doc_id, b.get("idx"))] += 1
                # Publish only the finished snapshot.  In particular, expand()
                # must not iterate a dictionary another worker is still growing.
                self._n_blocks = max(n, 1)
                self._postings = postings
            return self._postings

    def expand(self, token: str) -> list[str]:
        """조사가 붙은 어절을 색인어와 잇는다 — 형태소 분석기 없이.
        완전일치가 있으면 그것만, 없으면 접두 관계인 색인어를 몇 개."""
        post = self.postings()
        k = token.casefold()
        if k in post:
            return [k]
        out = [t for t in post
               if len(t) >= 2 and (t.startswith(k) or k.startswith(t))]
        out.sort(key=lambda t: (abs(len(t) - len(k)), t))
        return out[:4]

    def idf(self, token: str) -> float:
        post = self.postings().get(token)
        if not post:
            return 0.0
        return math.log(1 + self._n_blocks / len(post))

    # ------------------------------------------------------------- 상호참조
    def _redirect(self, src_doc: str, src, edge: dict, *,
                  redirects: Optional[dict] = None) -> dict:
        """승인된 재지정(edge_rules.json)을 간선 하나에 적용한다 — 사람이
        "제2조가 아니라 제2조 제3항"이라 확정한 좌표로 도착을 옮겨 앉힌다.
        새 좌표가 실재할 때만 옮긴다(구조가 다시 서면 노드가 사라질 수 있다)."""
        from lawrag.core.rag import verdicts as verdicts_mod   # 순환 의존 회피 — 지연
        redirect_rules = redirects if redirects is not None \
            else verdicts_mod.redirect_map()
        r = redirect_rules.get(
            (src_doc, src, edge.get("dst_doc", src_doc), edge["dst"]))
        if r is None:
            return edge
        dv = self.docs.get(edge.get("dst_doc", src_doc))
        if dv is None or dv.by_id.get(r["new_dst"]) is None:
            return edge
        return {**edge, "dst": r["new_dst"], "via": "교정"} \
            if "dst_doc" in edge else {**edge, "dst": r["new_dst"]}

    def ref_edges(self) -> dict:
        with self._cache_lock:
            return self._ref_edges_unlocked()

    def _ref_edges_unlocked(self) -> dict:
        """문서별 조문 상호참조 간선 — doc_id -> [{"src","dst","surface","block"}].
        본문의 "제4조를 참고한다" 가 구역을 가로로 잇는다. 쓰일 때 처음
        세운다(postings 와 같은 규율). 승인된 재지정이 있으면 도착이 옮겨 앉는다."""
        if self._refs is None:
            from lawrag.core.rag import refs as refs_mod       # 순환 의존 회피 — refs 는 DocView 타입만 본다
            from lawrag.core.rag import verdicts as verdicts_mod
            rule_snapshot = verdicts_mod.rule_snapshot()
            redirects = verdicts_mod.redirect_map(snapshot=rule_snapshot)
            self._refs = {doc_id: [self._redirect(
                                       doc_id, e["src"], e, redirects=redirects)
                                   for e in refs_mod.resolve(v)]
                          for doc_id, v in self.docs.items()}
            # 사람이 고친 관계 라벨 — 자동 분류(문면 술어)는 그대로 두고 조립
            # 시점에 덮는다. 억제·재지정과 같은 규율: 관측을 고쳐 쓰지 않는다.
            fixes = self._rel_fix_map()
            for doc_id, es in self._refs.items():
                for e in es:
                    r = fixes.get((doc_id, e["src"], "", e["dst"]))
                    if r:
                        e["rel"], e["rel_via"] = r, "사람"
        return self._refs

    def _rel_fix_map(self) -> dict:
        """(src_doc, src, dst_doc(문서 안이면 ""), dst) → 사람이 정한 rel."""
        return {(f.get("src_doc", ""), f.get("src"), f.get("dst_doc", ""),
                 f.get("dst")): f["rel"]
                for f in self.rel_fixes if f.get("rel")}

    def cross_refs(self) -> tuple:
        with self._cache_lock:
            return self._cross_refs_unlocked()

    def _cross_refs_unlocked(self) -> tuple:
        """문서 사이 참조 — (확정 간선, 보류 목록).

        결정론 대조(refs.cross_resolve)에 links.json 의 판정 결과를 합친다.
        저장된 링크는 좌표가 아직 유효한 것만 싣고, 그 링크가 정착시킨 보류
        항목은 목록에서 뺀다 — 한 번 판정한 것을 다시 묻지 않는다."""
        if self._cross is None:
            from lawrag.core.rag import refs as refs_mod
            from lawrag.core.rag import switches as switches_mod   # 순환 회피 — 지연
            edges, pending = refs_mod.cross_resolve(
                self.docs, declare=switches_mod.is_on("declare"))
            # Apply the SourceSet boundary before uniqueness/presumption is
            # calculated.  A forbidden candidate must not keep an admissible
            # candidate ambiguous, nor may it be exposed to a later LLM step.
            edges = [
                edge for edge in edges
                if self.relation_allowed(
                    str(edge.get("src_doc") or ""),
                    str(edge.get("dst_doc") or ""),
                )
            ]
            bounded_pending = []
            for item in pending:
                candidates = [
                    candidate for candidate in item.get("candidates", [])
                    if self.relation_allowed(
                        str(item.get("src_doc") or ""),
                        str(candidate.get("doc_id") or ""),
                    )
                ]
                if candidates:
                    bounded_pending.append({**item, "candidates": candidates})
            pending = bounded_pending
            covered: set = set()
            for lk in self.saved_links:
                dv = self.docs.get(lk.get("dst_doc"))
                if (lk.get("src_doc") not in self.docs or dv is None
                        or dv.by_id.get(lk.get("dst")) is None
                        or not self.relation_allowed(
                            str(lk.get("src_doc") or ""),
                            str(lk.get("dst_doc") or ""),
                        )):
                    continue                   # 문서·구역이 사라졌다 — 싣지 않는다
                edges.append({**lk, "via": lk.get("via", "저장")})
                covered.add((lk.get("src_doc"), lk.get("src"),
                             tuple(lk["key"]) if lk.get("key") else lk.get("surface")))
            pending = [p for p in pending
                       if (p["src_doc"], p["src"], tuple(p["key"])) not in covered
                       and (p["src_doc"], p["src"], p["surface"]) not in covered]
            # 자동 연결 — 후보가 하나로 떨어지는 보류는 기본 연결한다 (2026-08-12
            # 사용자 결정: 기본은 전부 연결, 사람은 참조 화면에서 끊는다).
            # 대용어("법"·"동법")라 이름 대조가 물러섰을 뿐, 코퍼스 안에서 갈
            # 곳이 하나뿐인 참조다(실측 5,006 중 3,901). 여럿에 걸린 것만
            # 보류로 남는다. 틀린 자동 간선은 끊기(억제 규칙)와 질의 중 LLM
            # 판정(백로그)이 사후에 거른다 — 그래서 기본 연결이 안전하다.
            auto_seen = {(e["src_doc"], e["src"], e.get("dst_doc"), e["dst"])
                         for e in edges}

            def in_appendix(v, node) -> bool:
                cur = v.by_id.get(node)
                while cur is not None:
                    s = (cur.get("surface") or "").strip()
                    if s == "부칙" or s.startswith("별표") or s.startswith("별지"):
                        return True
                    cur = v.by_id.get(cur.get("parent"))
                return False

            presume_on = switches_mod.is_on("presume")
            mainbody_on = switches_mod.is_on("mainbody")
            still = []
            for p in pending:
                uniq = {(c["doc_id"], c["node"]) for c in p["candidates"]}
                pick = via = None
                if len(uniq) == 1 and presume_on:
                    # "추정" — 이름을 안 부른 참조인데 그 조를 가진 문서가
                    # 하나뿐이라 그리 이었다 (이름대조=확실 / 추정=후보 유일).
                    pick, via = next(iter(uniq)), "추정"
                elif mainbody_on and len({d for d, _ in uniq}) == 1:
                    # "본문우선" — 한 문서 안 본문·부칙 번호 중복. 부칙 조는
                    # 밖에서 "부칙 제N조"로 부르므로 맨 "제N조"는 본문이다.
                    dv = self.docs.get(next(iter(uniq))[0])
                    mains = [(d, n) for d, n in uniq
                             if dv and not in_appendix(dv, n)]
                    if len(mains) == 1:
                        pick, via = mains[0], "본문우선"
                if pick is None:
                    still.append(p)
                    continue
                dst_doc, dst = pick
                ek = (p["src_doc"], p["src"], dst_doc, dst)
                if ek in auto_seen:
                    continue
                auto_seen.add(ek)
                edges.append({"src_doc": p["src_doc"], "src": p["src"],
                              "dst_doc": dst_doc, "dst": dst,
                              "surface": p["surface"], "hint": p["hint"],
                              "block": p.get("block"), "via": via,
                              "rel": p.get("rel", "인용")})
            pending = still
            # 끊긴 간선은 목록에서도 빠진다 — 참조 화면의 끊기(억제 규칙)가
            # 확장(expand_refs)만이 아니라 이 목록에서도 이겨야 검수가 남는다.
            from lawrag.core.rag import verdicts as verdicts_mod   # 순환 의존 회피
            rule_snapshot = verdicts_mod.rule_snapshot()
            redirects = verdicts_mod.redirect_map(snapshot=rule_snapshot)
            edges = [e for e in edges
                     if not verdicts_mod.is_suppressed(
                         e["src_doc"], e["src"], e.get("dst_doc", ""), e["dst"],
                         snapshot=rule_snapshot)]
            edges = [self._redirect(
                         e["src_doc"], e["src"], e, redirects=redirects)
                     for e in edges]
            # 일반 규칙(귀납층)은 인스턴스 재지정 **다음**이다 — 사람이 그
            # 간선에 직접 확정한 좌표가 규칙을 이긴다. off 면 호출 자체가 없어
            # 오늘의 시스템과 같다(RULE_LOOP.md §6 폭발 반경 보증 ④).
            from lawrag.core.rag import rules as rules_mod     # 순환 의존 회피 — 지연
            if rules_mod.mode() != "off":
                edges = [rules_mod.apply_edge(self, e) for e in edges]
                # 사람 우선 재확인 — 규칙이 옮긴 좌표 **위에도** 인스턴스
                # 재지정이 이긴다. 사람이 규칙의 착지를 다시 고쳤다면 그것이
                # 반례이고, 원좌표(규칙_전)로 원장에 귀속된다. 억제는
                # apply_edge 안에서 이미 이겼다(옮기기 전 검사).
                redone = []
                for e in edges:
                    if e.get("via") == "규칙":
                        r2 = self._redirect(
                            e["src_doc"], e["src"], e, redirects=redirects)
                        if r2.get("dst") != e.get("dst"):
                            rules_mod.log_overturn_auto(
                                e.get("rule", ""),
                                {**e, "dst": e.get("규칙_전", e.get("dst"))},
                                "사람 재지정이 규칙 착지를 덮음")
                            e = {k: v for k, v in r2.items()
                                 if k not in ("rule", "규칙_전")}
                    redone.append(e)
                edges = redone
            # 사람이 고친 관계 라벨 — 재지정·규칙이 좌표를 다 정한 다음이라,
            # 사람이 화면에서 본 그 좌표에 정확히 붙는다.
            fixes = self._rel_fix_map()
            for e in edges:
                r = fixes.get((e["src_doc"], e["src"], e.get("dst_doc", ""), e["dst"]))
                if r:
                    e["rel"], e["rel_via"] = r, "사람"
            # Redirects and learned rules run after the first boundary check,
            # so enforce it again on their final landing coordinates.
            edges = [
                edge for edge in edges
                if self.relation_allowed(
                    str(edge.get("src_doc") or ""),
                    str(edge.get("dst_doc") or ""),
                )
            ]
            bounded_pending = []
            for item in pending:
                candidates = [
                    candidate for candidate in item.get("candidates", [])
                    if self.relation_allowed(
                        str(item.get("src_doc") or ""),
                        str(candidate.get("doc_id") or ""),
                    )
                ]
                if candidates:
                    bounded_pending.append({**item, "candidates": candidates})
            pending = bounded_pending
            self._cross = (edges, pending)
        return self._cross

    def cross_ref_edges(self) -> list:
        return self.cross_refs()[0]

    def _cross_adjacency(self) -> tuple[dict, dict]:
        """문서간 간선을 출발/도착 문서별로 한 번 접은 조회창."""
        with self._cache_lock:
            if self._cross_from is None or self._cross_to is None:
                by_src: dict[str, list[dict]] = {}
                by_dst: dict[str, list[dict]] = {}
                for edge in self.cross_ref_edges():
                    by_src.setdefault(edge.get("src_doc", ""), []).append(edge)
                    by_dst.setdefault(edge.get("dst_doc", ""), []).append(edge)
                self._cross_from, self._cross_to = by_src, by_dst
            return self._cross_from, self._cross_to

    def cross_from(self, doc_id: str) -> list[dict]:
        """이 문서에서 나가는 문서간 간선."""
        return self._cross_adjacency()[0].get(doc_id, [])

    def cross_to(self, doc_id: str) -> list[dict]:
        """이 문서로 들어오는 문서간 간선."""
        return self._cross_adjacency()[1].get(doc_id, [])


# 프로세스 안 캐시 — 파일이 바뀌면 다시 세운다. 문서 업로드는 드물고 질의는
# 잦다. 서명은 (문서별 result.json·meta.json mtime, 용어 파일 mtime, 링크 파일
# mtime). meta.json 도 본다 — 이름 변경은 meta 만 고치는데, 이름은 색인이
# 화면에 주는 값이라 서명에 없으면 옛 이름이 재시작 때까지 남는다.
_cache: dict = {}


def _signature(store: Path, terms_file: Path, links_file: Path) -> tuple:
    sig: list = []
    if store.exists():
        for d in sorted(store.iterdir()):
            rj, mj = d / "result.json", d / "meta.json"
            if rj.exists():
                sig.append((d.name, rj.stat().st_mtime_ns,
                            mj.stat().st_mtime_ns if mj.exists() else 0))
    if terms_file.exists():
        sig.append(("__terms__", terms_file.stat().st_mtime_ns))
    if links_file.exists():
        sig.append(("__links__", links_file.stat().st_mtime_ns))
    aliases_file = store.parent / "aliases.json"
    if aliases_file.exists():
        # 별칭 사전도 간선을 움직인다 — 사전을 채우면 다음 질의부터 보여야 한다.
        sig.append(("__aliases__", aliases_file.stat().st_mtime_ns))
    # 통합 관계 번들은 Index 인스턴스에 캐시된다. 공식 위임·법령 가족 파일이
    # 바뀌었는데 같은 Index를 재사용하면 graph와 검색이 다시 갈라지므로 둘도 서명에 넣는다.
    relation_files = (
        ("__delegation__", Path(os.environ.get(
            "RAG_DELEGATION_STORE", store.parent / "delegation.json"))),
        ("__law_index__", Path(os.environ.get(
            "RAG_LAW_INDEX_STORE", store.parent / "law_index.json"))),
    )
    for tag, path in relation_files:
        if path.exists():
            sig.append((tag, path.stat().st_mtime_ns))
    # 간선 규칙(억제·재지정)도 서명에 든다 — 승인 즉시 간선이 옮겨 앉아야
    # "딸깍 수정"이 다음 질의부터 보인다. 재시작을 기다리게 하면 안 된다.
    from lawrag.core.rag import verdicts as verdicts_mod       # 순환 의존 회피 — 지연
    rp = verdicts_mod.rules_path()
    if rp.exists():
        sig.append(("__rules__", rp.stat().st_mtime_ns))
    # 계층 교정도 서명에 든다 — 마디를 옮기면 다음 질의부터 새 트리를 봐야 한다
    from lawrag.core import structure_fixes
    fp = structure_fixes.fixes_path()
    if fp.exists():
        sig.append(("__hfix__", fp.stat().st_mtime_ns))
    # 엔진 스위치도 서명에 든다 — 끄고 켠 것이 다음 질의부터 보여야 스위치다
    from lawrag.core.rag import switches as switches_mod       # 순환 의존 회피 — 지연
    ep = switches_mod.engine_path()
    if ep.exists():
        sig.append(("__engine__", ep.stat().st_mtime_ns))
    # 일반 규칙(귀납층)도 서명에 든다 — 파일 mtime 에 더해 **유효 모드 값**
    # 자체를 싣는다: env 전환·차단기 강하는 파일을 안 만지므로 mtime 만으로는
    # 스위치가 다음 질의에 반영되지 않는다.
    from lawrag.core.rag import rules as rules_mod             # 순환 의존 회피 — 지연
    for tag, p in (("__grules__", rules_mod.rules_file()),
                   ("__breaker__", rules_mod.breaker_file())):
        if p.exists():
            sig.append((tag, p.stat().st_mtime_ns))
    sig.append(("__rmode__", rules_mod.mode()))
    return tuple(sig)


def current() -> Index:
    if _snapshot_adapter_enabled():
        snapshot = current_content_snapshot(required=True)
        assert snapshot is not None  # narrowed by required=True
        sig = ("sourceset-content-snapshot-v1", snapshot.content_fingerprint("lexical"))
        if _cache.get("sig") != sig:
            t0 = time.perf_counter()
            idx = Index.load(content_snapshot=snapshot)
            if idx.content_snapshot_sha256 != snapshot.content_snapshot_sha256:
                raise ContentSnapshotError("lexical index escaped its pinned content snapshot")
            _cache["index"] = idx
            _cache["sig"] = sig
            log.info(
                "SourceSet 색인 로드 — 문서 %d, 항목 %d (%.0fms) — %s",
                len(idx.docs),
                len(idx.entries),
                (time.perf_counter() - t0) * 1000,
                snapshot.content_snapshot_sha256,
            )
        return _cache["index"]

    store, tf, lf = store_path(), terms_path(), links_path()
    sig = _signature(store, tf, lf)
    if _cache.get("sig") != sig:
        t0 = time.perf_counter()
        idx = Index.load(store, tf, lf)
        _cache["index"] = idx
        _cache["sig"] = sig
        log.info("색인 재구축 — 문서 %d, 항목 %d (%.0fms) — %s",
                 len(idx.docs), len(idx.entries),
                 (time.perf_counter() - t0) * 1000, store)
    return _cache["index"]
