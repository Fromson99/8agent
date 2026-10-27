"""Record terminal experiment state only; never call a model or resume a cell."""
import argparse,fcntl,json,subprocess,time
from pathlib import Path
from common import ROOT,ADR,ART,read,save,sha

def command(args):
 return subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

def observations_complete(summary, completion):
 return (completion.get('status')=='COMPLETE' and summary.get('complete_observations') is True
  and summary.get('status')=='COMPLETE_OBSERVATIONS' and summary.get('completed_product_cells')==111
  and summary.get('finished_evaluation_cases')==37 and summary.get('metrics_cells')==111
  and summary.get('ledger_cells')==111 and summary.get('source_integrity_failure_cells')==0
  and not summary.get('stop') and not summary.get('fatal_cells'))

def finish():
 completion=read(ART/'completion.json');summary=read(ART/'matrix-summary.json');freeze=read(ART/'design-freeze.json');p=ADR/'실험/manifest.json';m=read(p)
 if m['design']!=freeze['design']:raise ValueError('frozen design changed')
 complete=observations_complete(summary,completion)
 m['runs'][0].update(status='complete' if complete else 'failed',sha256=sha(ART/'matrix-summary.json'),completed_cells=summary.get('completed_product_cells',0),planned_cells=111)
 arms={('baseline' if k=='A0' else k):v for k,v in summary['arms'].items()}
 m['results'].update(status='complete' if complete else 'failed',by_arm=arms,comparisons=[{'pair':k,**v} for k,v in summary['paired_semantic'].items()],usage={k:v['usage'] for k,v in arms.items()},latency={k:v['latency_seconds'] for k,v in arms.items()},error_taxonomy=summary.get('fatal_cells',[]),quality_certified=False)
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
 if complete:
  import statistics
  ledger=read(ART/'retrieval-ledger.json');corpus=summary['corpus_total_article_roots'];flat={k:{} for k in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']}
  for arm in ledger['runs'][0]['arms']:
   stages=[case['stages'][-1] for case in arm['cases']];counts=[s['after_count'] for s in stages];ordered=sorted(counts);gold=sum(s['gold_after'] for s in stages);total=sum(s['gold_total'] for s in stages)
   values={'before_filter':sum(s['before_count'] for s in stages),'after_filter':sum(counts),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':ordered[min(len(ordered)-1,max(0,round((len(ordered)-1)*.95)))],'golden_recall':gold/total if total else None,'selectivity':statistics.mean(counts)/corpus}
   for k,v in values.items():flat[k][arm['arm_id']]=v
  m['retrieval_accounting'].update(corpus_total=corpus,**flat)
 else:
  for k,v in m['retrieval_accounting'].items():
   if isinstance(v,dict) and str(v.get('status','')).startswith('NOT_MEASURED'):v['status']='NOT_MEASURED_INCOMPLETE_EXECUTION'
 save(p,m)
 (ADR/'README.md').write_text((ADR/'README.md').read_text()+f"\n\n최종 실행 기록: 제품 완료 관찰 {summary.get('completed_product_cells',0)}/111, 평가 {summary.get('finished_evaluation_cases',0)}/37, 실행기 상태 {completion['status']}. 원본과 미확인 상태는 artifacts/RESULT.md 및 matrix-summary.json을 따른다. 품질 인증·MAIN 승격 아님.\n")
 command(['hash','--path',str(ADR)])
 state=command(['status','--path',str(ADR),'--status','completed' if complete else 'abandoned','--note','All observations recorded; no MAIN promotion.' if complete else 'Stopped experiment preserved; no automatic replay or completion claim.'])
 checks={}
 for name,args in [('structure',['validate','--path',str(ADR)]),('final',['validate','--path',str(ADR),'--final']),('graph',['graph','--adr-root',str(ROOT/'04_EXPERIMENTS/ADR')])]:
  r=command(args);(ART/(name+'-check.log')).write_text(r.stdout);checks[name]={'exit_code':r.returncode,'log':str((ART/(name+'-check.log')).relative_to(ROOT))}
 save(ART/'finalization-result.json',{'observations_complete':complete,'complete_claimed':complete and checks['final']['exit_code']==0,'checks':checks,'quality_certified':False,'main_changed':False,'automatic_retry':False})
 files=[]
 for path in sorted(ART.rglob('*')):
  if path.is_file() and path.name!='manifest.json' and not path.name.startswith('.'):
   files.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size,'description':'Frozen input, exact execution evidence, validation or derived report','contains_raw_prompts_and_outputs':path.name in ('request.json','response.json','output.json')})
 save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1054','files':files})
 return 0 if complete else 2

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--wait',action='store_true');args=parser.parse_args();plan=read(ART/'finalization-plan.json')
 for n,h in plan['files'].items():
  if sha(ROOT/n)!=h:raise ValueError('finalization file changed: '+n)
 with (ART/'.finalizer.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if (ART/'finalization-result.json').exists():raise ValueError('finalization already recorded')
  while args.wait and not (ART/'completion.json').exists():time.sleep(15)
  return finish()
if __name__=='__main__':raise SystemExit(main())
