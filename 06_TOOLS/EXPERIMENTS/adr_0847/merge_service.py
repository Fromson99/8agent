from pathlib import Path
import hashlib,json,subprocess,tempfile,shutil
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0847/lifecycle';D=R/'04_EXPERIMENTS/ADR/ADR-0847-basis-link-lifecycle/artifacts/design'
sha=lambda b:hashlib.sha256(b).hexdigest()
p=C/'snapshot/service.py';ours=p.read_text();base=ours
base=base.replace(', "/v1/basis-links/proposals", "/v1/basis-links/reviews"','')
base=base.replace('        "BASIS_LINKS_LIST", "BASIS_LINKS_PROPOSE", "BASIS_LINKS_REVIEW", "BASIS_LINKS_HISTORY", "BASIS_MIGRATION_STATUS",\n','')
a=base.index('    if api_type in {"BASIS_LINKS_PROPOSE"');z=base.index('    if api_type in {"WORKFLOW_RUN"',a);base=base[:a]+base[z:]
base='\n'.join(line for line in base.split('\n') if not ('allowed = allowed or' in line and 'basis-links' in line))
w=json.loads((D/'working-before.json').read_text());assert sha(base.encode())==w['service.py'],'base reconstruction differs'
current=(R/'service.py').read_bytes()
with tempfile.TemporaryDirectory() as td:
 folder=Path(td)
 for name,data in [('ours',ours.encode()),('base',base.encode()),('current',current)]: (folder/name).write_bytes(data)
 result=subprocess.run(['git','merge-file','-p',str(folder/'ours'),str(folder/'base'),str(folder/'current')],capture_output=True)
 assert result.returncode==0,result.stderr
 p.write_bytes(result.stdout)
receipt={'path':'service.py','initial_sha256':w['service.py'],'concurrent_sha256':sha(current),'merged_sha256':sha(p.read_bytes()),'method':'three-way merge; all Oracle DP source routing preserved'}
(D/'concurrent-service-merge.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Date query uses the public contract name.
s=p.read_text().replace('("internal_document_id","as_of_date")','("internal_document_id","as_of")');p.write_text(s)
for name in ['02_BACKEND/semantic_runtime/oracle_dp.py']:
 dest=C/'snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/name,dest);w[name]=sha((R/name).read_bytes())
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',name,'--upstream-state','present'],check=True,stdout=subprocess.DEVNULL)
(D/'working-before.json').write_text(json.dumps(w,indent=2)+'\n')
