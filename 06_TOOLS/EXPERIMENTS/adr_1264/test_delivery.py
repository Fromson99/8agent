from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full

def test_delivered_queue(full,tmp_path):
 out=ROOT/'04_EXPERIMENTS/ADR/ADR-1264-dataiku-queued-verify-kure/artifacts/run-003'
 out.mkdir(exist_ok=False)
 result=subprocess.run([sys.executable,str(Path(__file__).with_name('integration.py')),str(full[7]),str(tmp_path/'fixture'),'r5'],capture_output=True,text=True,timeout=180)
 (out/'integration.log').write_text(result.stdout+result.stderr)
 assert result.returncode==0,(result.stdout+result.stderr)[-5000:]
 assert 'R12_DELIVERED_INTEGRATION_PASS' in result.stdout
