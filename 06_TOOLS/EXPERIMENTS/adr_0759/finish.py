from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0759-query-routing-native-contract';D=A/'artifacts'
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0731/finish.py','759','Fixed acyclic receipt and fixture ownership. Critical160 and full431 checked; real metadata diagnostic found nullable coordinate entry and failed before title selection. Candidate rejected pending nullable coordinate guard; zero model calls.'],check=True)
for p in [D/'run-001/result.json',D/'contract-result.json']:
 v=json.loads(p.read_text());v['strict_success']=False;v['known_route_passed']=False;v['known_route_failure']='AttributeError: stored coordinate may be None';p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=A/'실험/manifest.json';v=json.loads(p.read_text());v['results']['by_arm']['integrated']['contracts_passed']=False;v['results']['error_taxonomy']+=['known_route_nullable_coordinate'];v['runs'][0]['sha256']=hashlib.sha256((D/'run-001/result.json').read_bytes()).hexdigest();p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=A/'README.md';s=p.read_text().replace('status: Accepted','status: Rejected').replace('Proceed with unchanged code and three fresh public paired cases under a new ADR.','Known real metadata probe failed before route selection; fix under a new ADR.');p.write_text(s)
