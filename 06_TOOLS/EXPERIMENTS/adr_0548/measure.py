"""Three pre-registered pairs on one exact previously delivered public compose view."""
import importlib.util,json,sys,subprocess,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0548-gemma-recorded-compose-compaction';C=R/'02_BACKEND/lawrag/research/candidates/adr_0548/compact'
spec=importlib.util.spec_from_file_location('recorded_core',R/'06_TOOLS/EXPERIMENTS/adr_0547/measure.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core);core.A=A;core.C=C
read=core.read;sha=core.sha

def verify():
 d=read(A/'artifacts/frozen-design.json');assert sha(Path(__file__))==d['runner_sha256']
 for p,h in d['input_sha256'].items():assert sha(R/p)==h,'input drift '+p
 m=read(C/'candidate.json');assert sha(C/'candidate.json')==d['candidate_manifest_sha256'];v=m['revisions'][0];assert v['revision_sha256']==d['revision_sha256']
 for row in v['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
 return d,C/'revisions'/d['revision_id']/'snapshot'

def main():
 d,snapshot=verify();case=read(R/d['product_cases'])['cases'][0]
 if len(sys.argv)>1:
  arm=sys.argv[1];repeat=int(sys.argv[2]);out=A/'artifacts/run-001/fixed'/case['case_id']/'compose'/('repeat-'+str(repeat))/arm
  core.fixed(d,snapshot,case,arm,'compose',repeat,out);return
 count=0
 for repeat in range(1,4):
  for arm in (['baseline','compact'] if repeat%2 else ['compact','baseline']):
   subprocess.run([sys.executable,str(Path(__file__)),arm,str(repeat)],cwd=R,check=True)
   count+=read(A/'artifacts/run-001/fixed'/case['case_id']/'compose'/('repeat-'+str(repeat))/arm/'result.json')['physical_calls'];assert count<=12
 rows=[read(p) for p in (A/'artifacts/run-001/fixed').glob('**/result.json')]
 core.write(A/'artifacts/run-001/result.json',{'experiment_id':d['experiment_id'],'status':'complete','physical_calls':count,'rows':rows,'main_wiring_unchanged':True,'semantic_quality':'unmeasured'})
 core.emit(event='measurement.finished',physical_calls=count,results=len(rows))
if __name__=='__main__':main()
