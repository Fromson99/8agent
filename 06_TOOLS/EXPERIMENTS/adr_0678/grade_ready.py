"""Schedule ready outputs using the byte-identical sealed evaluator."""
from pathlib import Path
import concurrent.futures,hashlib,json,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
G=R/'06_TOOLS/EXPERIMENTS/adr_0678/grade.py'
seal=json.loads((A/'artifacts/design/freeze.json').read_text())['files'][str(G.relative_to(R))]
source=G.read_text();assert hashlib.sha256(G.read_bytes()).hexdigest()==seal
namespace={'__file__':str(G),'__name__':'sealed_evaluator_functions'}
last=source.index('with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:')
exec(compile(source[:last],str(G),'exec'),namespace)
all_pairs=[(arm,g) for g in namespace['gold'] for arm in ('integrated',)]
while True:
 assert hashlib.sha256(G.read_bytes()).hexdigest()==seal
 ready=[(a,g) for a,g in all_pairs if (A/'artifacts/run-001'/a/g['case_id']/'result.json').exists() and not (A/'artifacts/run-001'/a/g['case_id']/'grade.json').exists()]
 if ready:
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(namespace['grade'],ready))
 if all((A/'artifacts/run-001'/a/g['case_id']/'grade.json').exists() for a,g in all_pairs):break
 time.sleep(15)
print('All 32 frozen one-call grades complete',flush=True)
