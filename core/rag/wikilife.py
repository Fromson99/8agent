"""위키 아티클의 생애 주기 — 공리 루프(잠정→규칙→정착)의 지식판.

규칙에게 4기준 보고서(성숙·안정·하중·부검)와 promotable 권고가 있듯,
아티클에게도 같은 판을 준다. 신호는 전부 이미 있는 것에서 파생된다
(저장하는 상태 없음 — 보고서는 언제나 다시 계산된다):

    성숙   Raw 필드의 출처 등급 구성 — llm-wiki 의 Raw 링크가 그대로 신호다.
           법제처 해석례(raw/expc) > 문답(raw/conversations). 문답발만이면 잠정.
    안정   Status 블록(llm-wiki 의 Outdated·Disputed 마킹) 수 — 분쟁 중인
           주장이 있으면 불안정.
    하중   적중 원장(wikiledger)의 주입 횟수 — 실전에서 얼마나 쓰이나.
    부검   주입된 질의의 피드백 정답/오답 — 끼면 답이 맞는가.

권고는 코드 결정론이고, 아티클을 고치는 것(재컴파일·Disputed 마킹·강등)은
위키를 소유한 LLM 세션과 사람의 몫이다 — 규칙의 정착 승격을 사람만 누르는
것과 같은 이유다.

기계 규칙과의 왕복도 여기 산다: 규칙이 정착(AXIOM)에 오르면 "왜"를
아티클로 남기라고 위키 log 에 컴파일 대기를 적고, 정착이 강등되면 그 규칙을
인용한 아티클을 재심 대상으로 적는다 (note_rule_transition — rules.set_status
가 부른다). 아티클이 규칙을 인용할 때는 본문에 `rule:<id>` 표기를 쓴다.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from core.rag import wikictx, wikiledger

_RAW_LINK_RE = re.compile(r"\]\((?:\.\./)+raw/(?P<topic>[^/)]+)/[^)]+\.md\)")
_STATUS_RE = re.compile(r"\*\*Status:\s*(?P<kind>Outdated|Disputed)\*\*")
_RULE_REF_RE = re.compile(r"rule:([\w\-.]+)")


def _rule_statuses() -> dict[str, str]:
    """규칙 id → 상태. 규칙 스토어가 없으면 빈 판 — 위키는 규칙 없이도 산다."""
    try:
        from core.rag import rules as rules_mod
        import json
        p = rules_mod.rules_file()
        rows = json.loads(p.read_text("utf-8")).get("rules", []) if p.exists() else []
        return {r.get("id", ""): r.get("status", "") for r in rows}
    except Exception:
        return {}


def report() -> dict[str, dict]:
    """아티클별 생애 보고서 — {slug: {성숙, 안정, 하중, 부검, 권고, …}}."""
    perf = wikiledger.stats()
    rule_status = _rule_statuses()
    out: dict[str, dict] = {}
    for row in wikictx._rows():
        text = row["text"]
        # 공적 출처(해석례·금융위 회신·판례·교과서)와 문답을 가른다 — 성숙의 축
        raws = {"expc": 0, "fsc": 0, "prec": 0, "moleg": 0,
                "conversations": 0, "기타": 0}
        for m in _RAW_LINK_RE.finditer(text):
            topic = m.group("topic")
            raws[topic if topic in raws else "기타"] += 1
        official = raws["expc"] + raws["fsc"] + raws["prec"] + raws["moleg"]
        status = {"Outdated": 0, "Disputed": 0}
        for m in _STATUS_RE.finditer(text):
            status[m.group("kind")] += 1
        # 강등·보류된 규칙을 인용한 채로 서 있는 아티클 — 재심 대상
        stale_rules = sorted({rid for rid in _RULE_REF_RE.findall(text)
                              if rule_status.get(rid) not in (None, "", "규칙", "정착")})
        p = perf.get(row["slug"], {"주입": 0, "정답": 0, "오답": 0})

        if status["Disputed"] > 0 or stale_rules:
            reco = "분쟁 중"
        elif p["오답"] >= 2 and p["오답"] > p["정답"]:
            reco = "재컴파일 후보"
        elif official == 0 and raws["conversations"] > 0:
            reco = "재검증 필요"          # 문답발만 — 공적 출처로 굳혀야 한다
        else:
            reco = "유지"

        judged = p["정답"] + p["오답"]
        out[row["slug"]] = {
            "title": row["title"],
            "성숙": {"해석례": raws["expc"], "회신": raws["fsc"],
                   "판례": raws["prec"], "교과서": raws["moleg"],
                   "문답": raws["conversations"],
                   "게이지": min(1.0, official / 5)},
            "안정": {"outdated": status["Outdated"], "disputed": status["Disputed"],
                   "게이지": max(0.0, 1.0 - status["Disputed"] * 0.5
                                 - status["Outdated"] * 0.25)},
            "하중": {"주입": p["주입"], "게이지": min(1.0, p["주입"] / 5)},
            "부검": {"정답": p["정답"], "오답": p["오답"],
                   "게이지": (p["정답"] / judged) if judged else None},
            "권고": reco,
            **({"재심_규칙": stale_rules} if stale_rules else {}),
        }
    return out


# ---------------------------------------------------------------- 규칙 ↔ 위키 왕복

def _append_log(entry: str) -> None:
    p = wikictx.wiki_dir() / "log.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    base = p.read_text("utf-8") if p.is_file() else "# Wiki Log\n"
    p.write_text(base.rstrip("\n") + "\n\n" + entry.strip() + "\n", "utf-8")


def note_rule_transition(rule_id: str, old: str, new: str,
                         rationale: str = "", by: str = "") -> bool:
    """규칙 상태 전이를 위키 연대기에 잇는다 — 정착 승격은 컴파일 대기("왜"를
    아티클로), 정착 강등은 재심(그 규칙을 인용한 아티클에 Disputed 검토).
    그 밖의 전이는 위키의 일이 아니다. 적었으면 True."""
    today = time.strftime("%Y-%m-%d")
    if new == "정착":
        _append_log(
            f"## [{today}] rule | 컴파일 대기: 정착 규칙 rule:{rule_id}\n"
            f"- Disposition: New\n"
            f"- 근거: {rationale or '(규칙 rationale 없음)'} (by {by})\n"
            f"- 요지: 정착(AXIOM)에 오른 기계 규칙의 '왜'를 아티클로 남긴다 — "
            f"본문에 rule:{rule_id} 표기로 인용하면 강등 시 재심이 자동으로 걸린다")
        return True
    if old == "정착":
        _append_log(
            f"## [{today}] rule | 재심: 정착 강등 rule:{rule_id} → {new}\n"
            f"- Disposition: Disputed\n"
            f"- 요지: 이 규칙을 rule:{rule_id} 로 인용한 아티클은 생애 보고서가 "
            f"'분쟁 중'으로 표시한다 — Status: Disputed 블록 검토 (by {by})")
        return True
    return False
