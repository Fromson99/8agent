"""STT 전사 파싱 로직 — 발화턴 계열 (registry `parsers.transcript`, SPEC §00.5).

전사에는 페이지도 bbox 도 없다. 대신 **발화 하나가 곧 좌표**다 — 판정의 근거 인용은
"몇 번째 발화의 몇 초"로 되돌아가야 하고(AGENT6 §1 원칙 3), 그 좌표가 doc.json 까지
살아남아야 한다. 이 파일이 하는 일은 그 좌표를 코어의 그릇(Element/Element.meta)에
싣는 것뿐이다. 구조화도 채점도 코어가 한다.

## 발화 하나를 왜 요소 **두 개**로 내는가 (이 파일에서 가장 이상해 보이는 결정)

코어 구조화기는 마커에 적중한 요소의 꼬리를 section 내용으로 넣을 때 Element.meta 를
싣지 않는다(core/structurize.py `build_sections` 의 tail 처리 — meta 를 통과시키는
`_content_of` 는 **마커에 걸리지 않은** 요소에만 쓰인다). 마커와 발화문을 한 요소에
합치면 화자·타임스탬프가 doc.json 에서 통째로 사라진다. 전사에서 그것이 사라지면
근거 인용이 불가능해지고, 인용 없는 판정은 무효다(§1 원칙 3). 그래서 발화당

    [001 PB]        ← 마커 줄. 형식의 `발화` 마커가 이 줄만 본다 (max_tail 0)
    안녕하세요 …      ← 본문 줄. meta 를 달고 그 section 의 content[0] 이 된다

두 요소를 낸다. 코어를 고치지 않고 좌표를 살리는 길은 이것뿐이다.

## 문자 오프셋의 기준

meta.char_start/char_end 는 **정규 전사 텍스트** 기준이다 — 정규화(공백 접기)된
발화문을 `\\n` 으로 이어 붙인 문자열이고, `canonical_text()` 가 그것을 돌려준다.
평문 입력(화자·타임스탬프 없음)에서는 이 오프셋이 유일한 인용 좌표가 된다.

## 결정론

같은 파일을 두 번 파싱하면 완전히 같은 결과다. 정렬·추론·시각이 끼어들지 않는다.
타임스탬프가 뒤죽박죽이어도 **다시 정렬하지 않는다** — 조용히 고치는 대신 경고한다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.glossary import normalize as normalize_surface
from core.parse_adapter import Element, ParseResult, norm_ws

# 발화 요소의 두 얼굴 — 형식 파일의 `발화` 마커는 MARKER 줄만 본다.
TYPE_MARKER = "utterance_marker"
TYPE_UTTERANCE = "utterance"

# 화자 라벨 정규화 표. **데이터다** — 표에 없는 라벨은 원문을 그대로 남기고
# stats["speakers"] 에 드러내 준다(조용히 뭉개면 누가 말했는지가 사라진다).
# 새 라벨이 현장에서 보이면 여기 한 줄을 늘린다.
SPEAKER_ALIASES: dict[str, tuple[str, ...]] = {
    "PB": ("PB", "판매자", "직원", "상담원"),
    "고객": ("고객", "투자자"),
}
UNKNOWN_SPEAKER = "미상"

# 발화 레코드의 필드 이름 흔들림 — STT 엔진마다 다르다. 여기 없는 이름은 없는 것으로
# 친다(추측해서 아무 필드나 발화문으로 삼지 않는다).
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "speaker": ("speaker", "spk", "speaker_label", "speaker_id", "role", "화자"),
    "text": ("text", "utterance", "content", "sentence", "발화", "내용"),
    "start": ("start", "start_time", "start_sec", "begin", "시작"),
    "end": ("end", "end_time", "end_sec", "finish", "종료"),
}

# 감싼 형태를 푸는 열쇠 — 이 이름들이 먼저다.
WRAPPER_KEYS = ("utterances", "segments", "turns", "transcript", "results", "발화")

# 평문 입력에 남기는 경고. 문구가 리포트에 그대로 실려 confidence 감점 근거가 된다.
PLAINTEXT_WARNING = (
    "화자 라벨·타임스탬프 없음 — 근거 인용이 문자 오프셋으로 대체되고 "
    "판정 confidence 가 한 단계 감점됩니다")


class TranscriptError(ValueError):
    """전사를 읽을 수 없다. 빈 결과를 돌려주는 대신 여기서 멈춘다(조용한 실패 금지)."""


@dataclass
class _Turn:
    """발화 하나 — 파일 형태와 무관한 중간 표현."""
    speaker: str
    text: str
    start: Optional[float]
    end: Optional[float]


# ===========================================================================
# 정규화
# ===========================================================================

# 공백 접기 — STT 출력에는 줄바꿈·연속 공백이 섞여 온다. 파싱 층 표준을 그대로 쓴다.
_collapse = norm_ws


_SPEAKER_INDEX = {normalize_surface(surface): canon
                  for canon, surfaces in SPEAKER_ALIASES.items()
                  for surface in surfaces}


def normalize_speaker(raw: Any) -> str:
    """화자 라벨 → 정규 라벨. 표에 없으면 원문을 그대로 둔다.

    대괄호는 지운다 — 마커 줄 `[001 화자]` 의 경계를 깨기 때문이다.
    """
    s = _collapse(raw).replace("[", "").replace("]", "").strip()
    if not s:
        return UNKNOWN_SPEAKER
    return _SPEAKER_INDEX.get(normalize_surface(s), s)


def _to_seconds(raw: Any, bad: list[str]) -> Optional[float]:
    """초 단위 실수로. 못 읽으면 None 으로 두고 `bad` 에 원문을 남겨 경고한다."""
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        bad.append(str(raw))
        return None


# ===========================================================================
# 입력 A(정본) — JSON
# ===========================================================================

def _unwrap(data: dict, path: Path) -> list[Any]:
    """감싼 형태를 푼다. 후보가 여럿이면 고르지 않고 거부한다."""
    for key in WRAPPER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return value
    candidates = sorted(k for k, v in data.items()
                        if isinstance(v, list) and v and isinstance(v[0], dict))
    if len(candidates) == 1:
        return data[candidates[0]]
    raise TranscriptError(
        f"발화 목록을 찾지 못했습니다: {path} — 최상위가 객체라면 "
        f"{list(WRAPPER_KEYS)} 중 한 이름에 발화 배열을 두세요 "
        f"(발견된 배열 후보: {candidates or '없음'}).")


def _field(record: dict, lowered: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _from_json(path: Path, text: str, warnings: list[str]) -> list[_Turn]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranscriptError(
            f"JSON 을 읽을 수 없습니다: {path} ({exc.lineno}행 {exc.colno}열: {exc.msg}) — "
            f"전사 파일이 손상됐거나 JSON 이 아닙니다.") from exc

    if isinstance(data, dict):
        records = _unwrap(data, path)
    elif isinstance(data, list):
        records = data
    else:
        raise TranscriptError(
            f"전사 JSON 의 최상위는 발화 배열이거나 그것을 감싼 객체여야 합니다: {path} "
            f"(받은 형태: {type(data).__name__})")

    if not records:
        raise TranscriptError(f"발화가 하나도 없습니다: {path}")

    turns: list[_Turn] = []
    empty: list[int] = []          # 본문이 빈 레코드 — 건너뛰되 시끄럽게 센다
    no_speaker = 0
    no_time = 0
    bad_time: list[str] = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            raise TranscriptError(
                f"{i + 1}번째 발화가 객체가 아닙니다: {path} "
                f"(받은 형태: {type(record).__name__}) — "
                f'{{"speaker": …, "start": …, "end": …, "text": …}} 형태여야 합니다.')
        lowered = {str(k).lower(): v for k, v in record.items()}
        body = _collapse(_field(record, lowered, FIELD_ALIASES["text"]))
        if not body:
            empty.append(i + 1)
            continue
        speaker_raw = _field(record, lowered, FIELD_ALIASES["speaker"])
        if speaker_raw is None:
            no_speaker += 1
        start = _to_seconds(_field(record, lowered, FIELD_ALIASES["start"]), bad_time)
        end = _to_seconds(_field(record, lowered, FIELD_ALIASES["end"]), bad_time)
        if start is None and end is None:
            no_time += 1
        turns.append(_Turn(speaker=normalize_speaker(speaker_raw), text=body,
                           start=start, end=end))

    if not turns:
        raise TranscriptError(
            f"본문이 있는 발화가 하나도 없습니다: {path} — "
            f"발화문 필드 이름이 {list(FIELD_ALIASES['text'])} 중 하나인지 확인하세요.")

    if empty:
        warnings.append(
            f"본문이 빈 발화 {len(empty)}개를 건너뜁니다 (원본 {empty[:10]}번째"
            f"{' 외' if len(empty) > 10 else ''}) — 발화 번호는 남은 발화 기준으로 다시 매겨집니다")
    if no_speaker == len(turns) and no_time == len(turns):
        warnings.append(PLAINTEXT_WARNING)
    else:
        if no_speaker:
            warnings.append(
                f"화자 라벨이 없는 발화 {no_speaker}개 — '{UNKNOWN_SPEAKER}' 으로 둡니다 "
                f"(누가 말했는지 모르는 발화는 판정 근거로 쓰지 마십시오)")
        if no_time:
            warnings.append(
                f"타임스탬프가 없는 발화 {no_time}개 — 그 발화의 근거 인용은 "
                f"문자 오프셋(meta.char_start/char_end)으로 대체됩니다")
    if bad_time:
        warnings.append(
            f"초로 읽을 수 없는 타임스탬프 {len(bad_time)}개를 버렸습니다 "
            f"(첫 값 '{bad_time[0]}') — start/end 는 초 단위 숫자여야 합니다")
    return turns


# ===========================================================================
# 입력 B(수용) — 평문
# ===========================================================================

def _from_plaintext(text: str, warnings: list[str]) -> list[_Turn]:
    """줄 하나가 발화 하나다.

    화자도 시각도 없으므로 문장으로 더 쪼개는 것은 **추측**이다. 줄 경계만 믿고,
    부족하다는 사실은 경고로 남긴다(§1 입력 규정).
    """
    turns = [_Turn(speaker=UNKNOWN_SPEAKER, text=_collapse(line), start=None, end=None)
             for line in text.splitlines() if line.strip()]
    if turns:
        warnings.append(PLAINTEXT_WARNING)
    return turns


# ===========================================================================
# 진입점
# ===========================================================================

def parse(path: str | Path) -> ParseResult:
    """전사 파일 하나 → ParseResult. 코어가 registry 를 통해 이 함수를 부른다."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"입력 전사를 찾을 수 없습니다: {p}")
    raw = p.read_bytes()
    if not raw.strip():
        raise TranscriptError(f"빈 파일입니다: {p} — 발화가 하나도 없습니다")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TranscriptError(
            f"UTF-8 로 읽을 수 없습니다: {p} ({exc.reason}) — 전사는 UTF-8 이어야 합니다") from exc

    warnings: list[str] = []
    suffix = p.suffix.lower()
    if suffix == ".json":
        turns, mode = _from_json(p, text, warnings), "json"
    elif suffix in (".txt", ".md"):
        turns, mode = _from_plaintext(text, warnings), "평문"
    else:
        raise TranscriptError(
            f"지원하지 않는 확장자입니다: {p.suffix} "
            f"(전사 정본은 .json, 평문은 .txt/.md 만 받습니다)")
    if not turns:
        raise TranscriptError(f"발화를 하나도 찾지 못했습니다: {p}")

    elements: list[Element] = []
    offset = 0
    starts: list[float] = []
    ends: list[float] = []
    speakers: dict[str, int] = {}
    out_of_order = 0
    previous: Optional[float] = None

    for i, turn in enumerate(turns):
        meta = {
            "turn": i + 1,
            "speaker": turn.speaker,
            "start": turn.start,
            "end": turn.end,
            # 정규 전사 텍스트(canonical_text) 기준 오프셋 — 타임스탬프가 없을 때의 좌표
            "char_start": offset,
            "char_end": offset + len(turn.text),
            "utterance": turn.text,
        }
        offset = meta["char_end"] + 1                     # 발화 사이의 "\n"
        elements.append(Element(index=len(elements), type=TYPE_MARKER,
                                text=f"[{i + 1:03d} {turn.speaker}]",
                                page=1, bbox=None, meta=dict(meta)))
        elements.append(Element(index=len(elements), type=TYPE_UTTERANCE,
                                text=turn.text, page=1, bbox=None, meta=dict(meta)))
        speakers[turn.speaker] = speakers.get(turn.speaker, 0) + 1
        if turn.start is not None:
            starts.append(turn.start)
            if previous is not None and turn.start < previous:
                out_of_order += 1
            previous = turn.start
        if turn.end is not None:
            ends.append(turn.end)

    if out_of_order:
        warnings.append(
            f"타임스탬프가 시간순이 아닌 발화 {out_of_order}개 — 순서를 고치지 않았습니다 "
            f"(전사 파일을 확인하세요)")
    # 표에 없는 라벨은 원문대로 남았다. 제3자(녹취담당 등)일 수도 있지만 PB 의 다른
    # 표기일 수도 있고, 후자라면 화자 기반 규칙이 조용히 빗나간다 — 이름을 불러 준다.
    unknown = sorted(set(speakers) - set(SPEAKER_ALIASES) - {UNKNOWN_SPEAKER})
    if unknown:
        warnings.append(
            f"정규화 표에 없는 화자 라벨: {', '.join(unknown)} — 원문 그대로 두었습니다 "
            f"(PB·고객의 다른 표기라면 transcript.py 의 SPEAKER_ALIASES 에 추가하세요)")

    duration = round(max(ends) - min(starts), 3) if starts and ends else None
    stats = {
        "utterances": len(turns),
        "speakers": {name: speakers[name] for name in sorted(speakers)},
        "duration": duration,
        "elements": len(elements),
        "mode": mode,
        "with_timestamp": len(starts),
        "chars": offset - 1 if turns else 0,
    }
    return ParseResult(
        path=str(p), doc_id=hashlib.sha256(raw).hexdigest()[:12],
        parser="transcript", born_digital=True,
        elements=elements, warnings=warnings, stats=stats)


def canonical_text(result: ParseResult) -> str:
    """meta.char_start/char_end 의 기준이 되는 정규 전사 텍스트.

    인용문이 전사에 **실제로 존재하는지** 문자 검증할 때(환각 인용 차단, AGENT6 §8)
    이 문자열을 기준으로 삼는다.
    """
    return "\n".join(e.meta["utterance"] for e in result.elements
                     if e.type == TYPE_UTTERANCE)
