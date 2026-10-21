"""Seal only validated bytes; preserve field status as unverified."""
import ast,base64,gzip,hashlib,importlib.metadata,json,re,subprocess,sys,tempfile,xml.etree.ElementTree as ET,zipfile,zlib
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_DEPENDENCY_RECOVERY_20261014_R1'
A=R/'09_ARTIFACTS/AUDITS/20261014-dependency-recovery-fix'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda obj:(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
def read(path):return json.loads(path.read_bytes())
def stats(path):
    s=ET.parse(path).getroot().find('testsuite')
    return {k:int(s.attrib[k]) for k in ('tests','failures','errors','skipped')}
def main():
    assert not (O/(N+'.zip')).exists(),'Preserve sealed delivery'
    source=read(O/'SOURCE_BINDING.json');reg=read(A/'regression-final-result.json')
    for name,digest in read(O/'TESTED_DELIVERY_BINDING.json').items():assert sha((O/name).read_bytes())==digest,name
    assert reg['exit_code']==0 and reg['product_unchanged'] and reg['test_files_unchanged']
    assert sha((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())==reg['active_pointer_sha256']
    for name,digest in source['working_source_files'].items():assert sha((R/name).read_bytes())==digest,name
    for name,digest in source['source_files'].items():assert sha((O/'payload'/name).read_bytes())==digest,name
    for name,digest in reg['product_sha256'].items():assert source['source_files'][name]==digest
    for name,digest in reg['test_sha256'].items():assert sha((R/name).read_bytes())==digest,name
    assert source['known_predecessors']==330
    text=(O/(N+'_RUN.txt')).read_text()
    packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text).group(1)
    bundle=json.loads(zlib.decompress(base64.b64decode(packed)))
    assert base64.b64decode(bundle['code'])==(O/'apply_patch.py').read_bytes()
    assert bundle['spec']==json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()))
    delivery=stats(O/'DELIVERY_TESTS.xml');assert delivery==dict(tests=2,failures=0,errors=0,skipped=0)
    installed={p.name:stats(p) for p in sorted(O.glob('INSTALLED*.xml'))}
    assert len(installed)==2 and all(v==dict(tests=117,failures=0,errors=0,skipped=0) for v in installed.values()),installed
    counts={'commands':0,'generation_gates':0,'tls_boots':0,'undo':0,'tamper_rejections':0};roots=[];commits=[]
    for p in sorted(O.glob('TEST_*.json.gz')):
        rows=json.loads(gzip.decompress(p.read_bytes()));assert rows[-1]['returncode']==0 and rows[-1]['argv'][-1]=='check'
        counts['commands']+=len(rows)
        for row in rows:
            for key,phrase in [('generation_gates','GENOS_RELEASE_GATE PASS'),('tls_boots','SERVICE_TLS_BOOTSTRAP PASS'),('undo','CODE_RESTORED;')]:counts[key]+=phrase in row['stdout']
            if row['returncode']!=0:
                assert row['argv'][0]=='bash' and row['argv'][2] in ('verify','undo')
                counts['tamper_rejections']+=1
            if 'installed_runner.py' in str(row['argv']):
                assert 'INSTALLED_RUNTIME_IMPORTS PASS; modules=' in row['stdout'];roots.append(row['argv'][2])
    assert counts==dict(commands=32,generation_gates=2,tls_boots=2,undo=2,tamper_rejections=4),counts
    working=stats(A/'regression-final.xml');assert working==dict(tests=987,failures=0,errors=0,skipped=1),working
    validation={'revision':N,'working_regressions':working,'installed_contracts':installed,'installed_total':234,'delivery_tests':delivery,
        'installer_checks':counts,'known_predecessors':330,'changed_product_files':5,'working_fix_files':4,
        'source_binding':source,'verified_installed_roots':roots,'generation_type':'synthetic fixture; unchanged throughout apply/undo',
        'active_main':{'generation':62,'release':'schema-recovery-20261014-r1','pointer_sha256':reg['active_pointer_sha256'],'changed':False},
        'model_inference_calls':0,'real_genos_or_external_network_calls':0,'tls_test':'Local loopback synthetic model discovery only',
        'sys_executable':sys.executable,'python':sys.version.split()[0],
        'packages':{n:importlib.metadata.version(n) for n in ('jsonschema','referencing','requests','fastapi','pytest')},
        'field_status':'NOT_VERIFIED','field_checkout':None,'field_commit':None,'field_generation_path':None,'field_generation_manifest_sha256':None,'field_serving_revision':None,'field_workflow_test':None,
        'found_during_packaging':'Some predecessor field selection_report variants omitted rejected_decisions/stop_reason; restored MAIN62 forwarding while preserving each inventory raw traceback policy',
        'failures_preserved':'failures/four-file-field-diagnostic-failure.zip; original collection setup and fixture selection logs retained',
        'limitations':['Actual model recovery rate and legal quality not measured','Unknown inventories are rejected before code replacement','MAIN promotion and GENOS field deployment remain separate']}
    (O/'VALIDATION.json').write_bytes(enc(validation))
    (O/'VALIDATION_SUMMARY.txt').write_text('''GENOS 원문 의존 관계 오류·재개 복구 R1 검증 결과 (2026-10-14)
작업 코드: 51개 파일 회귀 986 passed / 1 skipped / 0 failed. 실제 모델 호출 0회.
현장 설치 형식: 2조합 각각 117개 계약/API 검사 통과, 합계 234개.
검증 실행 32명령: 기존 Git checkout 적용/재적용/검증/원복, 변조 거부 4회.
실제 service.service의 localhost TLS 부팅 2회, 같은 committed checkout generation gate 2회 통과.
TRANSFER 실행 위치 로그 생성, 예산/표시/서빙/TLS/CM/숏컷/로그와 데이터 세대 불변 검사 통과.
이전 스키마 R1 적용 완료 330개 inventory 지원. 4개 수정 파일은 작업 코드 검증 바이트와 동일.
현장 소비자 1개 추가: 누락된 조사 거절/중단 사유 연결을 MAIN62와 맞춤. 기존 raw traceback 설정은 보존.
초기 설치본 검사에서 3개 API 진단 검사가 각 조합에서 실패해 소비자 누락을 발견했다.
실패 기록을 보존했으며 최종 234개 검사에서는 실패/면제 0개다.
현재 로컬 MAIN62 포인터/선택 릴리스는 그대로다. GENOS 내부 모델·현장 코드·데이터는 접근하지 않았다.
현장 반입, commit/push, 실제 generation/리비전 선택과 워크플로우 질의는 미확인이다.
''')
    notes=(A/'RESULT_UTF8.txt').read_text()
    notes+='\n삼성메일 후속 인계에서 추가 발견/수정\n기존 스키마 R1 현장 패키지의 investigation_diagnostics.selection_report가\nrejected_decisions/stop_reason을 최종 진단에 전달하지 않았다. 후속 ZIP은 이 소비자도\nMAIN62와 맞추며 raw traceback 생략을 유지한다. 상세 검증은 VALIDATION_SUMMARY.txt 참조.\n'
    (O/'FIX_REPORT_UTF8.txt').write_text(notes)
    (O/'WORKING_REGRESSION_RECEIPT.json').write_bytes((A/'regression-final-result.json').read_bytes())
    for p in O.glob('*.xml'):p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    files=['apply_patch.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz','TESTED_DELIVERY_BINDING.json','VALIDATION.json','VALIDATION_SUMMARY.txt','GUIDE_UTF8.txt','FIX_REPORT_UTF8.txt','WORKING_REGRESSION_RECEIPT.json',N+'_RUN.txt']
    files += [str(p.relative_to(O)) for folder in ('payload','preimage') for p in (O/folder).rglob('*') if p.is_file()]
    files += [p.name for p in O.glob('INSTALLED*.xml.gz')]+['DELIVERY_TESTS.xml.gz']
    manifest={'schema_version':'genos-partial-patch-v1','revision':N,'prerequisite':'GENOS_SCHEMA_RECOVERY_20261014_R1','gate_archive':'apply-generated BACKUP/APPLIED_CODE.zip','files':[]}
    for name in sorted(files):
        p=O/name;raw=p.read_bytes()
        assert p.suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
        if p.suffix=='.py':ast.parse(raw,feature_version=(3,10))
        manifest['files'].append({'path':name,'sha256':sha(raw),'bytes':len(raw)})
    (O/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    archive=O/(N+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in sorted(files)+['CODE_MANIFEST.json']:z.write(O/name,name)
    with tempfile.TemporaryDirectory(prefix='dependency-sealed-unpack-') as td:
        target=Path(td)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
            z.extractall(target)
        for row in manifest['files']:
            raw=(target/row['path']).read_bytes();assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
        assert (target/(N+'_RUN.txt')).read_bytes()==(O/(N+'_RUN.txt')).read_bytes()
        subprocess.run(['bash','-n',str(target/(N+'_RUN.txt'))],check=True)
    attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json']
    (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
    sealed={'revision':N,'sha256':sha(archive.read_bytes()),'bytes':archive.stat().st_size,'members':len(files)+1,'no_javascript':True,'hash_verified_members':len(files),'standalone_run_matches':True,'bash_syntax':'PASS','field_status':'NOT_VERIFIED'}
    (O/'SEALED_UNPACK_CHECK.json').write_bytes(enc(sealed));print(json.dumps(sealed))
if __name__=='__main__':main()
