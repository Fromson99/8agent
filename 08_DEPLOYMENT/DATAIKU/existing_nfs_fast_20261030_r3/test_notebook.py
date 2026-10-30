"""Run in a separate pytest process from test_batch_read.py to isolate imports."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT/'02_BACKEND'), str(ROOT/'05_TESTS'), str(ROOT/'05_TESTS/CONTRACTS')]
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full


def test_full_delivered_notebook_r2_paused_to_r3(full, tmp_path):
    result = subprocess.run([sys.executable, str(HERE/'validate_notebook.py'), str(full[7]), str(tmp_path/'native')],
                            capture_output=True, text=True, timeout=120)
    (tmp_path/'native-output.txt').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'NATIVE_R3_NOTEBOOK_PASS' in result.stdout
