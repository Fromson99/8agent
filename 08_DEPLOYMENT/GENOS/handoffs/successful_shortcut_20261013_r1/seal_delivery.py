import ast,base64,gzip,json,subprocess,zipfile,zlib
import xml.etree.ElementTree as ET
import build_delivery as b
O,R,N=b.OUT,b.ROOT,b.NAME

def passed(path):
 cases=list(ET.parse(path).iter('testcase'));assert cases and not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped')),path
 return len(cases)
assert not (O/(N+'.zip')).exists()
assert passed(O/'INSTALL_TESTS.xml')==8
contracts={p.name:passed(p) for p in O.glob('CONTRACTS_*.xml')};assert len(contracts)==2 and sum(contracts.values())==278
rows=[]
for p in sorted(O.glob('TEST_*.json.gz')):
 commands=json.loads(gzip.decompress(p.read_bytes()));assert sum('GENOS_RELEASE_GATE PASS' in x['stdout'] for x in commands)==1
 assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in x['stdout'] for x in commands)==2
 assert sum(bool(x['returncode']) for x in commands)==2
 rows.append({'file':p.name,'commands':len(commands),'sha256':b.sha(p.read_bytes())})
assert len(rows)==6
spec=json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()));run=(O/(N+'_RUN.txt')).read_text()
tree=ast.parse(run[run.index('import base64,hashlib,json,os,sys,types,zlib\n'):run.rindex('AD_REQUEST_LOGS_PY')]);bundle=json.loads(zlib.decompress(base64.b64decode(tree.body[1].value.args[0].args[0].value)))
assert bundle['spec']==spec and base64.b64decode(bundle['code'])==(O/'apply_patch.py').read_bytes()
A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication';main=json.loads((A/'artifacts/main-service-smoke.json').read_text());active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());assert active==main['pointer']
validation={'status':'PASS','environment':'WSL synthetic, no GENOS connection','matrix_cases':36,'candidate_contracts':169,'working_contracts':169,'installed_contracts':278,'installation_states':6,'service_boots':12,'same_committed_checkout_generation_gates':6,'known_inventories':len(spec['signatures']),'expected_tamper_rejections':12,'real_model_calls':0,'evidence':rows,'contracts':contracts,'selected_main':active,'main_smoke':main,'limitations':['Final publication success is not legal semantic correctness.','Legacy records without matching journal and final answer remain unconfirmed.','GENOS field deployment and UI not verified.','Tested legacy field bases do not contain bounded wiki recall; its22 contracts run against MAIN but do not apply to these field bases. Existing optional features are preserved.','Pre-existing unrelated no-socket display expectation failure is unchanged and outside these passing suites.']}
(O/'VALIDATION.json').write_bytes(b.encoded(validation))
(O/'VALIDATION_SUMMARY.txt').write_text('정상 완료 shortcut / 위키 / AD 페이지 검증\n\n상태36조합 전부 일치 (기준13/36 → 후보36/36)\n후보169계약 + 통합 작업169계약\n실제 현장형 설치본 계약278개\n설치6상태: 적용·반복·변조 거부·원복\n서비스 초기화12회 / 동일 committed checkout + 모의 generation 게이트6회\n알려진 선행 코드 inventory '+str(len(spec['signatures']))+'종\n실제 외부/GENOS 모델 호출0회\n\n로컬 MAIN59 successful-shortcut-20261013-r1 반영 완료\n선택301서빙파일·HEALTH/RAG_SEARCH200·선택 AD 목록 확인\n법률 의미 정답 인증과 GENOS 실제 배포/화면 성공은 미확인\nAD_REQUEST_LOGS R2 선적용 필요. 기존 ~/DEV에 적용.\n')
(O/'HANDOFF.json').write_bytes(b.encoded({'version':N,'predecessor':'GENOS_AD_REQUEST_LOGS_20261013_R2','field_code_root':'~/DEV','field_git_commit':None,'field_generation':None,'field_generation_manifest_sha256':None,'field_code_serving_revision':None,'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','rebuild_required':False,'workflow_editor_change_required':False,'local_main':active,'rollback':'Hash guarded undo to AD_REQUEST_LOGS R2; additive ledger receipts preserved'}))
source=json.loads((O/'SOURCE_BINDING.json').read_text());source.update(local_active_release_changed=True,local_active_release='successful-shortcut-20261013-r1',local_active_pointer_generation=59,field_compatibility_note='Private-only old repositories receive success/currentness guards and their missing private scope helper; common catalogue visibility is not enabled.');(O/'SOURCE_BINDING.json').write_bytes(b.encoded(source))
files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SOURCE_BINDING.json','WORKING_INTEGRATION.json','HANDOFF.json']
for n,h in json.loads((O/'WORKING_INTEGRATION.json').read_text())['files'].items():
 assert b.sha((R/n).read_bytes())==h
 p=O/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/n).read_bytes());files.append(str(p.relative_to(O)))
manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,'deployment_zip':'apply creates APPLIED_CODE.zip from the actual checkout','files':[{'path':n,'sha256':b.sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
(O/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json');(O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
with zipfile.ZipFile(O/(N+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in files:
  assert b.Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'};z.write(O/n,n)
with zipfile.ZipFile(O/(N+'.zip')) as z:
 assert z.testzip() is None and z.read(N+'_RUN.txt')==(O/(N+'_RUN.txt')).read_bytes()
 assert not any(b.Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
 for row in manifest['files']:assert b.sha(z.read(row['path']))==row['sha256']
subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt'];(O/'SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments));attachments.append('SHA256SUMS.txt')
(O/'EMAIL_PREFLIGHT.json').write_bytes(b.encoded({'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS 수정 코드] 정상 완료 shortcut·위키 필터 / AD 페이지 이동 — 로컬 MAIN59 반영','attachments':[{'filename':n,'bytes':(O/n).stat().st_size,'sha256':b.sha((O/n).read_bytes())} for n in attachments]}))
print(json.dumps({'attachments':5,'zip_bytes':(O/(N+'.zip')).stat().st_size,'installed_contracts':278,'main_generation':59}))
