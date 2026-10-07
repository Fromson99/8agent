"""Close completed product/evaluator run, index receipts, run final checks."""
import json,hashlib,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10';ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=read(A/'실험/manifest.json');assert m['results']['status']=='complete'
 comparison=ART/'model-comparison.json'
 if comparison.is_file():
  c=read(comparison);m['results']['comparisons']=[{'path':str(comparison.relative_to(R)),'sha256':sha(comparison),'cohorts':c['cohorts'],'pairs':c['pairs']}]
  m['results']['comparison_note']='Descriptive same-case comparison with ADR0496; provider/time/load and judge self-preference confound causal attribution'
 else:m['results']['comparison_note']='Qwen ADR0496 is not scored yet. Gemma evaluation complete; matched comparison remains pending.'
 write(A/'실험/manifest.json',m)
 commands=[['hash','--path',str(A.relative_to(R))],['status','--path',str(A.relative_to(R)),'--status','completed','--note','All61 Gemma attempts, Qwen evaluator, traces and diagnostic report written; MAIN unchanged']]
 for args in commands:subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=R,check=True,stdout=subprocess.DEVNULL)
 am=read(ART/'manifest.json');volatile={'manifest.json','offline-execution.json','offline-progress.log','validation-final.txt','graph-check.txt','completion.json'}
 paths={p for p in ART.rglob('*') if p.is_file() and p.name not in volatile and not p.name.endswith(('-wal','-shm')) and not p.name.startswith('offline-')}
 paths.update((R/'06_TOOLS/EXPERIMENTS/adr_0498').glob('*.py'))
 paths.update(A/name for name in ['PLAN.md','product-cases.json','gold-cases.json','CASE_REVIEW.md','COMPARISON.md'] if (A/name).exists())
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0498/gemma';paths.add(C/'candidate.json');paths.update(R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files'])
 am['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input or execution/evaluation receipt'} for p in sorted(paths)];write(ART/'manifest.json',am)
 index=R/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();link='('+A.name+'/README.md)'
 if link not in text:index.write_text(text+'\n- [ADR-0498 Gemma4 FP8 동일 RAG61문항]'+link+' — Gemma 생성/Qwen 채점; 상세 수치·제약은 리포트, MAIN 불변.\n')
 results=[]
 for args,filename in [(['validate','--path',str(A.relative_to(R)),'--final'],'validation-final.txt'),(['graph','--adr-root','04_EXPERIMENTS/ADR'],'graph-check.txt')]:
  with (ART/filename).open('w') as log:p=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=R,stdout=log,stderr=subprocess.STDOUT)
  results.append({'command':args,'returncode':p.returncode,'log':filename})
 receipt={'finished_at':time.time(),'product_and_scoring_complete':True,'comparison_complete':comparison.is_file(),'validation':results,'main_wiring':'unchanged'};write(ART/'completion.json',receipt);print(json.dumps(receipt))
 if any(x['returncode'] for x in results):raise SystemExit(1)
if __name__=='__main__':main()
