from scripts.rag_export_adr0038_case_markdown import _fence, _judge_user


def test_fence_grows_when_payload_contains_backticks():
    rendered = _fence("값 ``` 안쪽")
    assert rendered.startswith("````text\n")
    assert rendered.endswith("\n````")


def test_judge_user_respects_saved_label_mapping():
    user = _judge_user("정답", "기준", "후보",
                       {"baseline": "B", "candidate": "A"})
    assert "[답변 A]\n후보" in user
    assert "[답변 B]\n기준" in user

