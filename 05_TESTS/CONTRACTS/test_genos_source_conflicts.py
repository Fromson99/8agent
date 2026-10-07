import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import pytest
from semantic_runtime.contracts import sha
from test_document_release import source

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('source_conflicts', ROOT / '06_TOOLS/OFFLINE/genos_source_conflicts.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_identical_duplicates_and_disjoint_sources(tmp_path):
    a = source(tmp_path / 'a.sqlite', [('one', '모의문서', ['모의본문'])])
    b = source(tmp_path / 'b.sqlite', [('one', '모의문서', ['모의본문']), ('two', '모의문서2', ['본문'])])
    before = [sha(a), sha(b)]
    result = tool.scan([a, b, a])
    assert result['conflict_count'] == 0
    assert result['identical_duplicates'] == 1
    assert result['unique_documents'] == 2
    assert [sha(a), sha(b)] == before


def test_same_raw_changed_structure_and_different_raw_all_reported(tmp_path):
    docs = [('one', '모의문서', ['본문1']), ('two', '모의문서2', ['본문2'])]
    a = source(tmp_path / 'a.sqlite', docs)
    b = source(tmp_path / 'b.sqlite', docs)
    with sqlite3.connect(b) as db:
        db.execute("UPDATE source_unit SET json='{}' WHERE document_id='one'")
        db.execute("UPDATE document SET source_artifact_sha256='other' WHERE document_id='two'")
    before = [sha(a), sha(b)]
    result = tool.scan([a, b])
    assert result['conflict_count'] == 2
    assert [v['classification'] for v in result['conflicts']] == [
        'SAME_RAW_DIFFERENT_ROWS', 'DIFFERENT_OR_MISSING_RAW_HASH']
    assert not result['selected_winner'] and result['model_calls'] == 0
    assert [sha(a), sha(b)] == before
    assert '본문1' not in str(result)


def test_missing_input_not_created(tmp_path):
    path = tmp_path / 'absent.sqlite'
    with pytest.raises(FileNotFoundError):
        tool.scan([path])
    assert not path.exists()


def test_change_during_diagnosis_rejected(tmp_path):
    a = source(tmp_path / 'a.sqlite', [('one', '모의문서', ['본문'])])
    def mutate(message, **kwargs):
        with sqlite3.connect(a) as db:
            db.execute("UPDATE document SET name='changed'")
    with pytest.raises(ValueError, match='changed during diagnosis'):
        tool.scan([a], emit=mutate)


def test_database_connection_is_read_only(tmp_path):
    a = source(tmp_path / 'a.sqlite', [('one', '모의문서', ['본문'])])
    with tool.connect(a) as db:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            db.execute('DELETE FROM document')


def test_handoff_contains_exact_tool_and_valid_shell():
    txt = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SOURCE_CONFLICTS_R1_UTF8.txt'
    embedded = txt.read_text().split("<<'GENOS_CONFLICT_PY'\n", 1)[1].rsplit('\nGENOS_CONFLICT_PY', 1)[0]
    assert embedded == (ROOT / '06_TOOLS/OFFLINE/genos_source_conflicts.py').read_text()
    subprocess.run(['bash', '-n', str(txt)], check=True)


def test_r2_field_interpreter_without_checkout_venv(tmp_path):
    txt = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SOURCE_CONFLICTS_R2_UTF8.txt'
    embedded = txt.read_text().split("<<'GENOS_CONFLICT_PY'\n", 1)[1].rsplit('\nGENOS_CONFLICT_PY', 1)[0]
    assert embedded == (ROOT / '06_TOOLS/OFFLINE/genos_source_conflicts.py').read_text()
    subprocess.run(['bash', '-n', str(txt)], check=True)
    # Mimic the field: no checkout .venv, python3 supplied by the active environment.
    field = tmp_path / 'field'
    marker = field / '02_BACKEND/lawrag/pipeline/document_release.py'
    marker.parent.mkdir(parents=True)
    marker.touch()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    interpreter = bin_dir / 'python3'
    interpreter.write_text('#!/bin/bash\nif [[ "$2" == -c ]]; then exec "' + str(ROOT / '.venv/bin/python') + '" "$@"; fi\nexec "' + str(ROOT / '.venv/bin/python') + '" - --help\n')
    interpreter.chmod(0o700)
    env = {**os.environ, 'GENOS_CODE_ROOT': str(field),
           'PYTHONPATH': str(ROOT / '02_BACKEND'), 'PATH': str(bin_dir) + ':' + os.environ['PATH']}
    result = subprocess.run(['bash', str(txt)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PYTHON executable=' in result.stdout and 'usage:' in result.stdout
    assert not (field / '.venv').exists()
