"""LLM 호출 계층 — 문서 내용의 해석은 전부 여기를 거친다.

## 이전 설계와 달라진 점

예전에는 값 추출·정규화를 정규식이 하고 LLM 은 애매한 것만 봤다.
dataset 9종 전수조사에서 그 방식이 무너졌다 — 금액 파서 오탐 80%, 기준일 추출 성공률 44%.
이제 **문서에서 무언가를 읽어내는 일은 전부 LLM 이 하고, 코드는 구조화된 값만 다룬다.**

호출 지점은 5개이며 각각 입출력 JSON 이 고정되어 있다.
    tag_blocks        블록에 메인 태그 부여 (= 섹션 형성)
    extract_elements  섹션에서 세부 요소를 typed value 로 추출
    pair_sections     1단계 — 두 문서의 섹션이 같은 사안인지
    compare_values    2단계 — 코드가 판정 못 한 값쌍의 의미 동등성
    doc_meta          발행사·기준일·상품유형

## 결정론 확보

LLM 은 같은 입력에 다른 답을 낼 수 있다. 금융 감사에서는 문제가 된다.
그래서 모든 호출을 **입력 해시 기준으로 스냅샷에 기록**한다(cache.py).
같은 문서를 다시 돌리면 스냅샷을 재생하므로 결과가 고정되고, API 키 없이도 재현된다.
사람이 스냅샷을 고치면 그게 정답이 된다 — 감사 대응 경로다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from .. import env
from ..textkit import extract_json

PROMPT_DIR = Path(__file__).parent / "prompts"
DEFAULT_MODEL = "claude-sonnet-5"

CALLS = ("tag_blocks", "extract_elements", "pair_sections", "compare_values", "doc_meta")

# 호출별 출력 토큰 상한 — 태깅과 대응은 목록을 내므로 넉넉히 준다
# 실측: 7블록 태깅에 출력 6,486 토큰이 나왔다(근거 문장이 길어서).
# 배치 크기와 함께 넉넉히 잡되, 넘치면 TruncatedResponse 로 즉시 드러나게 한다.
_MAX_TOKENS = {
    "tag_blocks": 16384,
    "extract_elements": 8192,
    "pair_sections": 8192,
    "compare_values": 1024,
    "doc_meta": 1024,
}


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


class LLMUnavailable(RuntimeError):
    """LLM 백엔드도 스냅샷도 없을 때. 조용히 가짜 결과를 내지 않기 위해 명시적으로 던진다."""


class TruncatedResponse(RuntimeError):
    """응답이 max_tokens 에서 잘렸을 때. 깨진 JSON 을 파싱 오류로 위장시키지 않는다."""


class BaseClient:
    name = "base"

    def call(self, kind: str, payload: dict) -> dict:
        raise NotImplementedError

    # 편의 메서드 — 호출부 가독성을 위해
    def tag_blocks(self, p: dict) -> dict: return self.call("tag_blocks", p)
    def extract_elements(self, p: dict) -> dict: return self.call("extract_elements", p)
    def pair_sections(self, p: dict) -> dict: return self.call("pair_sections", p)
    def compare_values(self, p: dict) -> dict: return self.call("compare_values", p)
    def doc_meta(self, p: dict) -> dict: return self.call("doc_meta", p)


class AnthropicClient(BaseClient):
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        import anthropic

        env.ensure_loaded()
        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.name = f"anthropic:{self.model}"

    def call(self, kind: str, payload: dict) -> dict:
        if kind not in CALLS:
            raise ValueError(f"알 수 없는 호출 종류: {kind}")
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=_MAX_TOKENS.get(kind, 2048),
            system=load_prompt(kind),
            messages=[{"role": "user",
                       "content": json.dumps(payload, ensure_ascii=False, indent=2)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        # 잘린 응답은 JSON 이 깨져 원인을 알 수 없는 파싱 오류로 나타난다.
        # 실제로 겪은 일: tag_blocks 가 8192 토큰을 넘겨 잘렸고, 파서는 "JSON 없음"만 말했다.
        if getattr(msg, "stop_reason", None) == "max_tokens":
            raise TruncatedResponse(
                f"'{kind}' 응답이 max_tokens({_MAX_TOKENS.get(kind)})에서 잘렸습니다. "
                f"입력을 더 작은 배치로 나누거나 상한을 올리세요. "
                f"(출력 {getattr(msg.usage, 'output_tokens', '?')} 토큰)")
        return extract_json(text)


class SnapshotClient(BaseClient):
    """스냅샷 재생 전용. API 키 없이 테스트·데모·재현을 가능하게 한다.

    스냅샷에 없는 입력이 오면 조용히 넘어가지 않고 LLMUnavailable 을 던진다.
    없는 판정을 지어내면 리포트가 거짓말을 하게 되기 때문이다.
    """

    name = "snapshot"

    def __init__(self, store, strict: bool = True):
        self.store = store
        self.strict = strict

    def call(self, kind: str, payload: dict) -> dict:
        hit = self.store.get(kind, payload)
        if hit is not None:
            return hit
        if self.strict:
            raise LLMUnavailable(
                f"'{kind}' 호출에 대한 스냅샷이 없습니다. "
                f"ANTHROPIC_API_KEY 를 설정해 한 번 실행하면 스냅샷이 기록됩니다.")
        return {}


class RecordingClient(BaseClient):
    """실제 호출 결과를 스냅샷에 기록하면서 위임한다."""

    def __init__(self, inner: BaseClient, store):
        self.inner = inner
        self.store = store
        self.name = inner.name

    def call(self, kind: str, payload: dict) -> dict:
        hit = self.store.get(kind, payload)
        if hit is not None:
            return hit
        result = self.inner.call(kind, payload)
        self.store.put(kind, payload, result)
        return result


def get_client(prefer: str = "auto", model: str = DEFAULT_MODEL, store=None) -> BaseClient:
    """prefer: auto | anthropic | snapshot

    auto      키가 있으면 실제 호출(+스냅샷 기록), 없으면 스냅샷 재생
    anthropic 키가 없으면 예외
    snapshot  항상 스냅샷만 사용 (테스트)
    """
    if prefer == "snapshot":
        if store is None:
            raise ValueError("snapshot 백엔드에는 store 가 필요합니다")
        return SnapshotClient(store)

    has_key = env.has_api_key()          # .env 를 읽고 판단한다 (셸 환경변수가 우선)
    if prefer == "anthropic" and not has_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY 가 설정되어 있지 않습니다.")
    if has_key:
        inner = AnthropicClient(model=model)
        return RecordingClient(inner, store) if store is not None else inner
    if store is None:
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY 도 스냅샷도 없습니다. "
            "이 파이프라인은 문서 해석을 LLM 에 의존하므로 둘 중 하나가 필요합니다.")
    return SnapshotClient(store)
