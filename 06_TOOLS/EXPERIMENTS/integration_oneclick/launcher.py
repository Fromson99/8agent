"""Reserve and freeze a fresh, independent repeat. No old request is replayed."""
from pathlib import Path
import argparse,fcntl,json,os,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
TEMPLATE=ROOT/'06_TOOLS/EXPERIMENTS/adr_1351'
ADRROOT=ROOT/'04_EXPERIMENTS/ADR'
SOURCE=ADRROOT/'ADR-1351-integration-oneclick-provider-matrix'
BASE=ADRROOT/'ADR-1378-literal-provision-review-scope'
LATEST=ROOT/'06_TOOLS/EXPERIMENTS/integration_oneclick/latest.json'

def rewritten(text,number,slug):
 text=text.replace('ADR-1351-integration-oneclick-provider-matrix',f'ADR-{number:04d}-{slug}')
 text=text.replace('adr_1351',f'adr_{number:04d}').replace('adr1351',f'adr{number:04d}').replace('ADR1351',f'ADR{number:04d}').replace("'ADR-1351'",f"'ADR-{number:04d}'")
 baseline_number=BASE.name.split('-')[1]
 text=text.replace('ADR-1350-ontology-proposal-record-view',BASE.name).replace('Completed1350','Completed'+baseline_number).replace('completed1350','completed'+baseline_number).replace('since1350','since'+baseline_number).replace("'ADR-1350'",repr(BASE.name[:8]))
 return text

def run(cmd,**kw):
 return subprocess.run(cmd,cwd=ROOT,check=True,**kw)

