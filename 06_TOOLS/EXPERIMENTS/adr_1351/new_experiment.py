"""Reserve and freeze a fresh, independent repeat. No old request is replayed."""
from pathlib import Path
import argparse,fcntl,json,os,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
TEMPLATE=Path(__file__).resolve().parent
ADRROOT=ROOT/'04_EXPERIMENTS/ADR'
SOURCE=ADRROOT/'ADR-1351-integration-oneclick-provider-matrix'

def rewritten(text,number,slug):
 text=text.replace('ADR-1351-integration-oneclick-provider-matrix',f'ADR-{number:04d}-{slug}')
 text=text.replace('adr_1351',f'adr_{number:04d}').replace('adr1351',f'adr{number:04d}').replace('ADR1351',f'ADR{number:04d}').replace("'ADR-1351'",f"'ADR-{number:04d}'")
 return text

def run(cmd,**kw):
 return subprocess.run(cmd,cwd=ROOT,check=True,**kw)

def main():
 p=argparse.ArgumentParser();p.add_argument('--new',action='store_true');p.add_argument('--status',action='store_true');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
 if not a.new:
  return subprocess.call([sys.executable,str(TEMPLATE/'matrix.py'),*(['--status'] if a.status else [])],cwd=ROOT)
 # One active repeat across launcher invocations; existing primary run is separate.
 with (SOURCE/'artifacts/new-experiment.lock').open('a+') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('새 시험이 이미 실행 중입니다.');return 3
  if not (SOURCE/'artifacts/run-completed.json').exists():raise RuntimeError('현재 비교가 실행 중입니다. 완료 후 --new를 사용하세요.')
  manifest=json.loads((SOURCE/'실험/manifest.json').read_text())
  if manifest['results']['status']!='complete' or manifest['reservation']['status']!='completed':raise RuntimeError('현재 실험 최종 기록 검사가 아직 끝나지 않았습니다.')
  number=max(int(x.name.split('-')[1]) for x in ADRROOT.glob('ADR-[0-9][0-9][0-9][0-9]-*'))+1
  slug='integration-oneclick-provider-repeat'
  dest=ADRROOT/f'ADR-{number:04d}-{slug}';D=ROOT/'06_TOOLS/EXPERIMENTS'/f'adr_{number:04d}'
  run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','new','--adr-root','04_EXPERIMENTS/ADR','--number',str(number),'--slug',slug,'--title','원클릭 통합테스트 제공자 독립 반복','--phase','probe','--candidate-arms','matrix','--parent-manifest',str(SOURCE/'실험/manifest.json'),'--parent-arm','matrix','--parent-relation','retests','--owner','user-oneclick','--session-id','user-oneclick-'+str(number),'--scope','Explicit user-invoked independent R4 provider repeat; original UNKNOWN sessions never resumed','--scope-key','integration-provider-repeat-'+str(number),'--questions','provider-screen','integration-r4'])
  D.mkdir(exist_ok=False)
  for original in TEMPLATE.glob('*.py'):
   if original.name=='new_experiment.py':continue
   (D/original.name).write_text(rewritten(original.read_text(),number,slug))
  # Regenerate native source hashes BEFORE the first freeze; known old preparation
  # failure remains in1351 and is not deliberately repeated.
  setup=D/'setup.py';text=setup.read_text();mark="for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):"
  native="""spec=importlib.util.spec_from_file_location('prepare_queries',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
original=builder.source_queries;builder.ROOT=C;builder.source_queries=lambda:original(C)
sys.argv=['prepare_queries','--report',str(DES/'native-plans.json')];builder.main();sys.argv=['prepare_queries','--check'];builder.main()
"""
  assert text.count(mark)==1;text=text.replace(mark,native+mark);setup.write_text(text)
  # Fresh public endpoint metadata; fixed provider identities remain predeclared.
  import httpx
  response=httpx.get('https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints',timeout=30);response.raise_for_status()
  (dest/'artifacts/provider-endpoints.json').write_text(json.dumps(response.json(),ensure_ascii=False,indent=2))
  log=dest/'artifacts/oneclick.log'
  with log.open('x') as out:
   run([sys.executable,str(setup)],stdout=out,stderr=subprocess.STDOUT)
   run([sys.executable,str(D/'test_runner.py')],stdout=out,stderr=subprocess.STDOUT)
   run([sys.executable,str(D/'live_public.py'),'B03-03','deepinfra','--preflight'],stdout=out,stderr=subprocess.STDOUT)
   # New repetition has its own checks and immutable preparation receipt.
   receipt={'new_independent_repeat':True,'source_experiment':'ADR-1351','tests_passed':True,'preflight_passed':True,'model_calls_in_preparation':0}
   (dest/'artifacts/technical-verification.json').write_text(json.dumps(receipt,indent=2))
   run([sys.executable,str(D/'freeze.py')],stdout=out,stderr=subprocess.STDOUT)
  print('새 실험:',dest,'\n진행 화면:',dest/'artifacts/통합테스트_상태.html',flush=True)
  if a.prepare_only:return 0
  code=subprocess.call([sys.executable,str(D/'matrix.py')],cwd=ROOT)
  if (dest/'artifacts/run-completed.json').exists():
   with log.open('a') as out:
    run([sys.executable,str(D/'review.py')],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,str(D/'archive_runtime.py')],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,str(D/'finalize.py')],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(dest)],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(dest),'--status','completed','--note','Independent user-invoked run completed; all outcomes preserved'],stdout=out,stderr=subprocess.STDOUT)
    run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(dest),'--final'],stdout=out,stderr=subprocess.STDOUT)
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','graph','--adr-root',str(ADRROOT)],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
  return code
if __name__=='__main__':raise SystemExit(main())
