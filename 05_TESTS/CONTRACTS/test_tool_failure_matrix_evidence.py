"""Result accounting must not turn missing or skipped executions into passes."""
import ast
import json
from pathlib import Path
from tool_failure_matrix_evidence import from_junit,status_for,EXTRA,PREFIX,ROOT,DESIGN


def test_missing_skipped_and_failed_are_separate(tmp_path):
    path=tmp_path/'run.xml'
    path.write_text('<testsuite><testcase classname="test_tools" name="test_ok[x]"/>'
        '<testcase classname="test_tools" name="test_ok[y]"><skipped/></testcase>'
        '<testcase classname="test_tools" name="test_failed"><failure/></testcase></testsuite>')
    result=from_junit(path)
    assert status_for(['test_tools.py::test_ok'],result)[0]=='NOT_RUN'
    assert status_for(['test_tools.py::test_missing'],result)[0]=='NOT_RUN'
    assert status_for(['test_tools.py::test_failed'],result)[0]=='FAIL'
    assert status_for(['test_tools.py::test_ok[x]'],result)[0]=='PASS'


def test_all_scenario_references_exist_without_claiming_execution():
    cases=json.loads((DESIGN/'FAILURE_MATRIX.json').read_text())['cases']
    assert len(cases)==49 and set(EXTRA)<={c['id'] for c in cases}
    for c in cases:
        refs=c['existing_test_references']+[PREFIX+n for n in EXTRA.get(c['id'],[])]
        for ref in refs:
            filename,name=ref.split('::')
            functions={n.name for n in ast.parse((ROOT/filename).read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
            assert name in functions,ref
        assert status_for(refs,{})[0]=='NOT_RUN'
