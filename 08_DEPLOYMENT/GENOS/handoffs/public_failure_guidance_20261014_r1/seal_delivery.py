import ast,base64,gzip,hashlib,json,subprocess,zipfile,xml.etree.ElementTree as E
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1';A=R/'04_EXPERIMENTS/ADR/ADR-0775-public-failure-main'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode();read=lambda p:json.loads(p.read_bytes())
assert not (O/(N+'.zip')).exists(),'preserve sealed delivery'
source=read(O/'SOURCE_BINDING.json');active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');selected=read(R/active['manifest_path']);smoke=read(A/'artifacts/main-service-smoke.json');result=read(A/'artifacts/run-001/result.json')
assert active['generation']==61 and smoke['status']=='PASS' and result['strict_success']
assert all(sha((R/n).read_bytes())==h==selected['files'][n]==sha((R/selected['code_root']/n).read_bytes()) for n,h in source['source_files'].items())
def passed(path):
 cases=list(E.parse(path).iter('testcase'));assert cases and all(t.find('failure') is None and t.find('error') is None and t.find('skipped') is None for t in cases),path;return len(cases)
assert passed(O/'EDITOR.xml')==15
install_cases=[t for t in E.parse(O/'INSTALL.xml').iter('testcase') if t.get('name','').startswith('test_real_service_')]
assert len(install_cases)==6 and all(t.find('failure') is None and t.find('error') is None for t in install_cases)
assert passed(O/'INSTALLED_CONTRACT_WRAPPERS.xml')==2
contracts={basis:passed(O/('CONTRACTS_'+basis+'.xml')) for basis in ('query_latency_20261007_r3','query_latency_20261007_r4')}
traces=[]
for p in sorted(O.glob('TEST_*.json.gz')):
 rows=json.loads(gzip.decompress(p.read_bytes()));assert any('GENOS_RELEASE_GATE PASS' in row['stdout'] and row['returncode']==0 for row in rows);assert any('CODE_RESTORED' in row['stdout'] and row['returncode']==0 for row in rows);assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in row['stdout'] for row in rows)==2
 traces.append({'path':p.name,'sha256':sha(p.read_bytes()),'commands':len(rows),'expected_rejections':sum(row['returncode']!=0 for row in rows)})
