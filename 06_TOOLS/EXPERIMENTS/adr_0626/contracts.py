"""Saved guarded candidate test entrypoint supports spawned source builds."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0626/local-completion/snapshot'
if '--frozen' in sys.argv:
    revision=json.loads((CODE.parent/'candidate.json').read_text())['revisions'][-1]['revision_id']
    CODE=CODE.parent/'revisions'/revision/'snapshot'
sys.dont_write_bytecode=True
sys.path[:0]=[str(CODE/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
def main():
    import test_unit_fulltext_adaptive_read,test_batch_reference_navigation,test_compact_reference_menu_repair
    import test_legal_agent_v5,test_unified_legal_agent,test_chosen_unit_local_completion
    import importlib.util
    spec=importlib.util.spec_from_file_location('research_packager',ROOT/'06_TOOLS/EXPERIMENTS/adr_0626/package.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    target=ROOT/'04_EXPERIMENTS/ADR/ADR-0626-chosen-unit-local-completion/artifacts/research-code-rev-002'
    if not target.exists():package.materialize(CODE,target)
    for module in (test_legal_agent_v5,test_unified_legal_agent):module.ROOT=target
    import pytest
    return pytest.main(['-q',
        '--deselect=05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py::test_selected_scopes_drive_durable_assessment_publication_and_reuse[True]',
        '05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py',
        '05_TESTS/CONTRACTS/test_unit_read_canonical_boundaries.py',
        '05_TESTS/CONTRACTS/test_batch_reference_navigation.py',
        '05_TESTS/CONTRACTS/test_compact_reference_menu_repair.py',
        '05_TESTS/CONTRACTS/test_unified_legal_agent.py','05_TESTS/CONTRACTS/test_chosen_unit_local_completion.py'])
if __name__=='__main__':raise SystemExit(main())
