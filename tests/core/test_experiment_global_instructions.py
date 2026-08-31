from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_codex_and_claude_point_to_canonical_experiment_prompt() -> None:
    agents = (ROOT / "AGENTS.md").read_text("utf-8")
    claude = (ROOT / "CLAUDE.md").read_text("utf-8")
    canonical = "docs/adr/EXPERIMENT_AGENT_PROMPT.md"

    assert canonical in agents
    assert canonical in claude


def test_canonical_prompt_enforces_complete_experiment_lifecycle() -> None:
    prompt = (ROOT / "docs" / "adr" / "EXPERIMENT_AGENT_PROMPT.md").read_text("utf-8")
    required = [
        "첫 제품·중간·judge 호출보다 ADR 생성이",
        "작업 선점",
        "created_at",
        "experiment_id/arm_id",
        "claude-haiku-4-5-20251001",
        "질문-NNN-case-id.md",
        "corpus 전체 수",
        "validate --path docs/adr/ADR-NNNN-slug --final",
        "graph --adr-root docs/adr",
        "메인 배선은 `unchanged`",
    ]
    for requirement in required:
        assert requirement in prompt
