"""Seal the tested R1 correction without copying field data or credentials."""
import ast,gzip,json,platform,subprocess,zipfile,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
import build_delivery as b
OUT,ROOT,NAME=b.OUT,b.ROOT,b.NAME

def main():
 archive=OUT/(NAME+'.zip');assert not archive.exists(),'Preserve sealed delivery'
 hand=json.loads((OUT/'HANDOFF.json').read_bytes())
 assert b.sha((OUT/(NAME+'_RUN.txt')).read_bytes())==hand['run_txt_sha256']
 assert b.sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())==hand['local_active_pointer_sha256']
 assert b.sha((b.RELEASE/'release.json').read_bytes())==hand['source_release_manifest_sha256']
 assert (OUT/'payload'/b.TARGET).read_bytes()==(b.RELEASE/'code'/b.TARGET).read_bytes()
 cases=list(ET.parse(OUT/'TESTS.xml').iter('testcase'));assert len(cases)==3
 assert not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped'))
 variants=[]
 for p in sorted(OUT.glob('TEST_*.json.gz')):
  rows=json.loads(gzip.decompress(p.read_bytes()))
  assert len([r for r in rows if r['returncode']!=0])==2
  assert any('unknown v4 profile field' in r['stdout']+r['stderr'] for r in rows)
  assert any('SERVICE_PROFILE_BOOTSTRAP PASS' in r['stdout'] for r in rows)
  assert any('GENOS_RELEASE_GATE PASS' in r['stdout'] for r in rows)
  variants.append({'evidence':p.name,'sha256':b.sha(p.read_bytes()),'commands':len(rows),'expected_rejections':2,'passed':True})
 assert len(variants)==3
 counts={'installation_states':3,'r1_actual_service_boot_contract_error_reproductions':3,'r2_actual_service_boot_200':3,
  'same_committed_checkout_mock_generation_gates':3,'commands':sum(r['commands'] for r in variants),
  'expected_tamper_rejections':6,'known_r1_output_signatures':330,'real_network_calls':0,'real_model_inferences':0}
 validation={'status':'PASS','environment':'WSL local with synthetic generation and HTTP /models response only','python':platform.python_version(),
  'run_txt_sha256':hand['run_txt_sha256'],'test_source_sha256':b.sha((OUT/'test_delivery.py').read_bytes()),
  'junit_sha256':b.sha((OUT/'TESTS.xml').read_bytes()),'variants':variants,'counts':counts,
  'preserved':['all code except validator and binding manifests','generation bytes','MAIN53 active pointer'],
  'failed_setup_evidence':'failed_test_runs/01_missing_model_discovery_mock','field_deployment_verified':False}
 (OUT/'VALIDATION.json').write_bytes(b.encoded(validation))
 summary=f'''GENOS RAG R2 초기화 오류 정정 검증 결과

R1: 새 request_entry_policy 설정과 이전 workflow_tiers_policy 검증기가 함께 인계됨.
실제 service.service 초기화에서 unknown v4 profile field / ContractError / 503을 3개 설치 조합에서 재현.
R2: 누락 검증 파일을 MAIN53의 동일 바이트로 보완한 후 같은 3개 조합의 실제 서비스 초기화 200 확인.
대표 조합: 기존 캐시 R3, 캐시 R4, 캐시 R4 + 진행 표시 R5 (각 R1을 먼저 적용).
최종 독립 RUN 및 준비 명령 {counts['commands']}개: 정상 동작과 예상한 변조 거부 6회 확인.
각 조합의 check/apply/재실행/verify, 같은 committed checkout 모의 generation gate 3개 통과.
원복 시 R1 코드/manifest 전체 바이트 복원, generation 불변, 허용 범위 밖 파일 불변 확인.
허용 대상: 봉인된 R1 출력 inventory 330종. 모든 조합의 실제 부팅을 실행한 것은 아님.
Python 3.10 문법 / Bash 구문 / ZIP과 별도 RUN 동일 바이트 / JavaScript 제외 확인.

환경: WSL Python {platform.python_version()}, 모의 원문 generation, GET /models만 모의 HTTP 응답.
실제 서비스/profile/모델 목록 검증 함수는 실행. 실제 소켓 연결과 모델 추론 요청은 금지.
첫 검사는 모의 모델 목록 응답 누락으로 실패했고 기록을 보존한 뒤 해당 시험 설정을 보완함.
실제 네트워크/모델 추론 0회. 로컬 MAIN53 포인터 유지. 내부 데이터/인증정보 미포함.
GENOS 실제 적용/commit/push/리비전/워크플로우 성공 및 현장 Python 3.11 실행은 미확인.
사진에 내부 예외 메시지는 없어, 현장 장애에 다른 원인이 함께 있는지는 미확인.
'''
 (OUT/'VALIDATION_SUMMARY.txt').write_text(summary)
 source={k:hand[k] for k in ('version','source_release','source_release_manifest_sha256','source_code_root','required_predecessor','prior_code_zip_sha256','before_sha256','after_sha256','local_active_pointer_sha256')}
 source.update(target=b.TARGET,selection_generation=53,requires_rebuilt_generation=False,changes_cache=False,
  field_code_root='~/DEV',field_git_commit=None,field_generation=None,field_code_serving_revision=None,workflow_test='NOT_RUN')
 (OUT/'SOURCE_BINDING.json').write_bytes(b.encoded(source))
 for p in [OUT/'apply_patch.py',OUT/'payload'/b.TARGET]:ast.parse(p.read_bytes(),feature_version=(3,10))
 subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
 assert '.venv/bin/python' not in (OUT/(NAME+'_RUN.txt')).read_text()
 files=['apply_patch.py','PATCH_SPEC.json.gz',NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SOURCE_BINDING.json','payload/'+b.TARGET]
 manifest={'schema_version':'genos-transfer-overlay-v1','id':NAME,'transfer_only':True,
  'deployment_zip':'apply creates APPLIED_CODE.zip from actual DEV; use that archive for the gate',
  'validation':counts,'files':[{'path':n,'sha256':b.sha((OUT/n).read_bytes()),'bytes':(OUT/n).stat().st_size} for n in files]}
 (OUT/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
 (OUT/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((OUT/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in files:z.write(OUT/n,n)
 with zipfile.ZipFile(archive) as z:
  assert len(z.namelist())==len(set(z.namelist()))
  assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
  assert z.read(NAME+'_RUN.txt')==(OUT/(NAME+'_RUN.txt')).read_bytes()
  assert all(b.sha(z.read(r['path']))==r['sha256'] for r in manifest['files'])
 hand.update(sealed_at_utc=datetime.now(timezone.utc).isoformat(),code_zip_sha256=b.sha(archive.read_bytes()),
  code_zip_bytes=archive.stat().st_size,code_manifest_sha256=b.sha((OUT/'CODE_MANIFEST.json').read_bytes()),validation=counts)
 (OUT/'HANDOFF.json').write_bytes(b.encoded(hand))
 (OUT/'SHA256SUMS.txt').write_text(''.join(b.sha((OUT/n).read_bytes())+'  '+n+'\n' for n in [archive.name,NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']))
 print(json.dumps({'zip':str(archive),'sha256':hand['code_zip_sha256'],'bytes':hand['code_zip_bytes'],**counts},ensure_ascii=False))

if __name__=='__main__':main()
