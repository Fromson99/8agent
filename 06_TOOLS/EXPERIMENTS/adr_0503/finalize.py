"""Seal execution reports and run required final validators; no model calls."""
from pathlib import Path
import json,hashlib,sys,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 assert read(A/'실험/manifest.json')['results']['status']=='complete'
 for args in [['hash','--path',str(A.relative_to(R))],['status','--path',str(A.relative_to(R)),'--status','completed','--note','Seven paired Gemma attempts and swapped offline evaluations recorded; limitations and one-character plan observations preserved; MAIN unchanged']]:
  subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=R,check=True,stdout=subprocess.DEVNULL)
 paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ['manifest.json','validation-final.txt','graph-check.txt','completion.json'] and not p.name.endswith(('-wal','-shm'))]
 paths+=list((R/'06_TOOLS/EXPERIMENTS/adr_0503').glob('*.py'))+[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',A/'CASE_REVIEW.md']
 if (A/'JUDGMENT_FINDINGS.md').exists():paths.append(A/'JUDGMENT_FINDINGS.md')
 for arm in ['baseline','obligations']:
  C=R/'02_BACKEND/lawrag/research/candidates/adr_0503'/arm;paths.append(C/'candidate.json');paths.extend(R/x['frozen_path'] for x in read(C/'candidate.json')['revisions'][-1]['files'])
 am=read(A/'artifacts/manifest.json');am['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, exact product/evaluator trace, or reproducible report artifact'} for p in sorted(set(paths))];write(A/'artifacts/manifest.json',am)
 index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text();link='ADR-0503-gemma-obligations-bound-paired-probe/README.md'
 if link not in s:index.write_text(s+'\n- [ADR-0503 Gemma 요구 추적 보강 전후 7문항]('+link+') — 두 설정의 실제 실행과 익명 2회 평가. 기술적 미평가·요구문 한 글자 현상을 분리 기록, MAIN 불변.\n')
 checks=[]
 for args,filename in [(['validate','--path',str(A.relative_to(R)),'--final'],'validation-final.txt'),(['graph','--adr-root','04_EXPERIMENTS/ADR'],'graph-check.txt')]:
  with (A/'artifacts'/filename).open('w') as log:p=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=R,stdout=log,stderr=subprocess.STDOUT)
  checks.append({'command':args,'exit_code':p.returncode,'output':(A/'artifacts'/filename).read_text()})
 write(A/'artifacts/completion.json',{'execution_and_reports_recorded':True,'validation':checks,'main_wiring':'unchanged'});print(json.dumps(checks,ensure_ascii=False))
if __name__=='__main__':main()
