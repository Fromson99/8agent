"""Seal the installer correction only after tests of the exact embedded RUN."""
import ast,base64,gzip,json,subprocess,zipfile
import xml.etree.ElementTree as ET
import build_delivery as b

O,R,N=b.OUT,b.ROOT,b.NAME


def passed(path):
    cases=list(ET.parse(path).iter('testcase'))
    assert cases and not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped')),path
    return len(cases)


def main():
    assert not (O/(N+'.zip')).exists(),'Preserve sealed handoff'
    assert passed(O/'BUDGET_TESTS.xml')==8
    assert passed(O/'INSTALL_TESTS.xml')==8
    contracts={p.name:passed(p) for p in O.glob('CONTRACTS_*.xml')}
    assert len(contracts)==2 and sum(contracts.values())==416
    evidence=[]
    for p in sorted(O.glob('TEST_*.json.gz')):
        rows=json.loads(gzip.decompress(p.read_bytes()))
        expected_rejections=3 if '_budget.' in p.name else 2
        assert sum(bool(x['returncode']) for x in rows)==expected_rejections,p
        assert sum('GENOS_RELEASE_GATE PASS' in x['stdout'] for x in rows)==1
        assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in x['stdout'] for x in rows)==2
        evidence.append({'path':p.name,'sha256':b.sha(p.read_bytes()),'commands':len(rows),
                         'expected_rejections':expected_rejections})
    assert len(evidence)==6
    spec=json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()))
    prior=json.loads(gzip.decompress((b.PARENT/'PATCH_SPEC.json.gz').read_bytes()))
    assert {k:v for k,v in spec.items() if k!='revision'}=={k:v for k,v in prior.items() if k!='revision'}
    # RUN is the actual installer exercised by the installation tests.
    run=(O/(N+'_RUN.txt')).read_text()
    import zlib
    tree=ast.parse(run[run.index('import base64,hashlib,json,os,sys,types,zlib\n'):run.rindex('AD_REQUEST_LOGS_PY')])
    packed=tree.body[1].value.args[0].args[0].value
    bundle=json.loads(zlib.decompress(base64.b64decode(packed)))
    assert base64.b64decode(bundle['code'])==(O/'apply_patch.py').read_bytes()
    assert bundle['spec']==spec
    active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    validation={'status':'PASS_SCOPED_CHECKS','environment':'WSL; synthetic data/models; no GENOS access',
        'counts':{'installer_guard_tests':8,'installation_states':6,
            'service_boots':12,'same_committed_checkout_mock_generation_gates':6,
            'installer_commands':sum(r['commands'] for r in evidence),
            'r1_failure_reproductions_in_full_install_tests':3,'expected_tamper_rejections':12,
            'installed_contracts':sum(contracts.values()),'known_base_inventories':330,
            'distinct_shipped_service_variants_reversible_with_budget':6,'real_model_inferences':0},
        'contracts':contracts,'evidence':evidence,
        'run_txt_sha256':b.sha((O/(N+'_RUN.txt')).read_bytes()),
        'installer_sha256':b.sha((O/'apply_patch.py').read_bytes()),
        'runtime_implementation_changed_from_r1':False,
        'prior_working_contracts':{'count':116,'rerun_in_this_task':False,
            'validation_sha256':b.sha((b.PARENT/'VALIDATION.json').read_bytes())},
        'test_sources':{n:b.sha((O/n).read_bytes()) for n in ('test_budget_guard.py','test_delivery.py','test_installed_contracts.py','run_installed_tests.py')},
        'local_selected_release_at_seal':{'release_id':active['release_id'],'generation':active['generation'],
            'changed_by_this_task':False,'this_patch_promoted':False},
        'limitations':['GENOS R2 install, deployment, workflow and original AD model HTTP issue remain unverified.',
                      'Previously recorded numbered-reference schema-repair test is not fixed by this installer-only change.']}
    (O/'VALIDATION.json').write_bytes(b.encoded(validation))
    (O/'VALIDATION_SUMMARY.txt').write_text(
        'GENOS AD_REQUEST_LOGS R2 설치기 검증\n\n'
        'R1 service.py 오류: 기존 검증된 조사 예산 코드를 적용해 동일 메시지 재현\n'
        'R1 실패 시 코드 불변 및 backup 미생성 확인\n'
        '설치기 경계/거부 검사8개 통과\n'
        '대표 설치6상태(기존3상태 × 예산 설정 유무) 통과\n'
        f'실행/검사/원복/게이트 명령{validation["counts"]["installer_commands"]}개\n'
        '기존 R1 오류3회 재현 / 변조 거부12회 / service.service 초기화12회\n'
        '동일 committed checkout + 모의 generation 배포 게이트6회\n'
        '예산 코드가 있는 실제 설치본 계약416개 통과\n'
        '알려진 기준 inventory330종 / 서비스 변형6종의 예산 코드 복원 확인\n'
        '실제 GENOS/외부 모델 추론0회\n\n'
        '제품 코드 바이트는 R1과 동일하며 설치기만 수정했습니다.\n'
        'R1 작업 코드 검사116개는 기존 기록이며 이번 회차 재실행 수에 더하지 않았습니다.\n'
        '기존 숫자 인용 schema-repair 검사1개 실패는 별도 이력으로 유지합니다.\n'
        '실제 GENOS R2 적용/배포/화면 및 AD 모델 서버 오류 해결은 아직 미확인입니다.\n')
    (O/'HANDOFF.json').write_bytes(b.encoded({'version':N,'replaces_installer':'GENOS_AD_REQUEST_LOGS_20261013_R1',
        'predecessor':'GENOS_MODEL_STREAM_FIX_20261013_R1, with or without verified investigation-budget R1',
        'field_code_root':'~/DEV','field_git_commit':None,'field_generation':None,
        'field_generation_manifest_sha256':None,'field_code_serving_revision':None,
        'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT',
        'rebuild_required':False,'workflow_editor_change_required':False,'runtime_implementation_changed_from_r1':False}))
    files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt',
        'VALIDATION.json','SOURCE_BINDING.json','R1_SOURCE_RECORD.json','REPRODUCTION.json',
        'BASELINE_NOTES.json','HANDOFF.json']
    files += [str(p.relative_to(O)) for p in sorted((O/'payload').rglob('*')) if p.is_file()]
    manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,
        'deployment_zip':'apply creates APPLIED_CODE.zip from the actual checkout',
        'files':[{'path':n,'sha256':b.sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
    (O/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
    (O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in files))
    files.append('PACKAGE_SHA256SUMS.txt')
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
    (O/'EMAIL_PREFLIGHT.json').write_bytes(b.encoded({'to':'hyungjininfocz.son@partner.samsung.com',
        'subject':'[GENOS 수정 코드 R2] service.py 설치 오류 수정 — 기존 조사 예산 설정 보존',
        'attachments':[{'filename':n,'bytes':(O/n).stat().st_size,'sha256':b.sha((O/n).read_bytes())} for n in attachments]}))
    print(json.dumps({'installed_contracts':sum(contracts.values()),'installation_states':len(evidence),
                      'zip_bytes':archive.stat().st_size,'attachments':len(attachments)}))


if __name__=='__main__':main()
