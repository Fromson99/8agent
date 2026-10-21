from pathlib import Path
import sys,os
R=Path(__file__).resolve().parents[4];C=Path(sys.argv[1]).resolve();sys.path[:0]=[str(C/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')];sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(C),LAWRAG_TOOL_WORKSPACE_ROOT=str(C))
import pytest,semantic_runtime.search_selection
assert str(C) in semantic_runtime.search_selection.__file__
raise SystemExit(pytest.main(['-q',str(R/'05_TESTS/CONTRACTS/test_latest_document_policy.py'),str(R/'05_TESTS/CONTRACTS/test_search_selection.py'),'-k','not test_existing_database_search_and_actual_api']))