assert len(traces)==6 and source['known_predecessors']==990
spec=json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()));assert len(spec['signatures'])==990
for raw in spec['blobs'].values():ast.parse(base64.b64decode(raw),feature_version=(3,10))
assert (O/(N+'_PASTE_ALL.txt')).read_bytes().endswith((R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes())
field={'code_root':'~/DEV','git_commit':None,'generation':None,'generation_manifest_sha256':None,'code_serving_revision':None,'applied':False,'deployed':False,'workflow_editor_saved':False,'workflow_test':'NOT_RUN'}
validation={'status':'PASS_DISPLAY_BOUNDARIES_AND_INSTALLER','environment':'WSL synthetic models/data; no GENOS access','local_main':{'release_id':active['release_id'],'generation':61,'manifest_sha256':active['release_manifest_sha256'],'selected_files_verified':301,'service_health':200,'service_search':200,'injected_failures_via_actual_service':smoke['injected_failures_via_actual_service']},'protocol_matrix_cases':2400,'qualified_contracts':298,'installed_contracts':contracts,'editor_contracts':15,'installation_states':6,'service_boots':12,'same_committed_checkout_mock_generation_gates':6,'installer_evidence':traces,'known_predecessor_inventories':990,'source_files':source['source_files'],'field_variant_hashes':source['field_variants'],'field':field,'real_model_calls':0,'limitations':result['limitations']+['Existing global ADR graph errors8; added errors0.','Process death or platform response blocking is outside the executing display code.','GENOS field adapters retain existing cache/transport bytes; variant hashes recorded separately from local MAIN.'],'main_evidence':{'path':str((A/'artifacts/main-service-smoke.json').relative_to(R)),'sha256':sha((A/'artifacts/main-service-smoke.json').read_bytes())},'evidence_hashes':{p.name:sha(p.read_bytes()) for p in O.iterdir() if p.is_file() and p.suffix in ('.log','.xml')},'run_txt_sha256':sha((O/(N+'_RUN.txt')).read_bytes()),'editor_sha256':sha((O/(N+'_PASTE_ALL.txt')).read_bytes()),'installer_sha256':sha((O/'apply_patch.py').read_bytes())}
(O/'VALIDATION.json').write_bytes(enc(validation))
(O/'VALIDATION_SUMMARY.txt').write_text('예외 안내 R1 / 로컬 MAIN61 반영\n\n합성 프로토콜2400/2400, 관련 계약298/298\n선택301파일 hash 및 실제 WSL service.service HEALTH200/RAG_SEARCH200, 503/timeout/limit 확인\nGENOS 설치 코드 '+str(sum(contracts.values()))+'계약 통과 (캐시2계열; shortcut 설치 여부별 검사)\n독립 편집기15검사 통과; 실제 편집기 저장 필요\n설치/재실행/변조거부/원복6상태, 서비스 부팅12회, 동일 committed checkout 모의 generation gate6회\n알려진 선행 inventory990종; 기존 캐시/조사 예산/모델 전송/DB 보존\n정본5소스 중 workflow는 MAIN61과 동일, 현장 app/chat/stream/main_workflow는 기존 전송·진단 설정을 보존하여 variant hash 별도 기록\n신규 모델 호출0. GENOS 현장 반입/내부 모델/리비전/워크플로우 화면 성공은 미확인\n실패 표시 개선이며 503/timeout 원인 자체를 해결했다는 뜻이 아님\n기존5회귀 실패, 전역 graph8오류(추가0), 구 엔진6종 stale pin은 남아 있음\n')
(O/'HANDOFF.json').write_bytes(enc({'version':N,'predecessor':'ASSESSMENT_GAP_ACTION R2','field':field,'email_status':'NOT_SENT_AT_SEAL; see external EMAIL_SENT.json','rebuild_required':False,'workflow_editor_change_required':True,'requires_new_code_serving_revision':True,'requires_sse_restart':True,'local_main':validation['local_main']}))
(O/'AGENT_FAILURE_RECOVERY_POLICY.txt').write_bytes((R/'07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md').read_bytes());(O/'MAIN_RESULT.txt').write_bytes((A/'MAIN_RESULT.txt').read_bytes())
files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt',N+'_PASTE_ALL.txt','GUIDE_UTF8.txt','VALIDATION.json','VALIDATION_SUMMARY.txt','HANDOFF.json','SOURCE_BINDING.json','AGENT_FAILURE_RECOVERY_POLICY.txt','MAIN_RESULT.txt']
for n in source['source_files']:
 p=O/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/n).read_bytes());ast.parse(p.read_bytes(),feature_version=(3,10));files.append(str(p.relative_to(O)))
ast.parse((O/'apply_patch.py').read_bytes(),feature_version=(3,10));subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,'deployment_zip':'RUN apply constructs APPLIED_CODE.zip from exact installed checkout; payload is qualified source reference only','files':[{'path':n,'sha256':sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
(O/'CODE_MANIFEST.json').write_bytes(enc(manifest));files.append('CODE_MANIFEST.json');(O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
with zipfile.ZipFile(O/(N+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in files:
  assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'};z.write(O/n,n)
with zipfile.ZipFile(O/(N+'.zip')) as z:
 assert z.testzip() is None
 assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
 for row in manifest['files']:assert sha(z.read(row['path']))==row['sha256']
attachments=[N+'.zip',N+'_RUN.txt',N+'_PASTE_ALL.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']
(O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
print(json.dumps({'installed_contracts':contracts,'install_states':6,'editor_tests':15,'zip_bytes':(O/(N+'.zip')).stat().st_size,'run_bytes':(O/(N+'_RUN.txt')).stat().st_size,'main_generation':61}))
