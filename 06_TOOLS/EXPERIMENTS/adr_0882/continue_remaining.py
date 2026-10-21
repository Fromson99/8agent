from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract/artifacts'
p=A/'resource-continuation.json';assert not p.exists();p.write_text(json.dumps({'reason':'cm-008 isolated worker reached 8GiB; its failure preserved. Continue only two originally frozen, never attempted cases in separate sequential workers. No repeat of interrupted case or relaxed limit.','cases':['cm-033','cm-051'],'rss_gib':8},ensure_ascii=False,indent=2))
for cid in ('cm-033','cm-051'):
 with (A/(cid+'.log')).open('x') as out:
  s=subprocess.run([str(R/'.venv/bin/python'),str(T.parent/'resource_guard.py'),'--record',str(A/('resource-'+cid+'.json')),'--',str(R/'.venv/bin/python'),str(T/'live.py'),cid],stdout=out,stderr=subprocess.STDOUT,cwd=R)
 print(cid,s.returncode,flush=True)
 if json.loads((A/('resource-'+cid+'.json')).read_text())['stop_reason']:break
