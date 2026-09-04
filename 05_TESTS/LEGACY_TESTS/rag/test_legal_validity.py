from dataclasses import dataclass

from lawrag.core.rag.legal_validity import authority, parse_as_of, validate_document


@dataclass
class View:
    doc_id: str = "d1"
    name: str = "상법"
    kind: str = "law"
    enforce: str = "20240101"
    revised: str = "20240101"
    status: str = ""

    @property
    def is_current(self):
        return self.status != "구판"


def test_parse_as_of_requires_full_calendar_date():
    assert parse_as_of("2024년 2월 29일 기준").isoformat() == "2024-02-29"
    assert parse_as_of("2024-02-29 현재").isoformat() == "2024-02-29"
    assert parse_as_of("2024년 기준") is None


def test_current_text_after_requested_date_is_not_treated_as_historical_text():
    view = View(enforce="20200101", revised="20250101")

    finding = validate_document(view, parse_as_of("2024년 1월 1일 기준"))

    assert finding.temporal_status == "unverifiable_historical_text"


def test_not_yet_effective_is_blocked_and_authority_is_labeled():
    view = View(name="상법 시행령", enforce="20250101", revised="20250101")

    finding = validate_document(view, parse_as_of("2024-12-31 기준"))

    assert finding.temporal_status == "not_yet_effective"
    assert authority(view) == ("presidential_decree", 20)
