from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e'
m=json.loads((A/'실험/manifest.json').read_text())
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=(A/'artifacts/manifest.json') and not p.name.endswith(('-shm','.lock'))]
files+=list((R/'06_TOOLS/EXPERIMENTS/adr_0817').glob('*.py'))
value={'schema_version':'adr-artifacts-v1','adr_id':'ADR-0817','created_at':m['reservation']['created_at'],
       'files':[{'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,
                 'description':'Actual frozen-service requests, provider I/O, native journals and post-run source/consumer audit',
                 'contains_raw_prompts_and_outputs':'raw' in p.parts or 'runtime' in p.parts or p.suffix=='.log'} for p in sorted(files)]}
(A/'artifacts/manifest.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('Indexed',len(files),'artifacts; native WAL files retained when present')
