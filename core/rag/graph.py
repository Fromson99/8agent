"""코퍼스 그래프 — 구조화 산출을 연결관계로 편다. DB 없이.

원본(DELTAFlow)의 그래프는 Neo4j 에 있었다: 용어(GlossaryTerm)와 문단(OocPara)
이 MENTIONS 로 이어지고, 같은 뜻은 SAME_AS·GROUPS 로 묶이며, 탐험(OQL)이 그
위를 걸었다. 여기서는 같은 모양을 색인에서 바로 세운다 —

    정점   문서 · 구역(마디) · 용어
    간선   계층      부모 ↔ 자식 (구조 트리 그대로)
          출현      용어 → 구역 (MENTIONS 대응, via 제목/본문/표 무게 유지)
          공유      같은 정규형 제목·용어가 문서를 가로질러 잇는다 (SAME_AS 대응)
          참조      구역 → 구역 (본문의 "제4조를 참고한다" — refs.py 가 결정론으로 잇는다)

간선을 타입별로 갈라 둔 이유: 걷기(탐험)가 어느 간선을 몇 번 탔는지가 곧
회수 경위다. 한 인접 리스트에 섞으면 "어떻게 여기 왔나"를 되짚을 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.rag.index import Index

Sec = tuple[str, int]              # (doc_id, node_id) — 구역 좌표


@dataclass
class Graph:
    index: Index
    parent: dict = field(default_factory=dict)      # Sec -> Sec
    children: dict = field(default_factory=dict)    # Sec -> [Sec]
    term_secs: dict = field(default_factory=dict)   # 용어 key -> [(Sec, via)]
    sec_terms: dict = field(default_factory=dict)   # Sec -> [용어 key]
    ref_out: dict = field(default_factory=dict)     # Sec -> [(Sec, 표면형)] — 참조하는 쪽
    ref_in: dict = field(default_factory=dict)      # Sec -> [(Sec, 표면형)] — 참조받는 쪽

    # ------------------------------------------------------------- 구성
    @classmethod
    def from_index(cls, index: Index) -> "Graph":
        g = cls(index=index)
        # 계층 — 뷰어 페이로드의 parent 포인터 그대로
        for doc_id, v in index.docs.items():
            for n in v.nodes:
                nid, pid = n.get("id"), n.get("parent")
                if pid is not None:
                    g.parent[(doc_id, nid)] = (doc_id, pid)
                    g.children.setdefault((doc_id, pid), []).append((doc_id, nid))
        # 출현 — 제목 엔트리는 그 구역이 그 말을 **다루는** 자리(via 제목),
        # 용어 엔트리는 훑어 둔 출현 좌표를 그대로 싣는다.
        for e in index.entries:
            if e.kind == "제목" and e.node is not None:
                g._mention(e.key, (e.doc_id, e.node), "제목")
            for o in e.occurrences:
                if o.get("doc_id") and o.get("node") is not None:
                    g._mention(e.key, (o["doc_id"], o["node"]),
                               o.get("via", "본문"))
        # 참조 — 본문의 "제4조를 참고한다"(refs.py 가 결정론으로 이어 둔다).
        for doc_id, edges in index.ref_edges().items():
            for e in edges:
                src, dst = (doc_id, e["src"]), (doc_id, e["dst"])
                g.ref_out.setdefault(src, []).append((dst, e["surface"]))
                g.ref_in.setdefault(dst, []).append((src, e["surface"]))
        # 문서 사이 참조 — 이름 대조 확정 + links.json 의 판정 결과.
        for e in index.cross_ref_edges():
            src, dst = (e["src_doc"], e["src"]), (e["dst_doc"], e["dst"])
            g.ref_out.setdefault(src, []).append((dst, e["surface"]))
            g.ref_in.setdefault(dst, []).append((src, e["surface"]))
        return g

    def _mention(self, key: str, sec: Sec, via: str) -> None:
        rows = self.term_secs.setdefault(key, [])
        if not any(s == sec for s, _ in rows):
            rows.append((sec, via))
            self.sec_terms.setdefault(sec, []).append(key)

    # ------------------------------------------------------------- 걷기
    def sections_of(self, term_key: str) -> list[tuple[Sec, str]]:
        """용어 → 구역들. 제목 출현이 먼저 온다 — 다루는 자리가 언급보다 세다."""
        rows = self.term_secs.get(term_key, [])
        return sorted(rows, key=lambda r: 0 if r[1] == "제목" else 1)

    def terms_of(self, sec: Sec) -> list[str]:
        return list(self.sec_terms.get(sec, []))

    def references(self, sec: Sec) -> list[tuple[Sec, str]]:
        """이 구역 본문이 가리키는 구역들 — (구역, "제4조" 표면형)."""
        return list(self.ref_out.get(sec, []))

    def cited_by(self, sec: Sec) -> list[tuple[Sec, str]]:
        """이 구역을 가리키는 구역들 — 역방향. "제4조는 어디서 쓰이나"."""
        return list(self.ref_in.get(sec, []))

    def siblings(self, sec: Sec) -> list[Sec]:
        p = self.parent.get(sec)
        if p is None:
            return []
        return [s for s in self.children.get(p, []) if s != sec]

    def bridge(self, sec: Sec, cap: int = 12) -> list[tuple[Sec, str]]:
        """구역 → 그 구역의 용어 → **다른 문서**의 구역 (2-hop, 문서 가로지르기).

        원본 collect_connected 의 핵심 걸음이다: "찾은 것의 연결관계를 타고
        문서를 들고와야지, 문자열로 다시 찾지 말고." 같은 문서 안은 계층
        (siblings/children)이 담당하므로 여기서는 건너뛴다.
        """
        out: list[tuple[Sec, str]] = []
        seen: set[Sec] = {sec}
        for key in self.terms_of(sec):
            for other, via in self.sections_of(key):
                if other in seen or other[0] == sec[0]:
                    continue
                seen.add(other)
                out.append((other, key))
                if len(out) >= cap:
                    return out
        return out

    def shared_terms(self) -> dict[str, list[Sec]]:
        """여러 문서에 걸친 용어 — 이 어휘의 뼈대 (용어집 화면과 같은 기준)."""
        out = {}
        for key, rows in self.term_secs.items():
            docs = {s[0] for s, _ in rows}
            if len(docs) > 1:
                out[key] = [s for s, _ in rows]
        return out

    # ------------------------------------------------------------- 지형도
    def terrain(self, top_level: int = 1, cap_per_doc: int = 12) -> list[dict]:
        """문서마다 최상위 구역들 — 의미 회수 LLM 에게 주는 "이 시스템이 실제로
        보유한 구역" 지도. 원본의 지형도(ooc class 그룹) 대응."""
        out = []
        for doc_id, v in self.index.docs.items():
            tops = [n for n in v.nodes if n.get("parent") is None][:cap_per_doc]
            out.append({
                "doc_id": doc_id, "doc": v.name,
                "sections": [{"node": n.get("id"),
                              "title": (n.get("title") or n.get("surface") or "")}
                             for n in tops],
                "n_sections": len(v.nodes)})
        return out
