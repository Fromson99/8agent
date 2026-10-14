import ast,gzip,hashlib,json,zipfile,xml.etree.ElementTree as E,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_ASSESSMENT_GAP_ACTION_20261013_R2';A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode();read=lambda p:json.loads(p.read_bytes())
assert not (O/(N+'.zip')).exists()
source=read(O/'SOURCE_BINDING.json');active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');selected=read(R/active['manifest_path']);smoke=read(A/'artifacts/main-service-smoke.json');result=read(A/'artifacts/run-001/result.json')
assert active['generation']==60 and smoke['status']=='PASS' and result['strict_success']
assert all(sha((R/n).read_bytes())==h==selected['files'][n]==sha((R/selected['code_root']/n).read_bytes()) for n,h in source['source_files'].items())
assert '8 passed' in (O/'INSTALL_TESTS.log').read_text()
contracts={}
for name in ('query_latency_20261007_r3','query_latency_20261007_r4'):
 cases=list(E.parse(O/('CONTRACTS_'+name+'.xml')).iter('testcase'));assert len(cases)==171 and all(t.find('failure') is None and t.find('error') is None for t in cases);contracts[name]=len(cases)
traces=[]
for p in sorted(O.glob('TEST_*.json.gz')):
 rows=json.loads(gzip.decompress(p.read_bytes()));assert any('GENOS_RELEASE_GATE PASS' in row['stdout'] and row['returncode']==0 for row in rows);assert any('CODE_RESTORED' in row['stdout'] and row['returncode']==0 for row in rows);assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in row['stdout'] for row in rows)==2
 traces.append({'path':p.name,'sha256':sha(p.read_bytes()),'commands':len(rows),'expected_rejections':sum(row['returncode']!=0 for row in rows)})
assert len(traces)==6 and source['known_predecessors']==990
field={'code_root':'~/DEV','git_commit':None,'generation':None,'generation_manifest_sha256':None,'code_serving_revision':None,'applied':False,'deployed':False,'workflow_test':'NOT_RUN'}
validation={'status':'PASS_SCOPED_FIX_AND_INSTALLER','environment':'WSL, synthetic model/data only; no GENOS access','local_main':{'release_id':active['release_id'],'generation':active['generation'],'manifest_sha256':active['release_manifest_sha256'],'selected_files_verified':301,'service_health':200,'service_search':200,'patch_selected':True},'matrix_cases':952,'unique_contracts_passed':353,'installed_contracts':contracts,'installation_states':6,'service_boots':12,'same_committed_checkout_mock_generation_gates':6,'installer_evidence':traces,'known_predecessor_inventories':990,'source_files':source['source_files'],'field':field,'real_model_calls':0,'limitations':result['limitations'],'prior_four_recovery_failures':{'path':'08_DEPLOYMENT/GENOS/handoffs/assessment_gap_action_20261013_r1/PREIMAGE_RECOVERY.xml','sha256':sha((O.with_name('assessment_gap_action_20261013_r1')/'PREIMAGE_RECOVERY.xml').read_bytes()),'resolved':False},'main_evidence':{'path':str((A/'artifacts/main-service-smoke.json').relative_to(R)),'sha256':sha((A/'artifacts/main-service-smoke.json').read_bytes())},'evidence_hashes':{p.name:sha(p.read_bytes()) for p in O.iterdir() if p.is_file() and p.suffix in ('.log','.xml')},'run_txt_sha256':sha((O/(N+'_RUN.txt')).read_bytes()),'installer_sha256':sha((O/'apply_patch.py').read_bytes())}
(O/'VALIDATION.json').write_bytes(enc(validation))
(O/'VALIDATION_SUMMARY.txt').write_text('원문 gap 행동 충돌 R2 검증 / MAIN60 반영\n\n고정 합성952조합, 관련353계약 통과\n선택301파일 해시, 실제 WSL service.service HEALTH200/RAG_SEARCH200\nGENOS 설치 코드342계약 통과 (캐시2계열, 최근 shortcut 적용 상태 포함)\n설치/재실행/변조거부/원복6상태, 서비스 초기화12회, 같은 committed checkout 모의 generation gate6회\n'+f'설치 명령{sum(t["commands"] for t in traces)}개, 예상 변조 거부{sum(t["expected_rejections"] for t in traces)}회\n'+ '알려진 선행 inventory990종 hash 고정. 3파일 payload는 MAIN60과 동일\n원문 재구축/워크플로우 편집기 교체 없음; 새 코드서빙 리비전/SSE 재시작 필요\n신규 모델 호출0. GENOS 현장 내부모델/반입/배포/워크플로우 성공은 미확인\n기존 복구4실패 및 전역 지침의 미구현 항목은 미해결로 보존\n')
(O/'HANDOFF.json').write_bytes(enc({'version':N,'predecessors':['MODEL_STREAM_FIX R1','AD_REQUEST_LOGS R2','SUCCESSFUL_SHORTCUT R1'],'use_instead_of':'ASSESSMENT_GAP_ACTION R1','field':field,'email_status':'NOT_SENT_AT_SEAL; see external EMAIL_SENT.json','rebuild_required':False,'workflow_editor_change_required':False,'requires_new_code_serving_revision':True,'requires_sse_restart':True,'local_main':validation['local_main']}))
files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION.json','VALIDATION_SUMMARY.txt','HANDOFF.json','SOURCE_BINDING.json','AGENT_FAILURE_RECOVERY_POLICY.txt','MAIN_RESULT.txt']
for n in source['source_files']:
 p=O/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/n).read_bytes());ast.parse(p.read_bytes(),feature_version=(3,10));files.append(str(p.relative_to(O)))
ast.parse((O/'apply_patch.py').read_bytes(),feature_version=(3,10));subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,'deployment_zip':'Apply constructs APPLIED_CODE.zip from exact installed checkout','files':[{'path':n,'sha256':sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
(O/'CODE_MANIFEST.json').write_bytes(enc(manifest));files.append('CODE_MANIFEST.json');(O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
with zipfile.ZipFile(O/(N+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in files:
  assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'};z.write(O/n,n)
with zipfile.ZipFile(O/(N+'.zip')) as z:
 assert z.testzip() is None
 for row in manifest['files']:assert sha(z.read(row['path']))==row['sha256']
attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']
(O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
print(json.dumps({'installed_contracts':342,'install_states':6,'zip_bytes':(O/(N+'.zip')).stat().st_size,'run_bytes':(O/(N+'_RUN.txt')).stat().st_size,'main_generation':60}))
