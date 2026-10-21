from pathlib import Path
import sys,json,tempfile,shutil,os
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0796/selected';cm=json.loads((C/'candidate.json').read_text());S=C/'revisions'/cm['revisions'][-1]['revision_id']/'snapshot'
sys.dont_write_bytecode=True;sys.path[:0]=[str(S/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R))
import pytest,semantic_runtime.search_selection,lawrag.pipeline.search_selection
assert str(S) in semantic_runtime.search_selection.__file__ and str(S) in lawrag.pipeline.search_selection.__file__
with tempfile.TemporaryDirectory(prefix='latest-tests-') as tmp:
 t=Path(tmp);shutil.copyfile(S/'05_TESTS/test_latest_document_policy.py',t/'test_latest_document_policy.py');shutil.copyfile(R/'05_TESTS/conftest.py',t/'conftest.py')
 code=pytest.main(['-q',str(t/'test_latest_document_policy.py'),str(R/'05_TESTS/CONTRACTS/test_search_selection.py'),'-k','not test_existing_database_search_and_actual_api'])
 raise SystemExit(code)
