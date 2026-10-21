"""Seal only the actual installed and validated ZIP, preserving field status."""
from common import *
import zipfile,io
P=ROOT/'08_DEPLOYMENT/GENOS/handoffs/structured_selection_20261021_r1'
name='GENOS_STRUCTURED_SELECTION_20261021_R1'
build=read(P/'BUILD.json');v=read(P/'DELIVERY_VALIDATION.json');package=read(P/'PACKAGE.json')
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
assert v['passed'] and sha(P/(name+'.zip'))==v['archive_sha256']==build['sha256']
assert pointer==build['local_active_release'] and package['code']==release['files']
with zipfile.ZipFile(P/(name+'.zip')) as z:
 assert z.testzip() is None
 assert z.read('PACKAGE.json')==(P/'PACKAGE.json').read_bytes()
 for n,h in package['payload'].items():assert hashlib.sha256(z.read(n)).hexdigest()==h,n
 with zipfile.ZipFile(io.BytesIO(z.read('code.zip'))) as code:
  assert code.testzip() is None
  for n,h in package['code'].items():
   assert hashlib.sha256(code.read(n)).hexdigest()==h,n
   assert hashlib.sha256(z.read('payload/'+n)).hexdigest()==h,n
   assert sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h,n
 assert z.read('GENOS_WORKFLOW_PYTHON.txt')==z.read('payload/08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
result=read(ART/'result.json')
save(P/'SEALED.json',{'archive':name+'.zip','archive_sha256':build['sha256'],
 'validation_sha256':sha(P/'DELIVERY_VALIDATION.json'),'code_manifest_sha256':sha(P/'CODE_MANIFEST.json'),
 'qualified_contracts':199,'installed_contracts':v['installed_contracts'],'installer_commands':v['commands'],
 'local_main_generation':pointer['generation'],'release_manifest_sha256':pointer['release_manifest_sha256'],
 'all419_working_candidate_selected_packaged_installed_match':True,
 'candidate_exact_read_cases':result['correct']['candidate'],'candidate_total_cases':32,
 'physical_model_requests':result['physical_model_calls'],'model_responses':result['response_count'],
 'provider_errors':result['provider_errors'],'quality_certified':False,'GENOS_field_verified':False,
 'GENOS_commit':None,'GENOS_serving_revision':None,'data_modified':False})
(P/'SHA256SUMS.txt').write_text(''.join(f'{sha(P/n)}  {n}\n' for n in
 (name+'.zip',name+'_RUN.txt','GUIDE.txt','GENOS_WORKFLOW_PYTHON.txt','CODE_MANIFEST.json','DELIVERY_VALIDATION.json','SEALED.json')))
A=ROOT/'09_ARTIFACTS/AUDITS/20261021-structured-selection-main'
with (A/'RESULT.txt').open('a') as f:
 f.write(f'\n최종 ZIP: {P.relative_to(ROOT)}/{name}.zip\nSHA256: {build["sha256"]}\n')
 f.write(f'ZIP에서 추출해 설치한 코드80검사, 설치/재적용/커밋게이트/해시불일치 거부/사용자 변경 보존/원복{v["commands"]}명령 통과.\n')
 f.write(f'최종 실험의 실제 요청{result["physical_model_calls"]}회 중 응답{result["response_count"]}회. 기준 arm의 HTTP429 1회는 재시도 없이 실패로 보존했으며 모델 의미 오류로 해석하지 않는다.\n')
path=ROOT/'GENOS.md';text=path.read_text();heading='# GENOS — 질문과 작업의 진입점\n'
note=f'''\n2026-10-21 **범위·복수·제외 구조화 선택의 실제 LLM 검증 후 로컬 MAIN{pointer['generation']} / workflow{package['workflow_version']}을 선택하고 `GENOS_STRUCTURED_SELECTION_20261021_R1` ZIP을 완성했다.** 신규 합성32질문에서 최종 후보32/32의 원문 집합이 일치했다. 범위·열거·제외·열린 경계·목·여러 항/문서·빈 선택·없는 번호·적용 가정을 검사했다. 초기 후보16/32, 보완 후보31/32는 거절 기록으로 보존했고, 필수 구조화 필드와 적용 가정/원문 제외 구분을 보완한 새 후보를 새 문장으로 검증했다. 최종 실제 요청64회/응답63회이며 기준 arm의 HTTP429 1회는 재시도 없이 실패 기록으로 남겼다. 최종199계약, 실제 선택 서비스 HEALTH, 작업/검증/선택/ZIP419파일 일치와 ZIP 설치80계약·{v['commands']}명령을 확인했다. 데이터·모델 프로필·검색 선택은 유지했다. 전체 원문 코퍼스 재로딩은 기존 임베딩 작업과 병렬 실행하지 않았고 원문 읽기는 같은 코드의 합성 API/실제 모델 경계로 확인했다. **외부 Qwen3.8 합성 범위 선택 검증이며 전체 법률 답변이나 GENOS 내부 모델의 품질 인증은 아니다. 현장 반입·배포·편집기 적용·Git commit/push·메일 발송 미수행.** 앞선 자연어 라우팅 ZIP의 기능도 포함한다. [MAIN 검증·복원](09_ARTIFACTS/AUDITS/20261021-structured-selection-main/RESULT.txt) · [반입 안내](08_DEPLOYMENT/GENOS/handoffs/structured_selection_20261021_r1/GUIDE.txt) · [최종 ZIP 검증](08_DEPLOYMENT/GENOS/handoffs/structured_selection_20261021_r1/SEALED.json).\n'''
assert text.startswith(heading);path.write_text(heading+note+text[len(heading):])
print('Sealed final ZIP:',build['sha256'],'MAIN',pointer['generation'],'GENOS field unverified')
