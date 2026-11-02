from pathlib import Path
import sys,json,hashlib,shutil
R=Path('/home/jin/8-AGENT');P=R/'04_EXPERIMENTS/ADR/ADR-1259-wiki-typed-proposal-oracle-live';A=R/'04_EXPERIMENTS/ADR/ADR-1260-wiki-literal-glossary-oracle-live';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');C=R/f['code_root'];names=set(f['files'])
put(D/'baseline.json',{'parent_freeze':str((P/'artifacts/design/freeze.json').relative_to(R)),'parent_sha256':sha(P/'artifacts/design/freeze.json'),'active':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(R/n) for n in sorted(names) if (R/n).is_file()}})
for name in ['records.json','originals.json','source-binding.json']:shutil.copy2(P/'artifacts/design'/name,D/name)
c=read(P/'artifacts/design/criteria.json');c['new_contract_gates']=['Automatic exact-surface candidates exclude broader token fallback without hydrating it','Explicit caller label lookup retains broader behavior','Deferred candidates remain visible as unsearched, not absence','Same source/ACL/version/hash checks before and after model','No query/physical/deadline/space budget increase'];put(D/'criteria.json',c)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Automatic literal fragments should not silently expand to arbitrary label-token meanings; full explicit navigation remains available and unsearched fallback is disclosed.'
m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric='All actual chain gates within unchanged budgets',success_criteria=c['gates']+c['new_contract_gates'],failure_criteria=c['stop'])
m['design']['arms'][0].update(changes='Completed1259 budget failure, no repeated live baseline',controls='Same archived2 records/Oracle4 units/24physical1800overall600projection')
m['design']['arms'][1].update(changes='Exact-surface only for auto-derived literal glossary queries; broad explicit lookup preserved',controls='Original v1 compiler, original source checks, limits and canonical storage unchanged')
m['retrieval_accounting'].update(changed=True)
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(A,'literal',[n for n in sorted(names) if (R/n).is_file()],experiment_id=m['experiment_id'],arm_id='literal',run_ids=['run-001']);S=candidate/'snapshot'
for n in sorted(names):
 assert sha(C/n)==f['files'][n]
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(C/n,p)
 if not (R/n).is_file():ac.register_file(candidate,n,upstream_state='absent')
T=R/'06_TOOLS/EXPERIMENTS/adr_1260'
for name in ['common.py','live.py','native.py','freeze.py','check.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1259'/name).read_text().replace('1259-wiki-typed-proposal-oracle-live','1260-wiki-literal-glossary-oracle-live').replace('1259','1260').replace("/typed'","/literal'").replace("candidate_id='typed'","candidate_id='literal'").replace("arm_id='typed'","arm_id='literal'")
 (T/name).write_text(s)
print(candidate,len(names))
