"""Seal the exact tested installer and payload; no field success is inferred."""
import ast
import base64
from datetime import datetime,timezone
import gzip
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import build_delivery as b

O,R,N=b.OUT,b.ROOT,b.NAME


def passed(path):
    cases=list(ET.parse(path).iter('testcase'))
    assert cases and not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped')),path
    return len(cases)


def main():
    assert not (O/(N+'.zip')).exists()
    working=passed(O/'WORKING_TESTS.xml');assert working==115
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
    binding=json.loads((O/'SOURCE_BINDING.json').read_bytes())
    assert all(b.sha((R/n).read_bytes())==h for n,h in binding['source_files'].items())
    spec=json.loads(gzip.decompress((O/'PATCH_SPEC.json.gz').read_bytes()))
    assert len(spec['signatures'])==330
    state=next(iter(spec['signatures'].values()))
    for n,patch in state['patches'].items():
        raw=base64.b64decode(spec['blobs'][patch['after_sha256']])
        path=O/'payload'/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        assert b.sha(raw)==patch['after_sha256']
        ast.parse(raw,feature_version=(3,10))
    run=O/(N+'_RUN.txt');subprocess.run(['bash','-n',str(run)],check=True)
    assert '.venv/bin/python' not in run.read_text()
    hand=json.loads((O/'HANDOFF.json').read_bytes());assert hand['run_txt_sha256']==b.sha(run.read_bytes())
    counts={'working_contracts':working,'installed_contracts':sum(contracts.values()),
        'installation_states':3,'service_boots':6,'same_committed_checkout_mock_generation_gates':3,
        'installer_commands':sum(x['commands'] for x in evidence),'expected_tamper_rejections':6,
        'known_narrative_r2_inventories':330,'implementation_files':2,'real_model_inferences':0}
    validation={'status':'PASS','environment':'WSL; synthetic data/transport; no GENOS access',
        'counts':counts,'contracts':contracts,'evidence':evidence,
        'working_report_sha256':b.sha((O/'WORKING_TESTS.xml').read_bytes()),
        'run_txt_sha256':b.sha(run.read_bytes()),'source_binding_sha256':b.sha((O/'SOURCE_BINDING.json').read_bytes()),
        'test_sources':{p.name:b.sha(p.read_bytes()) for p in O.glob('test_*.py')},
        'scope':'Transport completion fix. Existing field generation and workflow editor preserved; no local promotion by this task.',
        'limitations':['Local fixtures verify protocol and wiring, not internal model quality or browser timing.',
                      'Field commit/generation/revision and workflow screen remain unverified.',
                      'No DONE remains incomplete; valid JSON or usage alone never certifies completion.']}
    (O/'VALIDATION.json').write_bytes(b.encoded(validation))
    summary=f'''GENOS 최종 답변 스트림 종료 처리 수정 R1 / 검증 결과

로컬 작업 코드 관련 계약 {working}개 통과(종료 처리·실제 Gateway 연결26개 포함).
실제 현장 httpx 코드 설치 조합 계약 {counts['installed_contracts']}개 통과.
대표 설치3상태, 서비스 초기화6회, 같은 committed checkout의 모의 generation gate3회 통과.
독립 RUN의 check/apply/재실행/verify/원복 등 {counts['installer_commands']}명령 검사.
변조 확인/원복 거부6회는 의도한 보호 동작입니다. 원문 generation 불변 확인.
알려진 narrative R2 inventory330종의 전체 코드와 엔진/PIPELINE 결속 확인.
추가 모듈과 수정 transport를 같은 설치 코드에서 import·실행했습니다.
테스트 수는 독립 품질 표본이나 실제 현장 요청 수가 아닙니다.
실제 외부·내부 모델 호출0회. GENOS 현장 반입/배포/워크플로우 화면 성공은 미확인입니다.
작업 코드와 인계본 수정 완료. 이 작업에서 로컬 선택 포인터를 변경하지 않았습니다.
별도 작업의 현재 로컬 MAIN57에는 이 전송 수정이 포함되지 않았으며 GENOS 인계와 별개입니다.
'''
    (O/'VALIDATION_SUMMARY.txt').write_text(summary)
    guide=O/'GUIDE_UTF8.txt'
    guide.write_text(guide.read_text().replace('관련 계약113개와 추가된 실제 Gateway 연결 검사 포함 종료 계약26개',
        f'관련 계약{working}개(실제 Gateway 연결 검사 포함 종료 계약26개 포함)').replace('계약282개',f"계약{counts['installed_contracts']}개"))
    files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt',
        'VALIDATION.json','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz','WORKING_INTEGRATION.json']
    files.extend(str(p.relative_to(O)) for p in sorted((O/'payload').rglob('*')) if p.is_file())
    assert all(p.suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in map(b.Path,files))
    manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,
        'deployment_zip':'apply creates APPLIED_CODE.zip from actual ~/DEV; gate that exact checkout',
        'files':[{'path':n,'sha256':b.sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
    (O/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
    (O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in files))
    files.append('PACKAGE_SHA256SUMS.txt')
    archive=O/(N+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in files:z.write(O/n,n)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(b.Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
        assert all(b.sha(z.read(row['path']))==row['sha256'] for row in manifest['files'])
    hand.update(sealed_at_utc=datetime.now(timezone.utc).isoformat(),source_status='contract_verified',
        code_zip_sha256=b.sha(archive.read_bytes()),code_zip_bytes=archive.stat().st_size,
        code_manifest_sha256=b.sha((O/'CODE_MANIFEST.json').read_bytes()),validation=counts)
    active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    hand['observed_local_selection']={'release_id':active['release_id'],'generation':active['generation'],
        'changed_by_this_task':False,'transport_fix_in_selected_release':False}
    (O/'HANDOFF.json').write_bytes(b.encoded(hand))
    mail=[archive.name,N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']
    (O/'SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in mail))
    print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,**counts}))


if __name__=='__main__':main()
