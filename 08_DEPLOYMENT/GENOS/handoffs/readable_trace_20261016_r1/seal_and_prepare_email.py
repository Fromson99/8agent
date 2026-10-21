"""Seal tested bytes, inspect attachments and prepare the authorized Samsung mail."""
import base64,gzip,hashlib,io,json,re,subprocess,zipfile
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET

H=Path(__file__).resolve().parent;NAME='GENOS_READABLE_TRACE_20261016_R1'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists() and not (H/'EMAIL_SENT.json').exists()
tests=ET.parse(H/'TEST_RESULTS.xml').getroot();suites=list(tests.iter('testsuite'))
assert sum(int(s.attrib['tests']) for s in suites)==2
assert sum(int(s.attrib['errors'])+int(s.attrib['failures']) for s in suites)==0
runtime=['apply_patch.py','PATCH_SPEC.json.gz',NAME+'_RUN.txt']
with zipfile.ZipFile(H/(NAME+'.zip')) as z:
    assert z.testzip() is None
    assert all(z.read(n)==(H/n).read_bytes() for n in runtime)
    tested={'tested_provisional_zip_sha256':sha((H/(NAME+'.zip')).read_bytes()),
            'runtime_files':{n:sha(z.read(n)) for n in runtime},
            'packaging_only_after_test':['validation','guides','source_binding','checksums']}
(H/'TESTED_PACKAGE_BINDING.json').write_bytes(enc(tested))
reports={}
for mode in ('zip','standalone'):
    rows=json.loads(gzip.decompress((H/('TEST_'+mode+'.json.gz')).read_bytes()))
    installed=[r for r in rows if 'installed_contract_runner.py' in ' '.join(r['argv'])]
    assert len(installed)==1 and installed[0]['returncode']==0 and '33 passed' in installed[0]['stdout']
    assert 'INSTALLED_CONTRACT_IMPORTS PASS; modules=220' in installed[0]['stdout']
    gate=[r for r in rows if 'gate' in r['argv']]
    assert len(gate)==1 and gate[0]['returncode']==0 and 'GENOS_RELEASE_GATE PASS' in gate[0]['stdout']
    boot=[r for r in rows if 'ACTUAL_SERVICE_BOOT PASS;' in r['stdout']]
    assert len(boot)==1 and boot[0]['returncode']==0
    reports[mode]={'installation_sequence':'PASS','installed_contracts_passed':33,
                   'installed_runtime_imports':220,'same_committed_checkout_release_gate':'PASS',
                   'actual_service_boot':'PASS; synthetic TLS model discovery only',
                   'source_test_transcript_sha256':sha((H/('TEST_'+mode+'.json.gz')).read_bytes())}
validation={'recorded_at':datetime.now(timezone.utc).isoformat(),'revision':NAME,
 'prerequisite':'GENOS_MAIN_FULL_20261016_R1','source_binding':'SOURCE_BINDING.json',
 'working_tests':{'passed':106,'record':'WORKING_VALIDATION.json'},'delivery_tests':reports,
 'interrupted_install_recovery':'PASS; hard exit after first code write, exact preimage restore and reapply',
 'preservation':'PASS; NFS generation/selection, field configuration, output/budget overlays, unrelated files',
 'drift_and_later_edit_rejection':'PASS; both check and undo refuse unknown changes',
 'repeat_and_rollback':'PASS; identical install replay and exact original byte restoration',
 'python311':json.loads((H/'PYTHON311_CHECK.json').read_bytes()),
 'no_external_or_genos_model_calls':True,'local_main_activation_changed':False,
 'known_baseline_tests':'3 pre-existing gateway fixture failures documented in WORKING_VALIDATION.json',
 'limits':['The approximately 180-second model timeout in the photos is not fixed.',
           'AD trace writes after completion; RAG trace appends during execution.',
           'Shared storage failure, forced termination or existing report limits may leave partial logs.',
           'Ingestion/build model logs are outside this request-report path.'],
 'genos':{'package_created':True,'field_applied':False,'field_commit':None,'field_generation':None,
          'code_serving_revision':None,'internal_model_workflow_test':'NOT_RUN'}}
(H/'VALIDATION.json').write_bytes(enc(validation))
files=runtime+['GUIDE_UTF8.txt','SAMPLE.trace.txt','SOURCE_BINDING.json','VALIDATION.json',
               'WORKING_VALIDATION.json','PYTHON311_CHECK.json','TESTED_PACKAGE_BINDING.json']