def write_runner(D,number,slug):
 for original in TEMPLATE.glob('*.py'):
  if original.name=='new_experiment.py':continue
  (D/original.name).write_text(rewritten(original.read_text(),number,slug))
 live=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1369/live_public.py').read_text()
 live=live.replace('ADR-1369-explicit-exclusion-quote-selection',f'ADR-{number:04d}-{slug}').replace('adr_1369',f'adr_{number:04d}').replace('adr1369',f'adr{number:04d}').replace('ADR1369',f'ADR{number:04d}')
 live=live.replace('candidate-repaired.json','candidate-matrix.json').replace("assert case_id in read(DES/'criteria.json')['plan']['cases']\n",'').replace('total>=80','total>=1560').replace('experiment80','experiment1560')
 live=re.sub(r"'parent_adr':'ADR-[0-9]+'", "'parent_adr':'"+BASE.name[:8]+"'",live,count=1)
 marker="   put(turn/'result.json',result)"
 assert live.count(marker)==1
 live=live.replace(marker,"   result['accepted_outcome']=((value.get('assembly') or {}).get('term_agent') or {}).get('accepted_outcome') if isinstance(value,dict) else None\n"+marker)
 (D/'live_public.py').write_text(live)
 matrix=D/'matrix.py'
 code=matrix.read_text()
 marker=" return 'EXPLANATION_REVIEW_REQUIRED'"
 assert code.count(marker)==1
 code=code.replace(marker," if result.get('case_id') in ('B03-03','B03-17'):\n  for turn in turns:\n   outcome=turn.get('accepted_outcome') or {}\n   if (outcome.get('disposition'),outcome.get('answer_coverage'))!=('ANSWER','COVERED'):return 'PARTIAL_OR_UNVERIFIED'\n"+marker)
 head="def report(state='RUNNING',selected=None):"
 assert code.count(head)==1
 code=code.replace(head,head+"\n if selected is None and (ART/'provider-selection.json').exists():selected=read(ART/'provider-selection.json')['selected']")
 row_mark="for k in ('id','title','status','provider','expected'))+'</tr>'"
 assert code.count(row_mark)==1
 code=code.replace(row_mark, "for k in ('id','title','status','provider','expected'))+'<td>'+('<a href=\"'+html.escape(str(Path(r['answer_path']).relative_to(ART)),quote=True)+'\">실제 답변</a>' if r['answer_path'] else '')+'</td></tr>'")
 code=code.replace('<th>기대 결과</th></tr>', '<th>기대 결과</th><th>답변</th></tr>')
 shutil.copyfile(Path(__file__).with_name('worker_exit.py'),D/'worker_exit.py')
 code=code.replace('def execute_cell(case,provider,panel,done,total):',
                   "def execute_cell(case,provider,panel,done,total):\n if (ART/'RESOURCE_STOP.json').exists():return")
 marker=" put(d/'worker-exit.json',{'returncode':proc.returncode,'process_collected':True})"
 assert code.count(marker)==1
 code=code.replace(marker,marker+"\n from worker_exit import record_resource_exit\n record_resource_exit(ART,d,case,provider,proc.returncode,read,put)")
 code=code.replace('result=report(state,selected);', "if (ART/'RESOURCE_STOP.json').exists():state='RESOURCE_STOP'\n   result=report(state,selected);")
 matrix.write_text(code)
 archive=D/'archive_runtime.py'
 archive.write_text(archive.read_text().replace("(folder/'preflight-stop.json').exists()", "(folder/'preflight-stop.json').exists() or (folder/'resource-stop.json').exists()"))

 audit=D/'audit.py';audit.write_text(audit.read_text().replace("c['status']=='unknown'","c['status'] in ('unknown','started')").replace("out['usage']={'include':True}","out['usage']={'include':True};out['stream']=True"))
 # Regenerate native source hashes BEFORE the first freeze; known old preparation
 # failure remains in1351 and is not deliberately repeated.
 setup=D/'setup.py';text=setup.read_text();mark="for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):"
 native="""spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'native-plans.json')];builder.main();sys.argv=['prepare_queries','--check'];builder.main()
"""
 text=text.replace('ADR-1346-charter-review-retention-live/artifacts/transport',BASE.name+'/artifacts/transport')
 admission_start=text.index('for key,v in providers.items():',text.index("metadata=read(ART/'provider-endpoints.json')"))
 admission_end=text.index("put(DES/'providers.json',providers)",admission_start)
 admission="""from provider_admission import admit
providers,skipped=admit(providers,metadata)
put(DES/'provider-admission.json',{'admitted':list(providers),'skipped':skipped})
if not providers:raise RuntimeError('현재 시험 조건을 지원하는 제공자가 없습니다.')
"""
 text=text[:admission_start]+admission+text[admission_end:]
 text=text.replace('all4 structured+reasoning; current throughput/latency null.', 'admitted endpoints verified for structured output and reasoning; availability receipt retained.')
 shutil.copyfile(Path(__file__).with_name('provider_admission.py'),D/'provider_admission.py')
 guard=next(line for line in text.splitlines() if line.startswith('assert all(sha(ROOT/n)'))
 text=text.replace(guard,"""frozen_parent=ROOT/parent['code_root']
assert all(sha(frozen_parent/n)==h for n,h in parent['selected_files'].items()),'Frozen baseline hash mismatch'
actual_working={n:sha(ROOT/n) for n in parent['selected_files']}
put(DES/'baseline-source.json',{'tested_snapshot':parent['code_root'],'working_differences':[n for n,h in actual_working.items() if h!=parent['selected_files'][n]],'checkout_writes':0})""")
 text=text.replace("'working_before':parent['selected_files']", "'working_before':actual_working")
 snapshot_line=next(line for line in text.splitlines() if line.startswith('can=ac.snapshot('))
 text=text.replace(snapshot_line,snapshot_line+"""
for relative,expected in parent['selected_files'].items():
 if sha(C/relative)!=expected:shutil.copyfile(frozen_parent/relative,C/relative)
assert all(sha(C/n)==h for n,h in parent['selected_files'].items())""")
 text=text.replace("put(DES/'candidate-matrix.json',desc)", "assert desc['selected_files']==parent['selected_files'],'Runnable code differs from tested parent'\nput(DES/'candidate-matrix.json',desc)")
 assert text.count(mark)==1;text=text.replace(mark,native+mark)
 lines=text.splitlines();changed=[];routing_guard_written=False
 for line in lines:
  if line.startswith('s=s.replace('):
   if not routing_guard_written:
    changed.append("routing_needs_expansion = 'deepinfra/bf16' not in s");routing_guard_written=True
   changed.extend(['if routing_needs_expansion:',' '+line])
  else:changed.append(line)
 setup.write_text('\n'.join(changed)+'\n')
 shutil.copyfile(Path(__file__).with_name('review_public.py'),D/'review_public.py')
 review=D/'review.py'
 review.write_text("""from common import *
from review_public import review_response
grades={c['id']:c for c in read(DES/'grading-only.json')}
rows=[]
for d in sorted((ART/'public-live').glob('*')):
 if not (d/'result.json').exists():continue
 r=read(d/'result.json');turns=r.get('turns',[])
 checks=[]
 for index,turn in enumerate(turns,1):
  path=d/f'turn-{index}/response.json.gz'
  if path.is_file():
   body=read(path).get('body')
   if isinstance(body,dict):checks.append(review_response(body,grades[turn['case_id']]['anchors']))
 rows.append({'cell':d.name,'semantic_pass':False,'review_state':'MANUAL_REVIEW_REQUIRED','anchor_checks':checks,'claims':sum(t['claims'] for t in turns),'unknown':r.get('unknown',0)})
put(ART/'semantic-review.json',{'rows':rows,'all_passed':False,'judging_model_calls':0,'product_response_rewritten':False,'conclusion':'Actual source and schema checks are separate from pending semantic and UI/internal review.'})
""")
 final=D/'finalize.py';content=final.read_text()
 start=content.index("brief='");end=content.index('\nvals=',start)
 content=content[:start]+"brief='새 독립 반복의 실제 결과를 기록했다. 설명 생성/원문·권한·전송 검증과 의미·내부환경·화면 검증을 구분한다. 원문전용·UNKNOWN·미실행을 통과로 처리하지 않는다.'"+content[end:]
 content=content.replace('기존 Parasail/NearAI 공백 응답과 검토 실패; R4는 시험계획이며 기존60개 통과 결과가 없었다.',BASE.name+' 동결본으로 제공자별 독립 반복.')
 final.write_text(content)

