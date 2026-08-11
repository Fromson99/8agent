"""검사 항목 파이프라인 — 미리 정한 질문을 두 문서에서 찾아 대조한다.

    run(계약서.pdf, 투자설명서.pdf) → Report

기존 run(pipeline.py)과 두 가지가 다르다.

**구조화가 병렬이다.** 두 문서는 서로를 모른다 — 한쪽이 끝나기를 기다릴
이유가 없다. 파싱·구조화가 런타임의 대부분이라 여기가 절반이 된다.

**범위를 경로가 아니라 용어로 찾는다.** 기존 규칙은 형식을 아는 사람이
section 경로를 못박았다("별지1/신탁계약 세부내역"). 검사 항목은 반대다 —
사용자는 "기간·보상금 검사해줘"라고 말할 뿐 값이 어느 구역에 있는지 모른다.
그래서 용어가 나오는 구역을 찾고(제목 먼저, 본문 다음), 그 구역 전체를
근처값으로 증거 표에 편다. 값을 **고르는** 일은 여전히 판정(judge)이 하고,
출처는 여전히 증거 ID 로만 돌아온다 — 찾는 방식이 바뀌어도 출처 위조를
막는 장치는 그대로다.

지금은 두 문서에 같은 용어가 나온다고 가정한다(항목의 term 하나로 양쪽을
찾는다). 문서마다 말이 다른 경우는 항목의 aliases 와 등록부 용어집이 받는다.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AGENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_ROOT.parent.parent
for p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml                                             # noqa: E402
import judge as judge_mod                               # noqa: E402
import pipeline                                         # noqa: E402
import scope as scope_mod                               # noqa: E402
import service                                          # noqa: E402
from core.glossary import normalize                     # noqa: E402
from core.rag import adapt as rag_adapt                 # noqa: E402
from core.rag.search import search as rag_search        # noqa: E402
from core.structurize import Document                   # noqa: E402

CHECKS = AGENT_ROOT / "tasks" / "agent1_checklist.yaml"
MAX_SECTIONS = 6           # 용어 하나가 끌어오는 구역 상한 — 근처값이 문서 절반이 되면 안 된다


def load_checks(path=None) -> list[dict]:
    data = yaml.safe_load(Path(path or CHECKS).read_text(encoding="utf-8"))
    return data.get("checks", [])


# ---------------------------------------------------------------------------
# 용어로 범위 찾기 — 결정론. 어디를 봤는지가 기록으로 남는다.
# ---------------------------------------------------------------------------

@dataclass
class Found:
    """한 문서에서 용어가 어디에 있었나 — 스코프를 만들기 전의 발견 기록."""
    term: str
    how: str                                  # "제목" | "본문" | "탐색" | "없음"
    section_ids: list = field(default_factory=list)
    surfaces: list = field(default_factory=list)
    trail: list = field(default_factory=list)  # 탐색(사다리)이었으면 — 왜 이 구역인가

    def dump(self) -> dict:
        d = {"term": self.term, "how": self.how,
             "sections": self.section_ids, "surfaces": self.surfaces}
        if self.trail:
            d["trail"] = self.trail
        return d


def _surfaces(term: str, aliases: list[str], glossary) -> list[str]:
    """찾을 표면형 — 항목의 term·aliases 에 등록부 용어집의 별칭을 합친다."""
    out = [term, *aliases]
    if glossary is not None:
        try:
            out += glossary.surfaces_of(term)
        except Exception:
            pass
    seen, uniq = set(), []
    for s in out:
        n = normalize(s)
        if n and n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def find_sections(doc: Document, term: str, aliases: Optional[list[str]] = None,
                  glossary=None, cap: int = MAX_SECTIONS) -> Found:
    """용어가 나오는 구역을 찾는다 — 제목 먼저, 본문 다음.

    제목에 있으면 그 구역이 그 말을 **다루는** 자리다(용어집 화면과 같은 구분).
    제목 매칭이 하나도 없을 때만 본문 언급으로 내려가고, 그때는 언급이 많은
    구역부터 담는다. 상한(cap)을 두는 이유: 근처값을 들고 오자는 것이지 문서를
    통째로 올리자는 것이 아니다.
    """
    surfs = _surfaces(term, aliases or [], glossary)
    found = Found(term=term, how="없음", surfaces=surfs)

    # ── 제목 — 경로 성분 어디든 용어가 들어 있으면 그 구역 ──
    titles: list[str] = []
    for sec in doc.sections:
        hay = [normalize(c) for c in sec.path]
        if any(s in h for s in surfs for h in hay if h):
            titles.append(sec.section_id)
    if titles:
        found.how, found.section_ids = "제목", titles[:cap]
        return found

    # ── 본문 — 내용에 용어가 든 구역, 언급 수로 줄 세운다 ──
    counted: list[tuple[int, str]] = []
    for sec in doc.sections:
        n = 0
        for item in sec.content:
            if item.get("type") == "table":
                text = " ".join(c.get("text", "")
                                for c in item.get("cells", {}).get("cells", []))
            else:
                text = item.get("text") or ""
            t = normalize(text)
            n += sum(1 for s in surfs if s in t)
        if n:
            counted.append((n, sec.section_id))
    counted.sort(key=lambda x: (-x[0], x[1]))
    if counted:
        found.how = "본문"
        found.section_ids = [sid for _, sid in counted[:cap]]
        return found

    # ── 탐색 — 정확 매칭이 다 빗나가면 RAG 검색 사다리를 빌린다. ──
    # 위 두 단은 표면형⊂문서 한 방향뿐이다. 사다리는 반대 방향(제목⊂질의)과
    # trigram 유사도, 접두 확장 tf·idf 까지 내려간다 — `중도해지수수료율` 로
    # 물어도 `중도해지수수료` 구역을, `청약철회권을` 로 물어도 본문의
    # `청약철회권` 을 찾는다. 근거가 약한 만큼 결과는 "탐색" 으로 표시되고
    # 판정에 경고가 붙는다 — 조용히 정확 매칭인 척하지 않는다.
    idx, sec_of = rag_adapt.index_of(doc)
    best: dict[str, tuple[float, str]] = {}
    for q in dict.fromkeys([term, *(aliases or [])]):
        r = rag_search(idx, q)
        for h in r.hits:
            sid = sec_of.get(h.node)
            if sid is None:
                continue
            why = f"'{q}' {h.match} — {h.value[:30]} ({'; '.join(h.reasons)})"
            cur = best.get(sid)
            if cur is None or h.score > cur[0]:
                best[sid] = (h.score, why)
    if best:
        ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[:cap]
        found.how = "탐색"
        found.section_ids = [sid for sid, _ in ranked]
        found.trail = [f"{sid} ← {why}" for sid, (_, why) in ranked]
    return found


def term_scope(doc: Document, doc_label: str, term: str,
               aliases: Optional[list[str]] = None,
               glossary=None) -> tuple[scope_mod.Scope, Found]:
    """용어로 찾은 구역들을 증거 표로 편다 — 찾기(여기)와 펴기(scope.build)의 분업."""
    found = find_sections(doc, term, aliases, glossary)
    sc = scope_mod.build(doc, doc_label, found.section_ids,
                         terms=[term, *(aliases or [])], glossary=glossary)
    return sc, found


# ---------------------------------------------------------------------------
# 검사 실행
# ---------------------------------------------------------------------------

def check_docs(src_doc: Document, tgt_doc: Document, checks: list[dict], llm,
               src_glossary=None, tgt_glossary=None,
               report: Optional[pipeline.Report] = None,
               keep_scopes: bool = True) -> pipeline.Report:
    """구조화가 끝난 두 문서에 검사 항목을 돌린다 — 시험이 PDF 없이 부를 수 있는 몸통."""
    report = report or pipeline.Report(
        contract_file=src_doc.source_file, prospectus_file=tgt_doc.source_file,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=getattr(llm, "model", ""))

    for check in checks:
        term = check.get("term", "")
        aliases = list(check.get("aliases") or [])

        s_scope, s_found = term_scope(src_doc, "계약서", term, aliases, src_glossary)
        t_scope, t_found = term_scope(tgt_doc, "투자설명서", term, aliases, tgt_glossary)

        # 정답 쪽에 용어 자체가 없으면 판정을 부를 것이 없다 — LLM 없이 내린다.
        # (대상 쪽만 없는 경우는 판정에 맡긴다: 정답 값을 뽑아 MISSING_IN_TARGET
        #  으로 내리는 것까지가 판정의 일이다.)
        if not s_scope.evidence:
            j = judge_mod.Judgement(
                term=term, verdict="SOURCE_EXTRACTION_FAILED", method="search",
                reason=f"계약서에서 '{term}' 을 찾지 못했습니다 "
                       f"(찾은 표면형: {', '.join(s_found.surfaces)})")
        else:
            j = judge_mod.judge(term, s_scope, t_scope, llm,
                                note=check.get("note", ""))
            j.method = "checklist"
            # 범위가 유사 검색으로 찾아졌으면 그 사실이 리포트에 남아야 한다 —
            # 값 선택은 여전히 증거 ID 로 묶여 있지만, 범위의 근거가 약하다.
            for label, f in (("계약서", s_found), ("투자설명서", t_found)):
                if f.how == "탐색":
                    j.warnings.append(
                        f"{label} 범위는 유사 검색(사다리)으로 찾았습니다 — "
                        "용어가 정확히 일치하지 않습니다")
        j.term = term
        report.rows.append(j)

        if keep_scopes:
            report.scopes[check.get("id") or term] = {
                "check_id": check.get("id", ""),
                "found": {"contract": s_found.dump(), "prospectus": t_found.dump()},
                "contract": s_scope.dump(), "prospectus": t_scope.dump()}

    report.usage = llm.totals() if hasattr(llm, "totals") else {}
    return report.recount()


def run(contract: str | Path, prospectus: str | Path,
        checks_path: Optional[str | Path] = None, llm=None,
        keep_scopes: bool = True) -> pipeline.Report:
    """파일 두 개를 받아 검사한다 — 구조화는 병렬, 판정은 항목 순서대로."""
    checks = load_checks(checks_path)

    # 두 문서는 서로 독립이다 — 나란히 구조화한다. 예외는 result() 가 그대로
    # 올린다(먼저 끝난 쪽의 실패도, 메시지도 잃지 않는다).
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_src = ex.submit(service.structurize_contract, contract)
        f_tgt = ex.submit(service.structurize_prospectus, prospectus)
        src, tgt = f_src.result(), f_tgt.result()

    if llm is None:
        from core.llm import LLM
        llm = LLM()

    report = pipeline.Report(
        contract_file=Path(contract).name, prospectus_file=Path(prospectus).name,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=getattr(llm, "model", ""),
        gate={"contract": src.doc.fitness, "prospectus": tgt.doc.fitness})

    return check_docs(src.doc, tgt.doc, checks, llm,
                      src_glossary=src.glossary, tgt_glossary=tgt.glossary,
                      report=report, keep_scopes=keep_scopes)
