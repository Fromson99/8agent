"""Exactly the prespecified four synthetic cases, with alternating arm order."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery'
freeze=json.loads((A/'artifacts/design/freeze.json').read_text())
for f,h in freeze['shared_files'].items():
    assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
criteria=json.loads((A/'artifacts/design/criteria.json').read_text())
codes={'baseline':A/'artifacts/design/baseline-code','integrated':R/freeze['code_root']}
for i,case in enumerate(criteria['model_probe']['cases']):
    for arm in (('baseline','integrated') if i%2==0 else ('integrated','baseline')):
        out=A/'artifacts/run-001/probe'/case['id']/arm
        out.mkdir(parents=True,exist_ok=True)
        assert not (out/'result.json').exists(),'Existing outcomes cannot be overwritten'
        env={**os.environ,'ADR688_PROBE_CASE':case['id'],'ADR688_PROBE_ARM':arm,'PYTHONDONTWRITEBYTECODE':'1'}
        with (out/'execution.log').open('w') as stream:
            p=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0688/run_contracts.py'),
                str(codes[arm]),'06_TOOLS/EXPERIMENTS/adr_0688/test_model_probe.py','-s','--show-capture=no'],cwd=R,env=env,
                stdout=stream,stderr=subprocess.STDOUT)
        if p.returncode:
            print(json.dumps({'case':case['id'],'arm':arm,'setup_exit_code':p.returncode}),flush=True)
        else:
            r=json.loads((out/'result.json').read_text())
            print(json.dumps({'case':case['id'],'arm':arm,'calls':r['calls'],'original_delivered':r['original_delivered'],
                              'valid':all(s['valid'] for s in r['steps'])}),flush=True)
