from __future__ import annotations

from types import SimpleNamespace

from scripts import rag_frame_only_answer_ab as experiment


class View:
    doc_id = "doc-1"
    by_id = {
        1: {"id": 1, "parent": None},
        2: {"id": 2, "parent": 1},
        3: {"id": 3, "parent": 2},
        9: {"id": 9, "parent": None},
    }

    def path(self, node):
        return {1: "제1조", 2: "제1조 ▸ ①", 3: "제1조 ▸ ① ▸ 1.",
                9: "제9조"}.get(node, "")


def test_frames_for_section_stays_inside_selected_subtree(monkeypatch):
    rows = [
        {"jo": 1, "node": 2, "actor": "회사", "act": "보고한다"},
        {"jo": 9, "node": 9, "actor": "거래소", "act": "정한다"},
    ]
    monkeypatch.setattr(experiment.frames, "load", lambda _doc_id: rows)

    assert experiment.frames_for_section(View(), 1) == rows[:1]
    assert experiment.frames_for_section(View(), 2) == rows[:1]
    assert experiment.frames_for_section(View(), 9) == rows[1:]


def test_render_frames_contains_only_structured_fields_not_source_body():
    row = {"jo": 1, "node": 2, "actor": "회사", "act": "보고하여야 한다",
           "target": "이사회", "object": "운영실태", "mode": "의무",
           "function": "절차", "proviso": True}

    rendered = experiment.render_frames(View(), 1, [row])

    assert "actor(규율 주체): 회사" in rendered
    assert "object(행위 객체): 운영실태" in rendered
    assert "단서: true" in rendered
    assert "원문에만 있는 비밀 문장" not in rendered


def test_render_frames_marks_missing_coverage_without_inventing_text():
    rendered = experiment.render_frames(View(), 1, [])
    assert "구조화 프레임 없음" in rendered
    assert "조문 원문은 제공되지 않음" in rendered


def test_summary_reports_paired_delta_and_token_reduction():
    usage_a = {"calls": 1, "input_tokens": 100, "output_tokens": 10,
               "duration_ms": 5, "errors": 0}
    usage_b = {"calls": 1, "input_tokens": 40, "output_tokens": 8,
               "duration_ms": 4, "errors": 0}
    rows = [{
        "judge": {"original": {"correct": True},
                  "frame_only": {"correct": False}},
        "coverage": {"selected_sections": 2, "sections_with_frames": 1,
                     "frame_count": 3},
        "original": {"usage": usage_a, "wall_ms": 10, "prompt_chars": 200},
        "frame_only": {"usage": usage_b, "wall_ms": 8, "prompt_chars": 100},
    }]

    summary = experiment._summary(rows)

    assert summary["original_correct"] == 1
    assert summary["frame_only_correct"] == 0
    assert summary["delta"] == -1
    assert summary["coverage"]["section_frame_coverage"] == 0.5
    assert summary["input_token_reduction"] == 0.6
