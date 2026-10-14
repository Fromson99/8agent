from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'bindings.json');C=R/b['stage'];pm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0702/coupled/candidate.json');P=R/'02_BACKEND/lawrag/research/candidates/adr_0702/coupled/revisions'/pm['revisions'][-1]['revision_id']/'snapshot'
files={f['target_path']:sha(P/f['target_path']) for f in pm['files']}
for p,h in files.items():assert sha(C/p)==h,p
pr=R/'04_EXPERIMENTS/ADR/ADR-0702-exception-state-wire-contract/artifacts/contracts/result.json';r=read(pr);assert not r['new_failures']
put(A/'artifacts/contracts/inherited-receipt.json',{'status':'byte-identical-parent-contracts-reused','parent_result':{'path':str(pr.relative_to(R)),'sha256':sha(pr)},'parent_code':str(P.relative_to(R)),'evaluated_code':str(C.relative_to(R)),'files':files,'contracts_passed':r['contracts']['passed'],'legacy_failures':len(r['contracts']['failures']),'new_failures':0,'model_calls':0})
cm=read(R/read(D/'freeze.json')['candidate']['manifest_path']);changes=[]
for f in cm['files']:
 p=f['target_path'];cur=sha(R/p) if (R/p).is_file() else None;after=sha(C/p)
 if cur!=after:
  assert cur==f.get('upstream_sha256'),p
  changes.append({'path':p,'before':cur,'after':after})
put(A/'artifacts/working-review.json',{'changes':changes,'no_concurrent_drift':True,'not_installed':True,'review_basis':'Inherited reviewed scope; source/profiles/engines/display/error/structured search/completion/read plan; all540files match completed702, with model-wire exception state coupling.'})
print(len(files),'inherited files;',len(changes),'scoped working changes;',r['contracts']['passed'],'passed')
