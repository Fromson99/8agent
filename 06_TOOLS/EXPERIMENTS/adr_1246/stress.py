"""Run only RAM cursor/writer interleaving, in its own process (no Oracle)."""
from pathlib import Path
import sys,json,os,faulthandler
faulthandler.enable()
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1246-oracle-record-storage-safety';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());mode=sys.argv[1];C=R/(read(D/'baseline.json')['manifest']['code_root'] if mode=='baseline' else read(D/'freeze.json')['code_root'])
sys.path[:0]=[str(C/'02_BACKEND'),str(Path(__file__).parent)]
import test_safety as tests
os.environ.update(DP='oracle',GENOS_RUNTIME_DIR='/oracle-safety-contract')
for key in ('GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR','GENOS_STATE_DIR'):os.environ.pop(key,None)
records=tests.MemoryRecords()
with tests.paths.using(records):tests.test_interleaved_writer_keeps_detached_cursor_snapshot((records,tests.paths.Path('/oracle-safety-contract/journal.sqlite')))
print('CURSOR_INTERLEAVING_PASS',mode,records.commits)
