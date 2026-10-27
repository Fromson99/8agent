"""Finalize records after the service exits; no model calls or product replays."""
from __future__ import annotations
import argparse
import fcntl
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from supervise import ROOT,AUDIT,EXPERIMENT,UNIT,read,save,sha,stamp,check
SOURCE=EXPERIMENT.parent
OPS=AUDIT.parent
METRICS=('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')

def command(args):
 return subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

def complete_observations(summary,completion):
 return (completion.get('status')=='COMPLETE' and summary.get('complete_observations') is True
  and summary.get('status')=='COMPLETE_OBSERVATIONS'
  and summary.get('completed_product_cells')==111 and summary.get('metrics_cells')==111
  and summary.get('ledger_cells')==111 and summary.get('finished_evaluation_cases')==37
  and summary.get('source_integrity_failure_cells')==0 and not summary.get('stop') and not summary.get('fatal_cells'))

def artifact_manifest(adr):
 files=[]
 for p in sorted((adr/'artifacts').rglob('*')):
  if not p.is_file() or p.name=='manifest.json' or p.name.startswith('.') or p.name.startswith('finalizer-'):continue
  files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
   'description':'Original evidence, frozen binding, execution receipt, or explicitly derived report.',
   'contains_raw_prompts_and_outputs':p.name in ('request.json','response.json','output.json')})
 save(adr/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':read(adr/'claim.json')['adr_id'],
  'created_at':stamp(),'files':files})

def flat_retrieval(ledger,corpus):
 out={k:{} for k in METRICS}
 for arm in ledger['runs'][0]['arms']:
  aid=arm['arm_id'];stages=[case['stages'][-1] for case in arm['cases']]
  counts=[s['after_count'] for s in stages];ordered=sorted(counts)
  gold=sum(s['gold_after'] for s in stages);total=sum(s['gold_total'] for s in stages)
  values={'before_filter':sum(s['before_count'] for s in stages),'after_filter':sum(counts),
   'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),
   'presented_p95':ordered[min(len(ordered)-1,max(0,round((len(ordered)-1)*.95)))],
   'golden_recall':gold/total if total else None,'selectivity':statistics.mean(counts)/corpus}
  for k,v in values.items():out[k][aid]=v
 return out

