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

import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent

log = logging.getLogger("core.rag.index")

# 저장소 경로 — api/routers/glossary.py 와 같은 규약. env 가 정본이고,
# 없으면 CLI 산출 자리를 본다.
def store_path() -> Path:
    return Path(os.environ.get("STRUCTURE_STORE", ROOT / "out" / "structure" / "viewer"))


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

    @classmethod
    def build(cls, doc_id: str, meta: dict, res: dict) -> "DocView":
        from core import structure_fixes           # 지연 — 순환 회피

        # 계층 사후 교정을 겹쳐 읽는다 — 사람이 옮긴 마디는 재해석 뒤에도
        # 제자리에 있어야 한다(경로·회수·참조 해소가 전부 이 트리를 본다).
        nodes = structure_fixes.apply(doc_id, res.get("nodes", []))
        v = cls(doc_id=doc_id, name=meta.get("name", doc_id),
                nodes=nodes, blocks=res.get("blocks", []))
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

    def path(self, node_id: Optional[int]) -> str:
        """마디의 조상 사슬 — `제2장 ▸ 제19조 ▸ 제3항`. 이것이 인용 좌표의
        사람이 읽는 형태다.

        표면(마커)과 제목을 **둘 다** 쓴다 — 제목만 쓰면 "제22조 (광고 관련
        준수사항)"이 "광고 관련 준수사항"으로 떠서, 참조 검수 화면에서 제22조
        마디가 계층에 없는 것처럼 읽힌다(실측 2026-08-12: 멀쩡한 구조를 계층
        결손으로 오판하게 했다)."""
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
        return " ▸ ".join(reversed(parts))

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
    """본문 색인용 토큰 — archive/trust-parser-v1 chunk_search 와 같은 꼴.
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
    docs: dict                     # doc_id -> DocView
    entries: list                  # Entry 목록 (제목 + 용어)
    saved_links: list = field(default_factory=list)   # links.json — 판정으로 고정된 링크
    _postings: Optional[dict] = None
    _n_blocks: int = 0
    _refs: Optional[dict] = None
    _cross: Optional[tuple] = None

    # ------------------------------------------------------------- 구성
    @classmethod
    def from_docs(cls, docs: list[tuple[str, dict, dict]],
                  user_terms: Optional[list[dict]] = None,
                  saved_links: Optional[list[dict]] = None) -> "Index":
        """(doc_id, meta, result) 목록에서 색인을 세운다. 파일이 아니라 값을
        받는다 — 시험이 저장소 없이 색인을 만들 수 있어야 한다."""
        views: dict[str, DocView] = {}
        entries: list[Entry] = []
        for doc_id, meta, res in docs:
            v = DocView.build(doc_id, meta, res)
            views[doc_id] = v
            for n in v.nodes:
                label = (n.get("title") or "").strip() or (n.get("surface") or "").strip()
                if not _is_name(label):
                    continue
                entries.append(Entry(
                    value=label, key=norm(label), kind="제목",
                    target=f"doc:{doc_id}:{n.get('id')}",
                    doc_id=doc_id, doc=v.name, node=n.get("id")))
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
        return cls(docs=views, entries=entries, saved_links=saved_links or [])

    @classmethod
    def load(cls, store: Optional[Path] = None,
             terms_file: Optional[Path] = None,
             links_file: Optional[Path] = None) -> "Index":
        """저장소에서 색인을 세운다. 해석 산출이 있는 문서만 싣는다."""
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
        if links_file.exists():
            try:
                links = json.loads(links_file.read_text(encoding="utf-8")).get("links", [])
            except Exception:
                links = []
        return cls.from_docs(docs, terms, links)

    # ------------------------------------------------------------- 본문 색인
    def postings(self) -> dict:
        """블록 본문의 렉시컬 색인 — 제목·용어가 다 빗나갔을 때의 마지막 단.
        쓰일 때 처음 세운다(문서가 많아도 첫 폴백 전까지는 공짜)."""
        if self._postings is None:
            self._postings = {}
            n = 0
            for doc_id, v in self.docs.items():
                for b in v.blocks:
                    n += 1
                    for t in _lex_terms(b.get("text") or ""):
                        self._postings.setdefault(t, {}).setdefault(
                            (doc_id, b.get("idx")), 0)
                        self._postings[t][(doc_id, b.get("idx"))] += 1
            self._n_blocks = max(n, 1)
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
    def _redirect(self, src_doc: str, src, edge: dict) -> dict:
        """승인된 재지정(edge_rules.json)을 간선 하나에 적용한다 — 사람이
        "제2조가 아니라 제2조 제3항"이라 확정한 좌표로 도착을 옮겨 앉힌다.
        새 좌표가 실재할 때만 옮긴다(구조가 다시 서면 노드가 사라질 수 있다)."""
        from core.rag import verdicts as verdicts_mod   # 순환 의존 회피 — 지연
        r = verdicts_mod.redirect_map().get(
            (src_doc, src, edge.get("dst_doc", src_doc), edge["dst"]))
        if r is None:
            return edge
        dv = self.docs.get(edge.get("dst_doc", src_doc))
        if dv is None or dv.by_id.get(r["new_dst"]) is None:
            return edge
        return {**edge, "dst": r["new_dst"], "via": "교정"} \
            if "dst_doc" in edge else {**edge, "dst": r["new_dst"]}

    def ref_edges(self) -> dict:
        """문서별 조문 상호참조 간선 — doc_id -> [{"src","dst","surface","block"}].
        본문의 "제4조를 참고한다" 가 구역을 가로로 잇는다. 쓰일 때 처음
        세운다(postings 와 같은 규율). 승인된 재지정이 있으면 도착이 옮겨 앉는다."""
        if self._refs is None:
            from core.rag import refs as refs_mod       # 순환 의존 회피 — refs 는 DocView 타입만 본다
            self._refs = {doc_id: [self._redirect(doc_id, e["src"], e)
                                   for e in refs_mod.resolve(v)]
                          for doc_id, v in self.docs.items()}
        return self._refs

    def cross_refs(self) -> tuple:
        """문서 사이 참조 — (확정 간선, 보류 목록).

        결정론 대조(refs.cross_resolve)에 links.json 의 판정 결과를 합친다.
        저장된 링크는 좌표가 아직 유효한 것만 싣고, 그 링크가 정착시킨 보류
        항목은 목록에서 뺀다 — 한 번 판정한 것을 다시 묻지 않는다."""
        if self._cross is None:
            from core.rag import refs as refs_mod
            edges, pending = refs_mod.cross_resolve(self.docs)
            covered: set = set()
            for lk in self.saved_links:
                dv = self.docs.get(lk.get("dst_doc"))
                if (lk.get("src_doc") not in self.docs or dv is None
                        or dv.by_id.get(lk.get("dst")) is None):
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
            still = []
            for p in pending:
                uniq = {(c["doc_id"], c["node"]) for c in p["candidates"]}
                if len(uniq) != 1:
                    still.append(p)
                    continue
                dst_doc, dst = next(iter(uniq))
                ek = (p["src_doc"], p["src"], dst_doc, dst)
                if ek in auto_seen:
                    continue
                auto_seen.add(ek)
                # via 는 화면에 그대로 뜨는 말이다. "추정" — 이름을 안 부른
                # 참조인데 그 조를 가진 문서가 하나뿐이라 그리 이었다는 뜻.
                # (이름대조=확실 / 추정=후보 유일 / 보류=후보 여럿)
                edges.append({"src_doc": p["src_doc"], "src": p["src"],
                              "dst_doc": dst_doc, "dst": dst,
                              "surface": p["surface"], "hint": p["hint"],
                              "block": p.get("block"), "via": "추정"})
            pending = still
            # 끊긴 간선은 목록에서도 빠진다 — 참조 화면의 끊기(억제 규칙)가
            # 확장(expand_refs)만이 아니라 이 목록에서도 이겨야 검수가 남는다.
            from core.rag import verdicts as verdicts_mod   # 순환 의존 회피
            edges = [e for e in edges
                     if not verdicts_mod.is_suppressed(
                         e["src_doc"], e["src"], e.get("dst_doc", ""), e["dst"])]
            edges = [self._redirect(e["src_doc"], e["src"], e) for e in edges]
            self._cross = (edges, pending)
        return self._cross

    def cross_ref_edges(self) -> list:
        return self.cross_refs()[0]


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
    # 간선 규칙(억제·재지정)도 서명에 든다 — 승인 즉시 간선이 옮겨 앉아야
    # "딸깍 수정"이 다음 질의부터 보인다. 재시작을 기다리게 하면 안 된다.
    from core.rag import verdicts as verdicts_mod       # 순환 의존 회피 — 지연
    rp = verdicts_mod.rules_path()
    if rp.exists():
        sig.append(("__rules__", rp.stat().st_mtime_ns))
    # 계층 교정도 서명에 든다 — 마디를 옮기면 다음 질의부터 새 트리를 봐야 한다
    from core import structure_fixes
    fp = structure_fixes.fixes_path()
    if fp.exists():
        sig.append(("__hfix__", fp.stat().st_mtime_ns))
    return tuple(sig)


def current() -> Index:
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
