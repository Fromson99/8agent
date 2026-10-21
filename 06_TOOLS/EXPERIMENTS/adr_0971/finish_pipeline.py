"""Continue this explicitly authorized one-off run after its existing encoder exits.

No scheduler, new experiment, retries, production switches or independent model workers.
"""
from common import *
import os,time,subprocess,fcntl,traceback
lock=(ART/'continuation.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
state={'status':'waiting_for_existing_encoder','started_at':time.time(),'pid':os.getpid(),'stages':[]}
put(ART/'continuation.json',state)
def progress():
 s=read(RUN/'embedding-state.json') if (RUN/'embedding-state.json').exists() else {}
 n=read(RUN/'corpus-summary.json')['chunks'];elapsed=max(1,time.time()-s.get('started_at',time.time()));done=s.get('rows',0)
 text=f'구조화 외규 독립문서70 벡터 구축\n\n상태: {state["status"]}\n검증된 원문:70문서 /275494블록 /15045602자 /누락0건\n저장 완료 벡터: {done:,} / {n:,} ({done/n:.1%})\n경과: {elapsed/60:.1f}분\n마지막 갱신: {time.strftime("%Y-%m-%d %H:%M:%S %Z")}\n\n동일 입력과 원문·모델·코드 해시를 고정한 순차 실행. MAIN 변경 없음.\n벡터 완료 후 검색51문항→리랭커51문항→사전6문항 답변 비교→결과 기록 순서.\n외부 모델 첫 실패 시 추가 외부 호출 중단. CPU 임베딩 누적 실행 한도6시간.\n완료 결과: RESULT.txt / artifacts/run-001/result.json\n실행 기록: artifacts/continuation.json\n'
 (ADR/'PROGRESS.txt').write_text(text)
def command(label,args,allowed=(0,)):
 state['status']=label;put(ART/'continuation.json',state);progress()
 with (ART/(label+'.log')).open('x') as f:result=subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 state['stages'].append({'stage':label,'returncode':result.returncode,'at':time.time()});put(ART/'continuation.json',state)
 if result.returncode not in allowed:raise RuntimeError(label+' failed; see preserved stage log')
py=str(ROOT/'.venv/bin/python');base=[py,'-B'];tool=[py,'06_TOOLS/run_tool.py','adr_structure.py']
try:
 while not (ART/'resource-embed.json').exists():
  progress();time.sleep(30)
 result=read(ART/'resource-embed.json')
 if result['returncode']!=0 or result['stop_reason'] or not (RUN/'embed-receipt.json').exists():raise RuntimeError('Encoder did not complete; preserve committed shards and original cumulative budget')
 for stage in ['retrieve','rerank','answer']:
  args=base+['06_TOOLS/EXPERIMENTS/resource_guard.py','--record',str((ART/('resource-'+stage+'.json')).relative_to(ROOT)),'--rss-gib','5.5','--as-gib','9','--min-available-gib','3','--min-disk-gib','10','--']+base+['06_TOOLS/EXPERIMENTS/adr_0971/run.py',stage]
  command(stage,args)
 command('judge',base+['06_TOOLS/EXPERIMENTS/adr_0971/judge_current_reference.py'])
 command('report',base+['06_TOOLS/EXPERIMENTS/adr_0971/report.py'])
 # All data/model workers are terminated before hashing and final validation.
 paths=list(ART.rglob('*'))+list((ROOT/'06_TOOLS/EXPERIMENTS/adr_0971').glob('*.py'))
 for arm in ['dense','dense-rerank']:
  candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0971'/arm
  paths+=[candidate/'candidate.json']+list((candidate/'revisions').rglob('*.py'))
 ignored={'manifest.json','continuation.json','continuation.lock','continuation.log'}
 files=[]
 for path in sorted(set(paths)):
  if not path.is_file() or path.name in ignored or path.name.endswith('.tmp') or path.name.startswith('validate-') or path.name=='graph.log':continue
  files.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path),'description':'Frozen design/source, complete vectors, lossless original payload or post-selection offline audit','contains_raw_prompts_and_outputs':'raw' in path.parts})
 put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0971','files':files})
 command('validate-structure',tool+['validate','--path',str(ADR.relative_to(ROOT))])
 # Keep reservation mutable until all other final checks pass.
 command('validate-precompletion',tool+['validate','--path',str(ADR.relative_to(ROOT)),'--final'],allowed=(0,1,2))
 errors=[line for line in (ART/'validate-precompletion.log').read_text().splitlines() if line.startswith('ERROR:')]
 if any('reservation' not in line and 'completed' not in line for line in errors):raise RuntimeError('Final precompletion checks need repair; reservation remains open')
 command('status-completed',tool+['status','--path',str(ADR.relative_to(ROOT)),'--status','completed','--note','Full70 stored text vector coverage, serial CM51 probe and exact artifact/source records complete; answer failures and semantic limits reported separately'])
 command('validate-final',tool+['validate','--path',str(ADR.relative_to(ROOT)),'--final'])
 command('graph',tool+['graph','--adr-root','04_EXPERIMENTS/ADR'],allowed=(0,1,2))
 index=ROOT/'04_EXPERIMENTS/ADR/README.md';line='- [ADR-0971 구조화 외규70 전체 벡터](ADR-0971-fulltext-vector70/RESULT.txt) — 저장된 원문 무누락 구축, CM51 검색 비교. MAIN 불변.\n'
 if 'ADR-0971-fulltext-vector70' not in index.read_text():
  with index.open('a') as f:f.write('\n'+line)
 state.update(status='complete',completed_at=time.time());put(ART/'continuation.json',state);progress()
except BaseException as exc:
 state.update(status='needs_attention',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc(),stopped_at=time.time());put(ART/'continuation.json',state);progress();raise
