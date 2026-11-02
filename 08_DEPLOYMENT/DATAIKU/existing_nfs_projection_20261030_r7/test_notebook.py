"""Run in a separate pytest process from test_batch_read.py to isolate imports."""
from pathlib import Path
import subprocess
import sys
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT/'02_BACKEND'), str(ROOT/'05_TESTS'), str(ROOT/'05_TESTS/CONTRACTS')]
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full


@pytest.mark.parametrize('previous',['r5'])
def test_full_delivered_notebook_paused_to_r7(full, tmp_path, previous):
    result = subprocess.run([sys.executable, str(HERE/'validate_notebook.py'), str(full[7]), str(tmp_path/'native'), previous],
                            capture_output=True, text=True, timeout=180)
    (tmp_path/'native-output.txt').write_text(result.stdout + result.stderr)
    (HERE/('native-'+previous+'-latest.log')).write_text(result.stdout+result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr)[-3500:]
    assert 'NATIVE_R7_NOTEBOOK_PASS' in result.stdout
