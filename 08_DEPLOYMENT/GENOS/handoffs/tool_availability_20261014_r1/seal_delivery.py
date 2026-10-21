"""Seal validated payload and runnable TXT without overwriting earlier deliveries."""
import ast,base64,gzip,hashlib,importlib.metadata,json,re,subprocess,sys,tempfile,xml.etree.ElementTree as ET,zipfile,zlib
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_TOOL_AVAILABILITY_20261014_R1';A=R/'09_ARTIFACTS/AUDITS/20261014-tool-availability'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda obj:(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
def read(p):return json.loads(p.read_bytes())
def stats(p):
 s=ET.parse(p).getroot().find('testsuite');return {k:int(s.attrib[k]) for k in ('tests','failures','errors','skipped')}
def main():
 assert not (O/(N+'.zip')).exists(),'Preserve sealed delivery'
 source=read(O/'SOURCE_BINDING.json');reg=read(A/'regression-final-result.json')
 for n,h in read(O/'TESTED_DELIVERY_BINDING.json').items():assert sha((O/n).read_bytes())==h,n
 assert reg['exit_code']==0 and reg['product_unchanged'] and reg['test_files_unchanged']
 assert sha((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())==reg['active_pointer_sha256']
 for n,h in source['working_source_files'].items():assert sha((R/n).read_bytes())==h,n
 for n,h in source['source_files'].items():assert sha((O/'payload'/n).read_bytes())==h,n
 for n,h in reg['product_sha256'].items():assert source['source_files'][n]==h
 for n,h in reg['test_sha256'].items():assert sha((R/n).read_bytes())==h,n
 assert source['known_predecessors']==660
 text=(O/(N+'_RUN.txt')).read_text();packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text).group(1)
 bundle=json.loads(zlib.decompress(base64.b64decode(packed)))
 assert base64.b64decode(bundle['code'])==(O/'apply_patch.py').read_bytes()
 assert bundle['spec']==json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()))
 delivery=stats(O/'DELIVERY_TESTS.xml');assert delivery==dict(tests=2,failures=0,errors=0,skipped=0)
 installed={p.name:stats(p) for p in sorted(O.glob('INSTALLED*.xml'))}
 assert len(installed)==2 and all(v['tests']>180 and not any(v[k] for k in ('failures','errors','skipped')) for v in installed.values()),installed
 counts={'commands':0,'generation_gates':0,'tls_boots':0,'undo':0,'tamper_rejections':0};roots=[]
 for p in sorted(O.glob('TEST_*.json.gz')):
  rows=json.loads(gzip.decompress(p.read_bytes()));assert rows[-1]['returncode']==0 and rows[-1]['argv'][-1]=='check';counts['commands']+=len(rows)
  for row in rows:
   for key,phrase in [('generation_gates','GENOS_RELEASE_GATE PASS'),('tls_boots','SERVICE_TLS_BOOTSTRAP PASS'),('undo','CODE_RESTORED;')]:counts[key]+=phrase in row['stdout']
   if row['returncode']!=0:
    assert row['argv'][0]=='bash' and row['argv'][2] in ('verify','undo');counts['tamper_rejections']+=1
   if 'installed_runner.py' in str(row['argv']):assert 'INSTALLED_RUNTIME_IMPORTS PASS; modules=' in row['stdout'];roots.append(row['argv'][2])
 assert counts==dict(commands=32,generation_gates=2,tls_boots=2,undo=2,tamper_rejections=4),counts
 working=stats(A/'regression-final.xml');assert working['tests']>1000 and working['failures']==working['errors']==0
 assert stats(A/'baseline-menu.xml')['failures']==3 and stats(A/'baseline-legacy.xml')['failures']==7
 validation={'revision':N,'working_regressions':working,'preexisting_deselected':reg['preexisting_failures_excluded'],'baseline_proof':reg['baseline_proof'],'installed_contracts':installed,'installed_total':sum(v['tests'] for v in installed.values()),'delivery_tests':delivery,'installer_checks':counts,'known_predecessors':660,'changed_product_files':11,'working_fix_files':10,'source_binding':source,'verified_installed_roots':roots,'generation_type':'synthetic fixture; unchanged through install/undo','active_main':{'generation':62,'release':'schema-recovery-20261014-r1','pointer_sha256':reg['active_pointer_sha256'],'changed':False},'model_inference_calls':0,'real_genos_or_external_network_calls':0,'tls_test':'Local loopback synthetic model discovery only','sys_executable':sys.executable,'python':sys.version.split()[0],'packages':{n:importlib.metadata.version(n) for n in ('jsonschema','requests','fastapi','pytest')},'field_status':'NOT_VERIFIED','field_checkout':None,'field_commit':None,'field_generation_path':None,'field_generation_manifest_sha256':None,'field_serving_revision':None,'field_workflow_test':None,'limitations':['No real internal model performance or quality measurement','Four preexisting legacy structural-transport failures deselected with baseline reproduction; resolver mock/type failures separately preserved','Unknown field inventories are rejected','Local MAIN promotion and GENOS deployment remain separate','422 team/scope problem intentionally excluded']}
 (O/'VALIDATION.json').write_bytes(enc(validation))
 (O/'VALIDATION_SUMMARY.txt').write_text(f'''GENOS 상황별 도구 제한·구조 부모 원문 읽기 R1 검증 — 2026-10-14
작업 코드: {working['tests']-working['skipped']} passed / {working['skipped']} skipped / 0 failed.
기존 실패 4건 명시 제외: 수정 전 구조 API mock에서도 같은 실패를 재현했고 로그/XML 보존.
추가로 기존 resolver mock/예외 타입 실패 3건도 수정 전 재현. 신규 회귀와 구분.
설치된 2개 현장 코드 조합 계약/API {sum(v['tests'] for v in installed.values())}개 통과, 실패/면제 0.
기존 Git checkout에서 TXT check/apply/reapply/verify/undo, 변조 거부 4회, 총 32명령 검증.
실제 service.service localhost TLS 부팅 2회 및 동일 committed checkout generation gate 2회 통과.
작업 코드 9개 수정/신규 파일은 설치 코드와 동일. 숏컷의 종료 guard도 동일하며 나머지 현장 routing/hint 코드를 보존.
현장 진단 소비자의 traceback 설정도 보존.
스키마 R1 / 의존 복구 R1의 알려진 660개 inventory만 지원. 원문 데이터/기존 환경 설정 보존.
실제 LLM 호출 0. 현장에 접근하지 않았으며 내부 모델 품질·현장 배포 성공은 미확인.
로컬 MAIN62 포인터/선택 릴리스 변경 없음. 422 팀/범위 오류 수정 없음.
''')
 (O/'FIX_REPORT_UTF8.txt').write_bytes((A/'AUDIT_UTF8.txt').read_bytes())
 (O/'WORKING_REGRESSION_RECEIPT.json').write_bytes((A/'regression-final-result.json').read_bytes())
 for p in O.glob('*.xml'):p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
 files=['apply_patch.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz','TESTED_DELIVERY_BINDING.json','VALIDATION.json','VALIDATION_SUMMARY.txt','GUIDE_UTF8.txt','FIX_REPORT_UTF8.txt','WORKING_REGRESSION_RECEIPT.json',N+'_RUN.txt']
 files += [str(p.relative_to(O)) for folder in ('payload','preimage') for p in (O/folder).rglob('*') if p.is_file()]
 files += [p.name for p in O.glob('INSTALLED*.xml.gz')]+['DELIVERY_TESTS.xml.gz']
 for n in ('baseline-menu.xml','baseline-legacy.xml'):
  (O/(n+'.gz')).write_bytes(gzip.compress((A/n).read_bytes(),mtime=0));files.append(n+'.gz')
 manifest={'schema_version':'genos-partial-patch-v1','revision':N,'prerequisite':source['prerequisite'],'gate_archive':'apply-generated BACKUP/APPLIED_CODE.zip','files':[]}
 for n in sorted(files):
  p=O/n;raw=p.read_bytes();assert p.suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
  if p.suffix=='.py':ast.parse(raw,feature_version=(3,10))
  manifest['files'].append({'path':n,'sha256':sha(raw),'bytes':len(raw)})
 (O/'CODE_MANIFEST.json').write_bytes(enc(manifest));archive=O/(N+'.zip')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in sorted(files)+['CODE_MANIFEST.json']:z.write(O/n,n)
 with tempfile.TemporaryDirectory(prefix='tool-availability-unpack-') as td:
  target=Path(td)
  with zipfile.ZipFile(archive) as z:
   assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
   assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in z.namelist());z.extractall(target)
  for row in manifest['files']:
   raw=(target/row['path']).read_bytes();assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
  assert (target/(N+'_RUN.txt')).read_bytes()==(O/(N+'_RUN.txt')).read_bytes()
  subprocess.run(['bash','-n',str(target/(N+'_RUN.txt'))],check=True)
 attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json']
 (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
 sealed={'revision':N,'sha256':sha(archive.read_bytes()),'bytes':archive.stat().st_size,'members':len(files)+1,'no_javascript':True,'hash_verified_members':len(files),'standalone_run_matches':True,'bash_syntax':'PASS','field_status':'NOT_VERIFIED'}
 (O/'SEALED_UNPACK_CHECK.json').write_bytes(enc(sealed));print(json.dumps(sealed))
if __name__=='__main__':main()