inventory={'schema_version':'genos-readable-trace-overlay-v1','revision':NAME,
           'application':'existing ~/DEV; fixed GENOS_MAIN_FULL_20261016_R1 predecessor required',
           'files':[{'path':n,'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in files]}
(H/'CODE_MANIFEST.json').write_bytes(enc(inventory));files.append('CODE_MANIFEST.json')
(H/'PACKAGE_SHA256SUMS.txt').write_text(''.join(sha((H/n).read_bytes())+'  '+n+'\n' for n in files))
files.append('PACKAGE_SHA256SUMS.txt')
with zipfile.ZipFile(H/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in files:z.writestr(name,(H/name).read_bytes())
attachments=[NAME+'.zip',NAME+'_RUN.txt','GUIDE_UTF8.txt','SAMPLE.trace.txt','VALIDATION.json','SHA256SUMS.txt']
(H/'SHA256SUMS.txt').write_text(''.join(sha((H/n).read_bytes())+'  '+n+'\n' for n in attachments[:-1]))
sealed={'revision':NAME,'sealed_at':datetime.now(timezone.utc).isoformat(),
        'files':{n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in set(files+attachments)},
        'field_applied':False,'email_sent':False}
(H/'SEALED.json').write_bytes(enc(sealed))
banned={'.js','.jsx','.mjs','.cjs'}
with zipfile.ZipFile(H/(NAME+'.zip')) as z:
    assert z.testzip() is None and all(Path(n).suffix.lower() not in banned for n in z.namelist())
    assert all(z.read(n)==(H/n).read_bytes() for n in files)
    assert all(sha(z.read(n))==pin for n,pin in tested['runtime_files'].items())
run=(H/(NAME+'_RUN.txt')).read_text()
embedded=re.findall(r"raw=zlib.decompress\(base64.b64decode\('([A-Za-z0-9+/=]+)'\)\)",run)
assert len(embedded)==1
import zlib
bundle=json.loads(zlib.decompress(base64.b64decode(embedded[0],validate=True)))
assert base64.b64decode(bundle['code'])==(H/'apply_patch.py').read_bytes()
assert bundle['spec']==json.loads(gzip.decompress((H/'PATCH_SPEC.json.gz').read_bytes()))
for state in bundle['spec']['signatures'].values():
    for name,row in state['patches'].items():
        assert Path(name).suffix.lower() not in banned
        assert sha(base64.b64decode(bundle['spec']['blobs'][row['after_sha256']],validate=True))==row['after_sha256']
subprocess.run(['bash','-n',str(H/(NAME+'_RUN.txt'))],check=True)
body=f'''<!doctype html><html><body>
<p>요청하신 <strong>vi용 LLM 전체 과정 로그와 중복 오류 표시 개선본</strong>을 보냅니다.</p>
<p><strong>앞서 보낸 GENOS_MAIN_FULL_20261016_R1 전체 반입본을 기존 ~/DEV에 설치한 다음 적용하는 추가 패치</strong>입니다.
해당 코드가 아니거나 다른 수정이 있으면 기존 파일을 보존하고 중단합니다. 기존 MAIN76 기능·최신 문서 선택·GENOS 설정을 유지합니다.</p>
<p>요청마다 <strong>*.trace.txt</strong>에 agent/서비스 단계별로 문단을 나누어 전체 과정을 누적합니다.
실제 전송 프롬프트·LLM 응답·호출 시간·입력/출력 토큰을 기록하고,
<strong>찾은 정보</strong>와 <strong>실제 프롬프트에 들어간 정보</strong>를 따로 표시합니다.
같은 traceback은 최초 한 번만 펼치고 이후 ERR-0001 같은 번호를 참조합니다.</p>
<p><strong>첨부를 업로드한 실제 TRANSFER 폴더에서 실행</strong></p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply</pre>
<p>각 단계의 READABLE_TRACE_EXIT=0을 확인하고 진행합니다. 별도 RUN.txt는 ZIP 안과 동일한 완전한 실행 파일입니다.
로그는 TRANSFER/readable-trace-r1-logs, 백업·적용 receipt는 readable-trace-r1-state에 남습니다.</p>
<p>기존 DEV에서 이번 변경만 검토·commit한 뒤 같은 TRANSFER에서 실행합니다.</p>
<pre>bash ./{NAME}/{NAME}_RUN.txt gate</pre>
<p>gate가 통과한 동일 commit을 push하고 코드서빙 새 리비전을 배포한 후 SSE를 재시작합니다.
이번 패치에는 워크플로우 편집기 변경이나 데이터 재구축이 없습니다. 현장 확인은 <strong>워크플로우 테스트 화면</strong>에서 합니다.</p>
<p>기존 GENOS_SHARED_LOG_DIR의 날짜/팀/legal_agent 또는 ad_mode 폴더에서 요청의 *.trace.txt를 vi로 열면 됩니다.
기존 요약 TXT/JSON에도 상세 경로가 표시됩니다. vi에서 /프롬프트에 들어간 정보, /찾은 정보, /오류 요약으로 이동할 수 있습니다.</p>
<p><strong>확인 사항:</strong> 작업 코드 106건, 설치된 코드 계약 33건씩(ZIP·별도 TXT),
설치 중단 복구·재실행·원복·실제 서비스 진입점·동일 checkout 배포 전 검사를 로컬 모의 환경에서 통과했습니다.
GENOS 현장 적용·내부 모델 결과는 아직 미확인입니다. 사진의 약 180초 timeout 자체를 해결한 변경은 아닙니다.
RAG는 실행 중 누적되며 AD 상세 기록은 작업 종료 뒤 생성됩니다.</p>
<p>첨부 6개: 패치 ZIP, 완전한 실행 TXT, 적용·원복 안내, 모의 로그 예시, 검증 결과, SHA-256 목록.</p>
<p>ZIP SHA-256: {sha((H/(NAME+'.zip')).read_bytes())}</p>
</body></html>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];bindings=[]
for n in attachments:
    raw=(H/n).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(n).suffix,'text/plain')
    parts.append({'mime_type':mime,'content_disposition':'attachment','filename':n,
                  'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    bindings.append({'name':n,'sha256':sha(raw),'bytes':len(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com',
      'subject':'[GENOS] vi용 LLM 전체 과정 로그 + 중복 오류 정리 (2026-10-16 R1)',
      'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_BODY_UTF8.html').write_text(body)
(H/'EMAIL_ATTACHMENT_BINDING.json').write_bytes(enc(bindings))
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
check={'recipient':args['to'],'subject':args['subject'],'attachments':bindings,
       'sealed_runtime_matches_tested_bytes':True,'no_javascript':True,'bash_syntax':'PASS',
       'embedded_standalone_payload':'PASS','email_args_characters':len((H/'EMAIL_ARGS.json').read_text())}
(H/'EMAIL_PRECHECK.json').write_bytes(enc(check));print(json.dumps(check,ensure_ascii=False,indent=2))
