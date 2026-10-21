"""Exercise frozen collector -> structure -> release -> index -> actual API, no LLM."""
from pathlib import Path
import json,sys,tempfile,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search';S=R/json.loads((A/'artifacts/design/freeze.json').read_text())['code_root']
sys.path[:0]=[str(S/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')];sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R))
import test_legal_agent_v5 as v5
v5.ROOT=S
import pytest
source=(R/'05_TESTS/CONTRACTS/test_latest_internal_versions.py').read_text();preamble=source[:source.index('def test_latest_precedes')]
body=source[source.index('@pytest.mark.parametrize(\'index_mode\''):]
body=body.replace("== '20220331'","== '2022-03-31'").replace("ids = [v[0]", "store.selection.require_latest()\n        assert store.selection.native_latest_verified\n        ids = [v[0]")
body=body.replace("assert payload['document_metadata']['filename_version']['date']", "assert payload['document_metadata']['is_latest'] is True\n        assert payload['document_metadata']['filename_version']['is_latest'] is True\n        assert payload['document_metadata']['filename_version']['date']")
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test_native.py').write_text(preamble+body);(p/'conftest.py').write_bytes((R/'05_TESTS/conftest.py').read_bytes());raise SystemExit(pytest.main(['-q',str(p/'test_native.py')]))
