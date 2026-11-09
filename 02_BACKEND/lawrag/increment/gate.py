"""시행일 배정, 멈춤 조건, 변경 게이트.

시행일
- 문서 기본 시행일: 공식 메타데이터(시행일자) → 없으면 마지막 부칙.
- 조문별: 법령 XML 조문시행일자 → 마지막 부칙 예외 → 문서 기본값 순.
- 옛 조문 판본의 종료일은 새 시행일 - 1일. 날짜는 KST YYYYMMDD 문자열이다.

멈춤 (자동 반영 금지)
- BLOCKED: 기존 최신 판본보다 이른 시행일 / 같은 시행일 재업로드(정정 절차 대상)
- BLOCKED_PENDING: 아직 시행 전인 조문 판본을 다시 개정

게이트: 자동 반영은 전부 SAME일 때뿐이다. 변경률은 MOVE·REF_ONLY·부칙을 빼고 센다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .addenda import Schedule
from .diff import ADD, AMEND, DELETE, MOVE_AMEND, SAME, Change, DiffResult
from .lawgo_parse import KIND_ADDENDUM, KIND_ANNEX, DocumentSnapshot

KST = timezone(timedelta(hours=9))
CONTENT_CHANGES = (AMEND, MOVE_AMEND, ADD, DELETE)


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def day_before(ymd: str) -> str:
    value = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])) - timedelta(days=1)
    return value.strftime("%Y%m%d")


def assign_effective(diff: DiffResult, snapshot: DocumentSnapshot, schedule: Schedule) -> str:
    """각 변경에 시행일을 붙이고 문서 기본 시행일을 돌려준다."""
    default = snapshot.effective or schedule.default
    for change in diff.changes:
        if change.change_type == DELETE or change.new is None:
            change.effective_from = default
            continue
        new = change.new
        # 법령 XML 조문시행일자는 보유 94개 판본 전부 문서 시행일자와 같은 값이었다 (조문별 정보 아님).
        # 조문별 시행일은 마지막 부칙의 예외가 정본이다.
        candidates = [schedule.per_article.get(new.key, "") if change.change_type != SAME else "",
                      default, new.official_effective]
        change.effective_from = next((c for c in candidates if c), "")
    return default


@dataclass
class Warning_:
    code: str
    strong: bool
    message: str


@dataclass
class GateResult:
    counts: dict[str, int]
    change_rate: float
    old_content: int
    new_content: int
    warnings: list[Warning_] = field(default_factory=list)
    stop: str = ""            # "" | BLOCKED | BLOCKED_PENDING
    stop_reason: str = ""

    @property
    def no_change(self) -> bool:
        return all(v == 0 for k, v in self.counts.items() if k != SAME)

    @property
    def strong(self) -> list[Warning_]:
        return [w for w in self.warnings if w.strong]

    def as_dict(self) -> dict:
        return {"counts": self.counts, "change_rate": round(self.change_rate, 4),
                "old_content": self.old_content, "new_content": self.new_content,
                "warnings": [w.__dict__ for w in self.warnings],
                "stop": self.stop, "stop_reason": self.stop_reason}


def evaluate(diff: DiffResult, snapshot: DocumentSnapshot, schedule: Schedule, *,
             base_effective: str, base_count: int, today: str | None = None) -> GateResult:
    today = today or today_kst()
    body = [c for c in diff.changes if c.kind != KIND_ADDENDUM]
    old_content = sum(1 for c in body if c.old is not None)
    new_content = sum(1 for c in body if c.new is not None)
    changed = sum(1 for c in body if c.change_type in CONTENT_CHANGES)
    rate = changed / old_content if old_content else (1.0 if changed else 0.0)
    gate = GateResult(diff.counts(), rate, old_content, new_content)
    add = gate.warnings.append

    first_load = base_count == 0
    if not first_load:
        if rate > 0.5:
            add(Warning_("CHANGE_RATE_OVER_50", True, f"변경률 {rate:.0%} (이동·인용 번호·부칙 제외)"))
        if new_content < 0.8 * old_content:
            add(Warning_("ARTICLE_COUNT_DROP", True, f"조문 수 {old_content}→{new_content}"))
        deletes = sum(1 for c in body if c.change_type == DELETE)
        if deletes > max(5, 0.2 * old_content):
            add(Warning_("MANY_DELETES", True, f"삭제 {deletes}건"))
        lost = [c.old.key for c in body if c.change_type == DELETE and c.kind == KIND_ANNEX]
        if lost:
            add(Warning_("ANNEX_REMOVED", True, f"별표·서식 사라짐: {', '.join(lost[:10])}"))
    if not snapshot.effective and not schedule.default:
        add(Warning_("EFFECTIVE_DATE_UNREAD", True, "문서 시행일을 읽지 못함"))
    if schedule.unparsed:
        add(Warning_("EFFECTIVE_DATE_UNREAD", True,
                     "부칙 시행일 예외를 읽지 못함: " + " / ".join(schedule.unparsed[:3])))
    if schedule.foreign:
        add(Warning_("FOREIGN_ADDENDUM", False,
                     f"타법개정 부칙({schedule.foreign}) — 그 부칙의 조문 번호는 다른 법 조문이라 "
                     f"조문별 예외로 쓰지 않고 문서 시행일자 {snapshot.effective or '없음'}를 적용"))
    if snapshot.effective and schedule.default and snapshot.effective != schedule.default \
            and snapshot.source_kind == "ADMRUL":
        add(Warning_("EFFECTIVE_DATE_MISMATCH", False,
                     f"메타 시행일자 {snapshot.effective} / 부칙 {schedule.default}"))
    low = [c.new.key for c in diff.changes
           if c.change_type == AMEND and c.similarity < 0.5 and c.new is not None]
    if low:
        add(Warning_("LOW_SIMILARITY_AMEND", False,
                     "같은 번호 유사도 0.5 미만 — 번호 재사용/확장 여부 확인: " + ", ".join(low[:10])))
    annex_unverified = [a.key for a in snapshot.articles
                        if a.kind == KIND_ANNEX and not a.attachment_sha256]
    if annex_unverified and snapshot.source_kind == "LAW":
        add(Warning_("ANNEX_ATTACHMENT_UNVERIFIED", False,
                     f"첨부 sha 없이 본문 머리만 비교한 별표 {len(annex_unverified)}건"))
    official = [c.official_note for c in diff.changes if c.official_note]
    if official and not first_load:
        add(Warning_("OFFICIAL_TAG_DISAGREE", False,
                     f"법제처 조문변경여부와 다른 판정 {len(official)}건 (판본을 건너뛴 비교면 정상)"))

    if gate.no_change or first_load:
        return gate
    effective = snapshot.effective or schedule.default
    if base_effective and effective and effective < base_effective:
        gate.stop, gate.stop_reason = "BLOCKED", f"기존 최신 판본({base_effective})보다 이른 시행일 {effective}"
    elif base_effective and effective == base_effective:
        gate.stop, gate.stop_reason = "BLOCKED", f"같은 시행일({effective})로 내용이 다른 재업로드 — 정정 절차 대상"
    else:
        pending = [c.old.key for c in diff.changes
                   if c.change_type != SAME and c.old is not None and c.old.effective_from > today]
        if pending:
            gate.stop = "BLOCKED_PENDING"
            gate.stop_reason = "시행 전 조문을 다시 개정: " + ", ".join(pending[:10])
        bad = [c.old.key for c in diff.changes
               if c.change_type != SAME and c.old is not None and c.effective_from
               and day_before(c.effective_from) < c.old.effective_from]
        if bad and not gate.stop:
            gate.stop = "BLOCKED"
            gate.stop_reason = "종료일이 시작일보다 앞서는 조문: " + ", ".join(bad[:10])
    return gate


def closing_date(change: Change) -> str:
    return day_before(change.effective_from)
