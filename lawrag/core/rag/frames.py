"""조문 프레임 — "누가 → 무엇을 → 누구에게 → 한다"를 마디마다 뽑아 둔 파생층.

문체 번역(docs/QUERY_TRANSLATION.md)이 못 넘는 벽이 어휘 격차였다 — 모델은
국세기본법이 "다른 기관에서 받아감"을 "협조 요청"이라 부른다는 것을 모른다.
모르는 낱말은 규칙으로 안 나온다. 그래서 낱말을 **코퍼스에서 미리 뽑아 둔다**:
조문마다 주체(actor)·상대(target)·행위(act)·객체(object)·문형을 뽑아 두면,
질의 시점의 일이 "조문 낱말을 지어내기"에서 "뽑아 둔 행위 어휘 중 고르기"로
바뀐다(열린 생성 → 닫힌 선택). 외부 설계 검토(2026-08-18, 노드·엣지 용어집)의
착지다 — 스키마의 actor_ids/target_ids/act_id/object_ids 자리.

규율 (tags.py 와 같다):
- **파생층**이다 — result.json 은 불변, 프레임은 data/frames/<doc_id>.jsonl.
  다시 뽑으면 그 파일만 바뀐다.
- **원문 표기 그대로** — actor·act·object 는 마디 본문의 표면형으로 쓰게 한다
  (프롬프트 규칙). 코드의 부분 문자열 검증은 뺐다 — 괄호 삽입·어미 변형에
  옳은 것까지 떨어뜨렸다(_grounded 머리). 정규명("tax_official")은 여기서
  만들지 않는다 — 정규화(별칭 병합)는 2차, 용어 사전의 병합키와 같은 자리.
- 단위는 **항**(없으면 조) — 프레임의 자연 단위다. 콜은 조 하나에 한 번,
  출력이 항마다 프레임 목록. 42문서 본문 조 5,504 · 항 21,424.
- LLM 은 하이쿠 — 뽑기(추출)지 판단이 아니다. 실패한 조는 빈 프레임으로
  남기고 다음 조로 간다(fail-open, 재실행이 그 조만 다시 뽑는다).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import DocView, Index, store_path

log = logging.getLogger("lawrag.core.rag.frames")

_JO = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")
MODEL = os.environ.get("RAG_FRAMES_MODEL", "claude-haiku-4-5-20251001")
WORKERS = int(os.environ.get("RAG_FRAMES_WORKERS", "6"))
JO_CHARS = 6000              # 조 하나 입력 상한 — 넘으면 앞을 자른다(별표류 폭주 방지)
MAX_TOKENS = int(os.environ.get("RAG_FRAMES_MAX_TOKENS", "4000"))   # 잘리면 3배로 1회 재시도

SYSTEM = (
    "너는 한국 법령 조문의 **프레임 추출기**다. 조 하나의 본문(항·호 단위로 id 가 "
    "붙어 있다)을 받아, 규범 문장마다 '누가(actor) → 무엇을(object) → 누구에게"
    "(target) → 한다(act)'를 뽑는다.\n"
    "규칙 — 위반은 곧 오답:\n"
    "① **본문에 실제로 있는 낱말만** 쓴다. actor·target·object·act 는 그 마디 "
    "본문의 표면형 그대로다(예: '세무공무원', '국가기관', '협조를 요청'). 바꿔 "
    "쓰거나 요약하거나 정규화하지 마라 — '국세청'이 본문에 없으면 쓰지 않는다.\n"
    "② act 는 **술어구**다 — '협조를 요청', '제공', '열람을 요구', '보고하여야'. "
    "명사 하나('협조')보다 본문의 동사구('협조를 요청')를 쓴다.\n"
    "③ 문형(mode)은 술어 끝으로 가른다 — 의무(하여야 한다) · 금지(하여서는 아니 "
    "된다·할 수 없다) · 허용(할 수 있다) · 절차(승인·인가·심의를 거쳐) · 위임"
    "(대통령령으로 정한다) · 간주(로 본다) · 정의(이란 …를 말한다) · 기타.\n"
    "④ 기능(function)은 그 문장이 규범에서 하는 일 — 근거·권한(행위를 가능하게 함) "
    "· 제한(행위를 막거나 좁힘) · 절차(밟아야 할 순서) · 위임(아래로 내려보냄) · "
    "정의(낱말의 뜻) · 효과(법률효과·간주) · 기타.\n"
    "⑤ 마디(id)마다 프레임은 0~3개. 정의 조·목적 조처럼 규범 문장이 없으면 빈 "
    "배열이다 — 억지로 만들지 마라. 단서('다만, …')는 별도 프레임으로 뽑고 "
    "proviso=true 를 단다.\n"
    "⑥ 없는 칸은 빈 문자열. target 이 없는 문장(단순 의무)은 target 을 비운다."
)
SCHEMA = {
    "type": "object",
    "properties": {"frames": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "node": {"type": "integer"},
            "actor": {"type": "string"}, "act": {"type": "string"},
            "target": {"type": "string"}, "object": {"type": "string"},
            "mode": {"type": "string",
                     "enum": ["의무", "금지", "허용", "절차", "위임", "간주", "정의", "기타"]},
            "function": {"type": "string",
                         "enum": ["근거·권한", "제한", "절차", "위임", "정의", "효과", "기타"]},
            "proviso": {"type": "boolean"}},
        "required": ["node", "actor", "act", "target", "object", "mode", "function",
                     "proviso"],
        "additionalProperties": False}}},
    "required": ["frames"], "additionalProperties": False,
}


def frames_dir() -> Path:
    return Path(os.environ.get("RAG_FRAMES_DIR", store_path().parent / "frames"))


# ---------------------------------------------------------------- 입력 만들기
def _units(v: DocView, jo: dict) -> list[dict]:
    """조 하나의 프레임 단위 — 항(circled)이 있으면 항, 없으면 조 자신.
    각 단위의 본문은 자기 범위 전체(호·목 포함)다 — 프레임은 항 수준이면 족하다."""
    kids = [n for n in v.nodes if n.get("parent") == jo["id"]
            and n.get("family") == "circled"]
    if not kids:
        return [{"id": jo["id"], "label": jo.get("surface", ""),
                 "text": v.section_text(jo, cap=JO_CHARS)}]
    out = []
    for k in kids:
        out.append({"id": k["id"], "label": k.get("surface", ""),
                    "text": v.section_text(k, cap=JO_CHARS // max(len(kids), 1) + 800)})
    return out


def _user(v: DocView, jo: dict, units: list[dict]) -> str:
    head = f"《{v.name}》 {jo.get('surface', '')} {jo.get('title', '')}".strip()
    body = "\n\n".join(f"[id={u['id']}] {u['text']}" for u in units)
    return f"[조]\n{head}\n\n[마디]\n{body}"


# ---------------------------------------------------------------- 검증
def _pack(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _grounded(frame: dict, texts: dict[int, str]) -> Optional[dict]:
    """마디 좌표가 실재하고 actor·act 가 둘 다 비지 않은 프레임만 받는다.

    부분 문자열 검사는 **뺐다** (2026-08-18 사용자 결정 — 부작용이 더 컸다):
    법령은 "제공(공유를 포함한다. 이하 같다)할 수 있다"처럼 괄호 삽입이 흔해
    "제공할 수 있다"가 연속 문자열로 없고, 조사·어미가 살짝 달라도 떨어졌다.
    개보법 제17조 ①의 act 가 비고 시행령류에서 프레임 2,575개가 통째로 버려진
    실측. 지어낸 낱말의 위험은 프롬프트 규칙 ①("본문에 실제로 있는 낱말만")과
    하이쿠의 추출 성향에 맡기고, 좌표(node)만 코드가 지킨다."""
    if not texts.get(frame.get("node"), ""):
        return None
    out = dict(frame)
    for k in ("actor", "act", "target", "object"):
        out[k] = (frame.get(k) or "").strip()
    if not out["actor"] and not out["act"]:
        return None
    return out


# ---------------------------------------------------------------- 뽑기
def extract_jo(llm, v: DocView, jo: dict) -> tuple[list[dict], dict]:
    """조 하나 → (프레임 목록, 관측). 실패는 빈 목록 + error."""
    units = _units(v, jo)
    texts = {u["id"]: u["text"] for u in units}
    out = llm.structured("rag.frames", SYSTEM, _user(v, jo, units), SCHEMA,
                         max_tokens=MAX_TOKENS, effort=None, model=MODEL)
    if out is None and llm.log and "잘림" in str(llm.log[-1].error or ""):
        # 출력 잘림만 재시도한다 — 마디가 아주 많은 조(실측 2026-08-19: 지배구조법
        # 제43조 과태료 각 호, 금투업규정 제4-20조)는 4천 토큰이 모자란다. 예산
        # 3배로 한 번만; 다른 오류(파싱·네트워크)는 fail-open 그대로 둔다.
        out = llm.structured("rag.frames", SYSTEM, _user(v, jo, units), SCHEMA,
                             max_tokens=MAX_TOKENS * 3, effort=None, model=MODEL)
    if out is None:
        err = llm.log[-1].error if llm.log else "?"
        return [], {"jo": jo["id"], "error": str(err)[:160]}
    frames, dropped = [], 0
    for f in out.get("frames", []):
        if f.get("node") not in texts:
            continue
        g = _grounded(f, texts)
        if g is None:
            dropped += 1
            continue
        frames.append({"jo": jo["id"], "node": g["node"], "actor": g["actor"],
                       "act": g["act"], "target": g["target"], "object": g["object"],
                       "mode": g["mode"], "function": g["function"],
                       "proviso": bool(g.get("proviso"))})
    return frames, {"jo": jo["id"], "n": len(frames), "dropped": dropped}


def _mainbody_jos(v: DocView) -> list[dict]:
    return [n for n in v.nodes
            if _JO.fullmatch((n.get("surface") or "").strip())
            and "부칙" not in v.path(n["id"])]


def extract_doc(v: DocView, llm_factory, out_dir: Optional[Path] = None,
                workers: int = WORKERS, only_missing: bool = True,
                article_ids: Optional[set[object]] = None) -> dict:
    """문서 하나 전량 → data/frames/<doc_id>.jsonl (한 줄 = 프레임 하나).
    only_missing 이면 이미 뽑힌 조는 건너뛴다(재실행이 실패분만 다시)."""
    out_dir = out_dir or frames_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{v.doc_id}.jsonl"
    done: set = set()
    if only_missing and path.is_file():
        for line in path.read_text("utf-8").splitlines():
            try:
                done.add(json.loads(line)["jo"])
            except Exception:
                pass
    jos = [j for j in _mainbody_jos(v)
           if j["id"] not in done
           and (article_ids is None or j["id"] in article_ids)]
    t0 = time.perf_counter()
    stats = {"doc": v.name, "jos": len(jos), "frames": 0, "errors": 0, "dropped": 0}
    if not jos:
        return stats

    def work(jo):
        llm = llm_factory()
        return extract_jo(llm, v, jo)

    with path.open("a", encoding="utf-8") as f, \
            ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, jo): jo for jo in jos}
        for fut in as_completed(futs):
            frames, meta = fut.result()
            if meta.get("error"):
                stats["errors"] += 1
                log.warning("프레임 실패 — %s %s: %s", v.name, futs[fut].get("surface"),
                            meta["error"])
                continue
            stats["dropped"] += meta.get("dropped", 0)   # 이제 좌표 없음·빈 프레임만
            for fr in frames:
                f.write(json.dumps(fr, ensure_ascii=False) + "\n")
            f.flush()                       # 진행이 밖에서 보이게 — 긴 문서는 분 단위다
            stats["frames"] += len(frames)
            # 뽑힌 조는 프레임이 0개라도 표시를 남긴다 — 재실행이 다시 안 묻게
            if not frames:
                f.write(json.dumps({"jo": futs[fut]["id"], "node": None, "actor": "",
                                    "act": "", "target": "", "object": "",
                                    "mode": "기타", "function": "기타",
                                    "proviso": False, "empty": True},
                                   ensure_ascii=False) + "\n")
    stats["sec"] = round(time.perf_counter() - t0, 1)
    return stats


# ---------------------------------------------------------------- 읽기
_cache: dict = {}


def load(doc_id: str) -> list[dict]:
    """문서의 프레임 전부 (빈 표시 행 제외). mtime 캐시."""
    p = frames_dir() / f"{doc_id}.jsonl"
    if not p.is_file():
        return []
    mt = p.stat().st_mtime_ns
    c = _cache.get(doc_id)
    if c and c[0] == mt:
        return c[1]
    rows = []
    for line in p.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not r.get("empty"):
            rows.append(r)
    _cache[doc_id] = (mt, rows)
    return rows


def vocab(index: Index) -> dict[str, dict]:
    """코퍼스 전체의 행위 어휘 — act 표면형 → {n, docs}. 질의 시점의 '닫힌 선택'
    메뉴가 이것이다. 정규화(별칭 병합)는 아직 없다 — 표면형 그대로."""
    out: dict[str, dict] = {}
    for doc_id, v in index.docs.items():
        for r in load(doc_id):
            a = (r.get("act") or "").strip()
            if not a:
                continue
            e = out.setdefault(a, {"n": 0, "docs": set()})
            e["n"] += 1
            e["docs"].add(v.name)
    return out
