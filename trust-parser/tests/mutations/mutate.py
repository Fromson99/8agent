"""T19. 변이 테스트 하네스 — 골든 쌍을 의도적으로 훼손한다 (SPEC §C12.4).

"이 제약이 잡아야 할 오류를 실제로 잡는가"의 자동 증명.
올바른 요약서를 훼손하고, **정확히 그 필드가** VALUE_MISMATCH/MISSING 로 발화하는지 본다.

죽은 제약 두 종류를 걸러낸다:
    (a) 한 번도 발화하지 않는 제약 — 변이를 넣어도 조용하면 가치가 없다
    (b) 잘못 발화하는 제약 — 변이와 무관한 필드가 함께 터지면 노이즈다
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Mutation:
    id: str
    field: str                      # 이 변이가 발화시켜야 할 필드
    expect: str                     # 기대 verdict
    describe: str
    apply: Callable[[str], str]     # 요약서 원문 → 훼손된 원문


def _replace(old: str, new: str) -> Callable[[str], str]:
    def fn(text: str) -> str:
        if old not in text:
            raise ValueError(f"변이 대상을 찾지 못했습니다: {old!r}")
        return text.replace(old, new, 1)
    return fn


def _delete_line(needle: str) -> Callable[[str], str]:
    def fn(text: str) -> str:
        lines = [l for l in text.split("\n") if needle not in l]
        if len(lines) == len(text.split("\n")):
            raise ValueError(f"삭제 대상을 찾지 못했습니다: {needle!r}")
        return "\n".join(lines)
    return fn


# 골든 쌍 acct_001 의 요약서(summary.md)에 대한 변이들.
# 각 변이는 제약 하나를 겨냥한다 — 실제 사고 유형에서 뽑았다(§C12.1 "사례 1건 = 제약 1개").
MUTATIONS: list[Mutation] = [
    Mutation("amount_digit_drop", "신탁금액", "VALUE_MISMATCH",
             "금액 자릿수 누락 (1억 → 1천만)",
             _replace("100,000,000원", "10,000,000원")),
    Mutation("period_year_typo", "신탁기간", "VALUE_MISMATCH",
             "기간 종료연도 오기 (27 → 26)",
             _replace("24.6.3 ~ 27.6.2", "24.6.3 ~ 26.6.2")),
    Mutation("perf_fee_rate", "수익보수", "VALUE_MISMATCH",
             "성과보수 요율 변경 (15% → 12%)",
             _replace("15.00%", "12.00%")),
    Mutation("account_typo", "계좌번호", "VALUE_MISMATCH",
             "계좌번호 한 자리 오기",
             _replace("12345678901", "12345678902")),
    Mutation("payout_ratio", "원금지급비율", "VALUE_MISMATCH",
             "원금지급비율 변경 (0% → 50%)",
             _replace("| 원금지급비율 | 0% |", "| 원금지급비율 | 50% |")),
    Mutation("drop_amount_row", "신탁금액", "MISSING_IN_SUMMARY",
             "신탁금액 행 삭제 — 누락 검출",
             _delete_line("투자금액")),
    Mutation("drop_method_row", "신탁자금 운용방법", "MISSING_IN_SUMMARY",
             "운용방법 행 삭제 — 누락 검출",
             _delete_line("**운용방법**")),
]


def apply_to(summary_path: str | Path, mutation: Mutation, out_dir: str | Path) -> Path:
    src = Path(summary_path)
    text = src.read_text(encoding="utf-8")
    out = Path(out_dir) / f"{src.stem}.{mutation.id}{src.suffix}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(mutation.apply(text), encoding="utf-8")
    return out


def find(mutation_id: str) -> Optional[Mutation]:
    return next((m for m in MUTATIONS if m.id == mutation_id), None)
