"""Seal the verified standalone-SSE overlay and its exact field instructions."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261008-svg-judgment-standalone-r1'
NAME='GENOS_RAG_PROGRESS_GRAPH_20261008_R5'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda obj:(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()

def main():
 archive=OUT/(NAME+'.zip');assert not archive.exists(),'Preserve sealed delivery'
 hand=json.loads((OUT/'HANDOFF.json').read_bytes());validation=json.loads((OUT/'VALIDATION.json').read_bytes())
 binding=json.loads((OUT/'SOURCE_BINDING.json').read_bytes())
 assert len(binding['variants'])==hand['known_code_signatures']==165
 assert all(row['static_hash_and_contracts_passed'] for row in binding['variants'])
 assert all(row['passed'] for row in validation['variants'])
 assert validation['txt_commands']==10*len(validation['variants'])
 assert len(validation['contracts'])==9
 assert '6 passed' in (AUDIT/'gate-budget-sealed-code.txt').read_text()
 assert '77 passed' in (AUDIT/'contracts-last.txt').read_text()
 assert json.loads((AUDIT/'local-server-receipt.json').read_bytes())['unavailable_generation_probe_success']
 for name,pin in hand['source_sha256'].items():
  raw=(OUT/'payload'/name).read_bytes();assert sha(raw)==pin,name
  if name not in {'genos_diagnostics.py','genos_log_runner.py'}:assert sha((ROOT/name).read_bytes())==pin,name
  if name.endswith('.py'):ast.parse(raw,feature_version=(3,10))
 pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';assert sha(pointer.read_bytes())==hand['local_active_pointer_sha256']
 run=OUT/(NAME+'_RUN.txt');workflow=OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')
 assert sha(run.read_bytes())==hand['run_txt_sha256']==validation['run_txt_sha256']
 assert sha(workflow.read_bytes())==hand['workflow_txt_sha256']
 assert '.venv/bin/python' not in run.read_text()
 ast.parse(workflow.read_text(),feature_version=(3,10))
 for p in (run,OUT/'START_SSE.txt'):subprocess.run(['bash','-n',str(p)],check=True)
 summary=('GENOS 별도 SSE / 현재 판단 / SVG R10 적용 R5 검증\n\n'
  '작업 표시·SSE·로그 계약: 77개 통과; 새 모델 호출 0\n'
  '기존 코드 지문 165종: 코드/engine/schema hash 정적 검증\n'
  f"실제 첨부 RUN: {len(validation['variants'])}개 대표 설치 상태 / {validation['txt_commands']}개 check/apply/재실행/verify/undo/변조 거부 명령 통과\n"
  '설치 코드 9개 계열에서 JSON/SSE/분리 표시/현재 판단 계약 통과\n'
  '동일 committed checkout의 모의 generation gate 및 CM/예산/오류 보존: 6개 통과\n'
  '실제 START_SSE TXT로 WSL 로컬 HTTP 서버 시작/health/SSE_CHECK 확인; 모델/원문 초기화 없음\n'
  '별도 stream_app:app 실행; SVG R10 / 현재 판단 진행 R2 / SSE 로그 R1\n'
  '모의 미리보기: 실제 GENOS 화면·법령 판단 결과와 별도\n'
  '로컬 MAIN45 포인터 유지; GENOS 적용/push/리비전/실제 화면 미확인; 메일 미발송\n')
 (OUT/'VALIDATION_SUMMARY.txt').write_text(summary)
 shutil.copyfile(AUDIT/'수정후-모의-근거관계.png',OUT/(NAME+'_EXAMPLE.png'))
 files=['apply_display.py','PATCH_SPEC.json.gz',NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt',
  'START_SSE.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SOURCE_BINDING.json',NAME+'_EXAMPLE.png']
 files += [p.relative_to(OUT).as_posix() for p in sorted((OUT/'payload').rglob('*')) if p.is_file()]
 manifest={'schema_version':'genos-transfer-overlay-v1','id':NAME,'transfer_only':True,
  'deployment_zip':'apply generates APPLIED_CODE.zip from actual DEV for gate',
  'files':[{'path':n,'sha256':sha((OUT/n).read_bytes()),'bytes':(OUT/n).stat().st_size} for n in files]}
 (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest));files.append('CODE_MANIFEST.json')
 (OUT/'PACKAGE_SHA256SUMS.txt').write_text(''.join(sha((OUT/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for name in files:z.write(OUT/name,name)
 hand.update(code_zip_sha256=sha(archive.read_bytes()),code_zip_bytes=archive.stat().st_size,
  validation={'working_contracts':77,'field_inventory_signatures':165,'tested_installation_states':len(validation['variants']),
    'txt_commands':validation['txt_commands'],'families':len(validation['contracts']),'mock_generation_gate_checks':6,
    'local_standalone_start_and_probe':'PASS','model_calls':0},transfer_only=True)
 (OUT/'HANDOFF.json').write_bytes(encoded(hand))
 (OUT/'SHA256SUMS.txt').write_text(''.join(sha((OUT/n).read_bytes())+'  '+n+'\n' for n in [archive.name,run.name,workflow.name,'START_SSE.txt','GUIDE_UTF8.txt']))
 with zipfile.ZipFile(archive) as z:
  assert all(sha(z.read(row['path']))==row['sha256'] for row in manifest['files'])
 print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,'sha256':hand['code_zip_sha256'],**hand['validation']},ensure_ascii=False))

if __name__=='__main__':main()
