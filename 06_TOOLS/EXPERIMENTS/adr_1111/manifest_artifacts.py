from pathlib import Path
import json,hashlib
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1111-genos-mode-scope-qualification'
paths=[p for folder in ('design','run-001') for p in (A/'artifacts'/folder).rglob('*') if p.is_file()]+list(Path(__file__).parent.glob('*.py'))+[R/'05_TESTS/CONTRACTS/test_genos_applied_mode.py']
x={'schema_version':'adr-artifacts-v1','adr_id':'ADR-1111','created_at':json.loads((A/'실험/manifest.json').read_text())['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'files':[{'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'description':'UI mode, actual scope, baseline regression and official package evidence','contains_raw_prompts_and_outputs':False} for p in paths]}
(A/'artifacts/manifest.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
