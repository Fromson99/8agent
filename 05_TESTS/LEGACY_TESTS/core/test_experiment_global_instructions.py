from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)


def test_codex_and_claude_point_to_canonical_experiment_prompt() -> None:
    agents = (ROOT / "AGENTS.md").read_text("utf-8")
    claude = (ROOT / "CLAUDE.md").read_text("utf-8")
    canonical = "04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md"

    assert canonical in agents
    assert canonical in claude


def test_canonical_prompt_enforces_complete_experiment_lifecycle() -> None:
    prompt = (ROOT / "04_EXPERIMENTS" / "LEGACY_ADR" / "EXPERIMENT_AGENT_PROMPT.md").read_text("utf-8")
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



def test_global_rules_enforce_research_candidate_isolation() -> None:
    prompt = (ROOT / "04_EXPERIMENTS" / "LEGACY_ADR" / "EXPERIMENT_AGENT_PROMPT.md").read_text("utf-8")
    standard = (ROOT / "04_EXPERIMENTS" / "LEGACY_ADR" / "STANDARD.md").read_text("utf-8")
    template = (
        ROOT / "04_EXPERIMENTS" / "LEGACY_ADR" / "templates" / "experiment-manifest.json"
    ).read_text("utf-8")

    for text in (prompt, standard):
        assert "ADR-0138" in text
        assert "scripts/adr_candidate.py snapshot" in text
        assert "freeze" in text
        assert "registry" in text
    assert "candidate_snapshot" in standard
    operational = (ROOT / "AGENTS.md").read_text("utf-8")
    assert "06_TOOLS/run_tool.py adr_structure.py" in operational
    assert "--adr-root 04_EXPERIMENTS/ADR" in operational
    for text in (standard, template):
        assert "adr-code-isolation-v1" in text
        assert "production_paths_modified_before_decision" in text
        assert "runtime_import_allowed" in text
        assert "production_registry_registered" in text
        assert "main_wiring_unchanged" in text