def finalize():
 check(read(AUDIT/'resume-plan.json'))
 completion=read(AUDIT/'completion.json');summary=read(EXPERIMENT/'matrix-summary.json')
 if not complete_observations(summary,completion):
  save(AUDIT/'finalizer-result.json',{'status':'INCOMPLETE_PRESERVED','recorded_at':stamp(),
    'completion':completion,'summary_status':summary.get('status'),'automatic_retry':False,'experiment_complete_claimed':False})
  return 2
 ledger=read(EXPERIMENT/'retrieval-ledger.json');freeze=read(EXPERIMENT/'design-freeze.json')
 p=SOURCE/'실험/manifest.json';m=read(p)
 if m['design']!=freeze['design']:raise ValueError('frozen experimental design changed')
 m['runs'][0].update(status='complete',artifact_path=str((EXPERIMENT/'matrix-summary.json').relative_to(ROOT)),sha256=sha(EXPERIMENT/'matrix-summary.json'))
 arms={('baseline' if k=='A0' else k):v for k,v in summary['arms'].items()}
 m['results'].update(status='complete',by_arm=arms,comparisons=[{'pair':k,**v} for k,v in summary['paired_semantic'].items()],
  judge_disagreements=None,usage={k:v['usage'] for k,v in arms.items()},latency={k:v['latency_seconds'] for k,v in arms.items()},
  error_taxonomy=[{'arm':k,'types':v['semantic']['failure_types']} for k,v in arms.items()],
  calibration='Not performed; provisional same-model offline evaluator.',provider_mix_report=str((EXPERIMENT/'provider-summary.json').relative_to(ROOT)))
 m['retrieval_accounting'].update(corpus_total=summary['corpus_total_article_roots'],**flat_retrieval(ledger,summary['corpus_total_article_roots']))
 m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((EXPERIMENT/'retrieval-ledger.json').relative_to(ROOT)),sha256=sha(EXPERIMENT/'retrieval-ledger.json'))
 for row in m['questions']:row['sha256']=sha(SOURCE/'실험'/row['file'])
 save(p,m)
 p=SOURCE/'README.md';text=p.read_text();text=text.replace('실행 중. 모든111셀 관찰이 완료된 뒤 오프라인 평가를 순차 실행하고 artifacts/RESULT.md와 matrix-summary.json을 집계하도록 연결했다. 아직 전체 실험 완료나 제공자 전환의 실제 성공을 주장하지 않는다.',
 '111개 제품 관찰과37개 오프라인 평가 기록의 집계를 마쳤다. 실제 답변 성공·실패·미확정 및 제공자 전환 건수는 artifacts/RESULT.md, matrix-summary.json, provider-summary.json에 구분한다. 품질 승인이나 MAIN 승격을 뜻하지 않는다.')
 text+='\n\n운영 복구: ADR1050에서 기존18개 기록을 보존하고19번째부터 동일 동결 실행을 이어갔다. 전체 실행·평가 관찰의 완료와 사전 품질기준 충족은 별도다. 최종 구조 검사 기록은 ADR1050 artifacts/finalizer-result.json을 따른다.\n'
 p.write_text(text)
 # This operational audit reports lifecycle proof and integrity, not new legal answers.
 result={'status':'OPERATIONAL_RECOVERY_COMPLETE','recorded_at':stamp(),'contracts_passed':11,
  'finalization_contracts_passed':11,'service_lifecycle_tests':read(AUDIT/'service-lifecycle-validation.json'),'existing18_preserved':True,
  'source_experiment':freeze['experiment_id'],'product_cells':111,'evaluation_cases':37,
  'new_audit_model_calls':0,'source_result_path':str((EXPERIMENT/'matrix-summary.json').relative_to(ROOT)),
  'source_result_sha256':sha(EXPERIMENT/'matrix-summary.json'),'main_changed':False}
 save(AUDIT/'recovery-result.json',result)
 p=OPS/'실험/manifest.json';op=read(p);op['results'].update(status='complete',by_arm={'baseline':result})
 op['runs'][0].update(status='complete',artifact_path=str((AUDIT/'recovery-result.json').relative_to(ROOT)),sha256=sha(AUDIT/'recovery-result.json'))
 save(p,op)
 validations={}
 for adr in (SOURCE,OPS):
  artifact_manifest(adr)
  result=command(['hash','--path',str(adr)])
  if result.returncode:raise ValueError(result.stdout)
  result=command(['validate','--path',str(adr)])
  if result.returncode:raise ValueError(result.stdout)
  result=command(['status','--path',str(adr),'--status','completed','--note','All originally planned observations and reports finished; original18 preserved; no replay, policy change or MAIN promotion.'])
  if result.returncode:raise ValueError(result.stdout)
  result=command(['validate','--path',str(adr),'--final'])
  validations[adr.name]={'exit_code':result.returncode,'output':result.stdout}
 graph=command(['graph','--adr-root',str(ROOT/'04_EXPERIMENTS/ADR')])
 # Existing unrelated graph errors never become a successful global graph check.
 payload={'status':'VALIDATED' if all(v['exit_code']==0 for v in validations.values()) else 'VALIDATION_FAILED',
  'recorded_at':stamp(),'validations':validations,'graph':{'exit_code':graph.returncode,'output':graph.stdout},
  'observations_complete':True,'quality_certified':False,'main_changed':False}
 save(AUDIT/'finalizer-result.json',payload)
 return 0 if payload['status']=='VALIDATED' else 2

def main():
 p=argparse.ArgumentParser();p.add_argument('--wait',action='store_true');args=p.parse_args()
 plan=read(AUDIT/'finalization-plan.json')
 for relative,expected in plan['files'].items():
  if sha(ROOT/relative)!=expected:raise ValueError('finalization script binding changed: '+relative)
 with (AUDIT/'.finalizer.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if (AUDIT/'finalizer-result.json').exists():raise ValueError('finalization already attempted; inspect instead of overwriting')
  while args.wait:
   state=subprocess.run(['systemctl','--user','show',UNIT,'-p','SubState','--value'],capture_output=True,text=True,check=True).stdout.strip()
   if state not in ('running','start','start-pre','start-post','stop','stop-sigterm','stop-sigkill'):break
   save(AUDIT/'finalizer-status.json',{'status':'WAITING_FOR_EXISTING_SERVICE','updated_at':stamp(),'model_calls':0})
   time.sleep(15)
  if not (AUDIT/'completion.json').exists():
   save(AUDIT/'finalizer-result.json',{'status':'SERVICE_INCOMPLETE','recorded_at':stamp(),'automatic_retry':False});return 2
  return finalize()
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  save(AUDIT/'finalizer-result.json',{'status':'FINALIZATION_ERROR','recorded_at':stamp(),'error':str(exc),'type':type(exc).__name__,'automatic_retry':False});raise
