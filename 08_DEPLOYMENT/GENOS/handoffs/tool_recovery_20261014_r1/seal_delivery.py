"""Seal only verified installed bytes, retaining failed fixture/build history."""
import ast,base64,gzip,hashlib,importlib.metadata,json,re,subprocess,sys,tempfile,xml.etree.ElementTree as E,zipfile,zlib
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_TOOL_RECOVERY_20261014_R1';A=R/'04_EXPERIMENTS/ADR/ADR-0779-tool-recovery-main'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode();read=lambda p:json.loads(p.read_bytes())
def stats(p):
 cases=list(E.parse(p).iter('testcase'))
 return {'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),'errors':sum(c.find('error') is not None for c in cases),'skipped':sum(c.find('skipped') is not None for c in cases)}
def main():
 assert not (O/(N+'.zip')).exists()
 source=read(O/'SOURCE_BINDING.json');local=read(A/'artifacts/run-001/result.json');service=read(A/'artifacts/main-service-smoke.json')
 for n,h in read(O/'TESTED_DELIVERY_BINDING.json').items():assert sha((O/n).read_bytes())==h,n
 assert local['strict_success'] and service['status']=='PASS'
 assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==service['pointer']
 for n,h in source['working_source_files'].items():assert sha((R/n).read_bytes())==h,n
 for n,h in source['source_files'].items():assert sha((O/'payload'/n).read_bytes())==h,n
 for n,variants in source['field_variants'].items():
  if not any(n.endswith('/'+x+'.py') for x in ('shortcut_cases','investigation_diagnostics','readable_log','request_entry')):assert set(variants.values())=={source['source_files'][n]},n
 text=(O/(N+'_RUN.txt')).read_text();packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text).group(1)
 bundle=json.loads(zlib.decompress(base64.b64decode(packed)));assert base64.b64decode(bundle['code'])==(O/'apply_patch.py').read_bytes()
 assert bundle['spec']==json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()))
 delivery=stats(O/'DELIVERY_TESTS.xml');assert delivery==dict(tests=2,failures=0,errors=0,skipped=0),delivery
 installed={p.name:stats(p) for p in sorted(O.glob('INSTALLED*.xml'))};assert len(installed)==2
 assert all(v['tests']==549 and v['failures']==1 and v['errors']==v['skipped']==0 for v in installed.values()),installed
 for name in installed:
  kind=name.removeprefix('INSTALLED_').removesuffix('.xml')
  baseline=read(O/('LEGACY_DISPLAY_BASELINE_'+kind+'.json'))
  failures=[c for c in E.parse(O/name).iter('testcase') if c.find('failure') is not None]
  assert failures[0].get('name')==baseline['test']['name'] and failures[0].find('failure').get('message')==baseline['message']
  assert "assert 'REFERENCE_TARGET_UNRESOLVED' not in rendered" in failures[0].find('failure').text
 counts={'commands':0,'generation_gates':0,'tls_boots':0,'undo':0,'tamper_rejections':0};roots=[]
 for p in sorted(O.glob('TEST_*.json.gz')):
  rows=json.loads(gzip.decompress(p.read_bytes()));assert rows[-1]['returncode']==0 and rows[-1]['argv'][-1]=='check';counts['commands']+=len(rows)
  for row in rows:
   for key,phrase in [('generation_gates','GENOS_RELEASE_GATE PASS'),('tls_boots','SERVICE_TLS_BOOTSTRAP PASS'),('undo','CODE_RESTORED;')]:counts[key]+=phrase in row['stdout']
   if row['returncode']!=0:
    if 'installed_runner.py' in str(row['argv']):assert row['returncode']==1
    else:assert row['argv'][0]=='bash' and row['argv'][2] in ('verify','undo');counts['tamper_rejections']+=1
   if 'installed_runner.py' in str(row['argv']):assert 'INSTALLED_RUNTIME_IMPORTS PASS; modules=' in row['stdout'];roots.append(row['argv'][2])
 assert counts==dict(commands=32,generation_gates=2,tls_boots=2,undo=2,tamper_rejections=4),counts
 validation={'revision':N,'local_main':service,'qualification':local,'installed_contracts':installed,'installed_total':sum(v['tests']-v['failures'] for v in installed.values()),'installed_known_display_failures':2,'legacy_display_baselines':{kind:read(O/('LEGACY_DISPLAY_BASELINE_'+kind+'.json')) for kind in ('query_latency_20261007_r3','query_latency_20261007_r4')},'delivery_tests':delivery,'installer_checks':counts,'known_predecessors':source['known_predecessors'],'changed_product_files':len(source['source_files']),'source_binding':source,'verified_installed_roots':roots,'generation_type':'synthetic fixture; unchanged through install/undo','model_inference_calls':0,'real_genos_or_external_network_calls':0,'tls_test':'Loopback synthetic model discovery only','sys_executable':sys.executable,'python':sys.version.split()[0],'packages':{n:importlib.metadata.version(n) for n in ('jsonschema','requests','fastapi','pytest')},'field_checkout':None,'field_commit':None,'field_generation_path':None,'field_generation_manifest_sha256':None,'field_serving_revision':None,'field_workflow_test':None,'field_status':'NOT_VERIFIED','limits':local['limitations']+['Eight historical graph errors unchanged; new0','Existing wiki recall disabled in field; not enabled or newly shipped','Unknown code inventories are rejected']}
 (O/'VALIDATION.json').write_bytes(enc(validation))
 (O/'VALIDATION_SUMMARY.txt').write_text(f'''도구 실패 복구 누적 R1 검증 — 2026-10-14
로컬 MAIN63 / tool-recovery-20261014-r1 반영 및 실제 service.service 확인 완료.
작업/검증 후보/선택 릴리스306파일 동일; 원문·모델·검색 설정 유지.
사전 동결 공통 정책5994조합 통과. 기존 회귀842통과·동일4기존실패. 새 회귀0(검사 범위).
37개 구현 범위 실패 시나리오 통과, 후속12시나리오 미실행. 개별 도구×모든 실패 조합 완전성은 아님.
ADR0779 final validation 통과. 전체 graph는 과거8오류 그대로·추가0.
현장 설치 모의2구성: 계약/API {validation['installed_total']}개 통과, 각 구성에서 기존 표시 정책 기대 차이1실패(패치 전 동일 재현), 새 회귀/skip0.
실제 실행 TXT32명령: check/apply/reapply/verify/undo 및 변조거부4회.
실제 service.service localhost TLS부팅2회, 같은 committed checkout의 generation gate2회 통과.
지원 코드 inventory {source['known_predecessors']}개. 제품파일21개와 기존 코드 pin만 갱신.
현장 숏컷/진단/로그 변형은 보존하며 wiki recall을 켜지 않음.
모델 추론0회·GENOS접속0회. 현장 commit/push/리비전/워크플로우 재질의는 미확인.
사진의 구조 부모 읽기 결함은 코드/합성API로 확인했으나 길이 종료 자체·모든 판단 성공을 보장하지 않음.
''')
 for p in O.glob('*.xml'):p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
 files=['apply_patch.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz','TESTED_DELIVERY_BINDING.json','VALIDATION.json','VALIDATION_SUMMARY.txt','GUIDE_UTF8.txt','FIX_REPORT_UTF8.txt',N+'_RUN.txt']
 files += [str(p.relative_to(O)) for folder in ('payload','preimage') for p in (O/folder).rglob('*') if p.is_file()]
 files += [p.name for p in O.glob('INSTALLED*.xml.gz')]+['DELIVERY_TESTS.xml.gz']
 for kind in ('query_latency_20261007_r3','query_latency_20261007_r4'):
  files.append('LEGACY_DISPLAY_BASELINE_'+kind+'.json')
  files.append('failures/legacy-display-baseline-'+kind+'.xml')
  raw=O/('failures/legacy-display-baseline-'+kind+'.xml');name='legacy-display-baseline-'+kind+'.xml.gz'
  (O/name).write_bytes(gzip.compress(raw.read_bytes(),mtime=0));files.append(name)
 manifest={'schema_version':'genos-partial-patch-v1','revision':N,'prerequisite':source['prerequisite'],'gate_archive':'apply-generated BACKUP/APPLIED_CODE.zip','files':[]}
 for n in sorted(files):
  p=O/n;raw=p.read_bytes();assert p.suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
  if p.suffix=='.py':ast.parse(raw,feature_version=(3,10))
  manifest['files'].append({'path':n,'sha256':sha(raw),'bytes':len(raw)})
 (O/'CODE_MANIFEST.json').write_bytes(enc(manifest));archive=O/(N+'.zip')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in sorted(files)+['CODE_MANIFEST.json']:z.write(O/n,n)
 with tempfile.TemporaryDirectory(prefix='tool-recovery-unpack-') as td:
  target=Path(td)
  with zipfile.ZipFile(archive) as z:
   assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
   assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in z.namelist());z.extractall(target)
  for row in manifest['files']:
   raw=(target/row['path']).read_bytes();assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
  assert (target/(N+'_RUN.txt')).read_bytes()==(O/(N+'_RUN.txt')).read_bytes();subprocess.run(['bash','-n',str(target/(N+'_RUN.txt'))],check=True)
 attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','FIX_REPORT_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json']
 (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
 sealed={'revision':N,'sha256':sha(archive.read_bytes()),'bytes':archive.stat().st_size,'members':len(files)+1,'no_javascript':True,'hash_verified_members':len(files),'standalone_run_matches':True,'bash_syntax':'PASS','field_status':'NOT_VERIFIED'}
 (O/'SEALED_UNPACK_CHECK.json').write_bytes(enc(sealed));print(json.dumps(sealed))
if __name__=='__main__':main()
