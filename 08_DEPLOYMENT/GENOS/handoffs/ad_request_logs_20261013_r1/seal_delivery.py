"""Seal only final verified bytes and retain limits and baseline failure evidence."""
import ast,base64,gzip,json,subprocess,zipfile
import xml.etree.ElementTree as ET
import build_delivery as b

O,R,N=b.OUT,b.ROOT,b.NAME


def passed(path):
    cases=list(ET.parse(path).iter('testcase'))
    assert cases and not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped')),path
    return len(cases)


def main():
    assert not (O/(N+'.zip')).exists()
    working=passed(O/'WORKING_TESTS.xml')+passed(O/'OVERHEAD_TESTS.xml')
    assert passed(O/'INSTALL_TESTS.xml')==5
    contracts={p.name:passed(p) for p in O.glob('CONTRACTS_*.xml')}
    assert len(contracts)==2
    evidence=[]
    for p in O.glob('TEST_*.json.gz'):
        rows=json.loads(gzip.decompress(p.read_bytes()))
        assert sum(bool(x['returncode']) for x in rows)==2
        assert sum('GENOS_RELEASE_GATE PASS' in x['stdout'] for x in rows)==1
        assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in x['stdout'] for x in rows)==2
        evidence.append({'path':p.name,'sha256':b.sha(p.read_bytes()),'commands':len(rows)})
    assert len(evidence)==3
    binding=json.loads((O/'SOURCE_BINDING.json').read_text())
    assert all(b.sha((R/n).read_bytes())==h for n,h in binding['source_files'].items())
    spec=json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()))
    assert len(spec['signatures'])==330
    # One representative readable payload; every exact variant is in PATCH_SPEC.
    for n,patch in next(iter(spec['signatures'].values()))['patches'].items():
        raw=base64.b64decode(spec['blobs'][patch['after_sha256']])
        ast.parse(raw,feature_version=(3,10))
        path=O/'payload'/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    validation={'status':'PASS_SCOPED_CHECKS','environment':'WSL; synthetic data and HTTP responses',
        'counts':{'working_contracts':working,'installed_contracts':sum(contracts.values()),
            'installation_states':3,'service_boots':6,'same_committed_checkout_mock_generation_gates':3,
            'installer_commands':sum(row['commands'] for row in evidence),'expected_tamper_rejections':6,
            'known_field_inventories':330,'implementation_files':len(binding['source_files']),
            'real_model_inferences':0},'contracts':contracts,'evidence':evidence,
        'run_txt_sha256':b.sha((O/(N+'_RUN.txt')).read_bytes()),
        'source_binding_sha256':b.sha((O/'SOURCE_BINDING.json').read_bytes()),
        'test_sources':{n:b.sha((O/n).read_bytes()) for n in ('test_delivery.py','test_installed_contracts.py','run_installed_tests.py')},
        'local_selected_release_at_seal':{'release_id':active['release_id'],'generation':active['generation'],
            'changed_by_this_task':False,'this_patch_promoted':False},
        'limitations':['GENOS field HTTP cause and successful deployment/screen remain unverified.',
            'Existing numbered-reference schema-repair test fails before and after; see BASELINE_NOTES.json.',
            'Shared report finalization is best effort after AD completion; SQL audit remains authoritative.']}
    (O/'VALIDATION.json').write_bytes(b.encoded(validation))
    (O/'VALIDATION_SUMMARY.txt').write_text(
        f'GENOS 팀별 실행 로그·모델 계약 R1 검증\n\n작업 코드 계약: {working}개 통과\n'
        f'현장 설치 코드 계약: {sum(contracts.values())}개 통과\n'
        f'대표 설치3상태 / 설치·확인·원복·게이트 명령{validation["counts"]["installer_commands"]}개\n'
        '변조 거부6회 / 서비스 초기화6회 / 동일 committed checkout 모의 generation gate3회\n'
        '알려진 현장 inventory330종 / 실제 모델 추론0회\n\n'
        '별도 숫자 인용 schema-repair 검사1개는 수정 전후 동일하게 실패합니다. 통과 수에서 제외했습니다.\n'
        '기존 테스트 실행기의 forkserver 문제를 guarded wrapper로 고친 뒤 현장 계약 전체를 재실행했습니다.\n'
        '실제 GENOS 오류 해결·반입·배포·화면 성공 및 로컬 MAIN 승격을 뜻하지 않습니다.\n')
    (O/'HANDOFF.json').write_bytes(b.encoded({'version':N,'field_code_root':'~/DEV',
        'field_git_commit':None,'field_generation':None,'field_generation_manifest_sha256':None,
        'field_code_serving_revision':None,'genos_applied':False,'genos_deployed':False,
        'workflow_test':'NOT_RUN','email_status':'NOT_SENT','rebuild_required':False,
        'workflow_editor_change_required':False,'predecessor':'GENOS_MODEL_STREAM_FIX_20261013_R1'}))
    files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt',
           'VALIDATION.json','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz','WORKING_INTEGRATION.json','BASELINE_NOTES.json','HANDOFF.json']
    files += [str(p.relative_to(O)) for p in sorted((O/'payload').rglob('*')) if p.is_file()]
    manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,
        'deployment_zip':'apply creates APPLIED_CODE.zip from the actual checkout',
        'files':[{'path':n,'sha256':b.sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
    (O/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
    checks=''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in files)
    (O/'PACKAGE_SHA256SUMS.txt').write_text(checks);files.append('PACKAGE_SHA256SUMS.txt')
    archive=O/(N+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in files:
            assert b.Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(O/n,n)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for row in manifest['files']:assert b.sha(z.read(row['path']))==row['sha256']
        assert z.read(N+'_RUN.txt')==(O/(N+'_RUN.txt')).read_bytes()
    subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
    attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']
    (O/'SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
    attachments.append('SHA256SUMS.txt')
    preflight={'to':'hyungjininfocz.son@partner.samsung.com',
        'subject':'[GENOS 수정 코드] 팀별 legal_agent·ad_mode 로그 분리 및 모델 요청 공통화 R1',
        'attachments':[{'filename':n,'bytes':(O/n).stat().st_size,'sha256':b.sha((O/n).read_bytes())} for n in attachments]}
    (O/'EMAIL_PREFLIGHT.json').write_bytes(b.encoded(preflight))
    print(json.dumps({'working':working,'installed':sum(contracts.values()),'zip_bytes':archive.stat().st_size,'attachments':len(attachments)}))


if __name__=='__main__':main()