def main():
 p=argparse.ArgumentParser();p.add_argument('--new',action='store_true');p.add_argument('--status',action='store_true');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
 if not a.new:
  if LATEST.exists():
   latest=json.loads(LATEST.read_text())
   artifacts=ROOT/latest['adr']/'artifacts'
   print('진행 화면',artifacts/'통합테스트_상태.html',flush=True)
   summary_file=artifacts/'summary.json'
   if summary_file.exists():
    summary=json.loads(summary_file.read_text())
    selected=summary.get('selected_provider')
    if (artifacts/'provider-selection.json').exists():
     selected=json.loads((artifacts/'provider-selection.json').read_text())['selected']
    print('실행 상태',summary.get('state'),'· 호출',summary.get('physical_calls',0),'회')
    if selected:
     completed=sum(row.get('provider')==selected and row.get('verdict') not in
                   ('INCOMPLETE_NO_RETRY','NOT_EXECUTED') for row in summary.get('cells',[]))
     explained=sum(row.get('provider')==selected and row.get('verdict')=='EXPLANATION_REVIEW_REQUIRED' for row in summary.get('cells',[]))
     print('공개 시험',selected,'· 실행 결과',completed,'/ 31 · 설명 응답',explained,'건 · 나머지는 결과표에서 확인')
    return 0
   print('새 실험 준비 완료')
   return 0
  report=BASE/'artifacts/run-001/result.json'
  if report.exists():
   value=json.loads(report.read_text())
   print(json.dumps({k:value.get(k) for k in ('all_passed','physical_calls','unknown','cells')},ensure_ascii=False,indent=2))
   print('실제 답변과 진단:',BASE/'artifacts/수정과_실제답변.txt')
  else:print('수정본 실제 검증 진행 중:',BASE)
  return 0
 # One active repeat across launcher invocations; existing primary run is separate.
 with (SOURCE/'artifacts/new-experiment.lock').open('a+') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('새 시험이 이미 실행 중입니다.');return 3
  if not (SOURCE/'artifacts/run-completed.json').exists():raise RuntimeError('현재 비교가 실행 중입니다. 완료 후 --new를 사용하세요.')
  manifest=json.loads((SOURCE/'실험/manifest.json').read_text())
  if manifest['results']['status']!='complete' or manifest['reservation']['status']!='completed':raise RuntimeError('현재 실험 최종 기록 검사가 아직 끝나지 않았습니다.')
  baseline=json.loads((BASE/'실험/manifest.json').read_text())
  if baseline['results']['status']!='complete' or baseline['reservation']['status']!='completed':raise RuntimeError('수정본 검증이 아직 진행 중입니다.')
  import hashlib
  pin=json.loads((BASE/'artifacts/design/candidate-repaired.json').read_text())
  frozen_parent=ROOT/pin['code_root']
  for relative,expected in pin['selected_files'].items():
   if hashlib.sha256((frozen_parent/relative).read_bytes()).hexdigest()!=expected:
    raise RuntimeError('검증한 시험본의 파일이 달라졌습니다: '+relative)

  number=max(int(x.name.split('-')[1]) for x in ADRROOT.glob('ADR-[0-9][0-9][0-9][0-9]-*'))+1
  slug='integration-oneclick-provider-repeat'
  dest=ADRROOT/f'ADR-{number:04d}-{slug}';D=ROOT/'06_TOOLS/EXPERIMENTS'/f'adr_{number:04d}'
  run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','new','--adr-root','04_EXPERIMENTS/ADR','--number',str(number),'--slug',slug,'--title','원클릭 통합테스트 제공자 독립 반복','--phase','probe','--candidate-arms','matrix','--parent-manifest',str(BASE/'실험/manifest.json'),'--parent-arm','repaired','--parent-relation','extends','--owner','user-oneclick','--session-id','user-oneclick-'+str(number),'--scope','Explicit user-invoked independent R4 provider repeat; original UNKNOWN sessions never resumed','--scope-key','integration-provider-repeat-'+str(number),'--questions','provider-screen','integration-r4'])
  D.mkdir(exist_ok=False)
  write_runner(D,number,slug)
  # Fresh public endpoint metadata; fixed provider identities remain predeclared.
  import httpx
  response=httpx.get('https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints',timeout=30);response.raise_for_status()
  (dest/'artifacts/provider-endpoints.json').write_text(json.dumps(response.json(),ensure_ascii=False,indent=2))
  log=dest/'artifacts/oneclick.log'
  with log.open('x') as out:
   run([sys.executable,str(D/'setup.py')],stdout=out,stderr=subprocess.STDOUT)
   run([sys.executable,str(D/'test_runner.py')],stdout=out,stderr=subprocess.STDOUT)
   admitted=json.loads((dest/'artifacts/design/providers.json').read_text())
   run([sys.executable,str(D/'live_public.py'),'B03-03',next(iter(admitted)),'--preflight'],stdout=out,stderr=subprocess.STDOUT)
   # New repetition has its own checks and immutable preparation receipt.
   receipt={'new_independent_repeat':True,'source_experiment':'ADR-1351','tests_passed':True,'preflight_passed':True,'model_calls_in_preparation':0}
   (dest/'artifacts/technical-verification.json').write_text(json.dumps(receipt,indent=2))
   run([sys.executable,str(D/'freeze.py')],stdout=out,stderr=subprocess.STDOUT)
  print('새 실험:',dest,'\n진행 화면:',dest/'artifacts/통합테스트_상태.html',flush=True)
  LATEST.write_text(json.dumps({'adr':str(dest.relative_to(ROOT)),'runner':str((D/'matrix.py').relative_to(ROOT))},ensure_ascii=False,indent=2)+'\n')
  if a.prepare_only:return 0
  code=subprocess.call([sys.executable,str(D/'matrix.py')],cwd=ROOT)
  if (dest/'artifacts/run-completed.json').exists():
   with log.open('a') as out:
    run([sys.executable,str(D/'review.py')],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,str(D/'archive_runtime.py')],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,str(D/'finalize.py')],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(dest)],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(dest),'--status','completed','--note','Independent user-invoked run completed; all outcomes preserved'],stdout=out,stderr=subprocess.STDOUT)
   from artifact_index import seal
   print('보관 파일 검증',seal(ROOT,dest),'개',flush=True)
   run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(dest),'--final'])
   subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','graph','--adr-root',str(ADRROOT)],cwd=ROOT,capture_output=True)
  return code
if __name__=='__main__':raise SystemExit(main())
