"""Seal only the tested installers and pinned source; field execution stays unverified."""
import ast,gzip,hashlib,importlib.metadata,json,sys,xml.etree.ElementTree as ET,zipfile
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_SCHEMA_RECOVERY_20261014_R1'
A=R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main/artifacts'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def read(p):return json.loads(p.read_bytes())
def stats(p):
    s=ET.parse(p).getroot().find('testsuite')
    return {k:int(s.attrib[k]) for k in ('tests','failures','errors','skipped')}
def main():
    assert not (O/(N+'.zip')).exists(),'Preserve sealed handoff'
    source=read(O/'SOURCE_BINDING.json');build=read(O/'BUILD_SOURCE_BINDING.json')
    for n,h in source['source_files'].items():assert sha((O/'payload'/n).read_bytes())==sha((R/n).read_bytes())==h,n
    for row in build['files']:assert sha((O/'build-payload'/row['path']).read_bytes())==sha((R/row['path']).read_bytes())==row['after']
    for n,h in build['dependencies'].items():assert sha((R/n).read_bytes())==h,n
    main=read(A/'main-service-smoke.json');assert main['status']=='PASS' and main['pointer']['generation']==62
    result=read(A/'run-001/result.json');assert result['strict_success']
    alltests=stats(O/'DELIVERY_ALL.xml');assert alltests==dict(tests=3,failures=0,errors=0,skipped=0)
    assert stats(O/'BUILD_DELIVERY_TESTS.xml')==dict(tests=1,failures=0,errors=0,skipped=0)
    installed={p.name:stats(p) for p in O.glob('INSTALLED*.xml')}
    assert sorted(x['tests'] for x in installed.values())==[61,89,89]
    assert all(not any(x[k] for k in ('failures','errors','skipped')) for x in installed.values())
    counts={'commands':0,'generation_gates':0,'tls_success':0,'tls_untrusted_rejected':0,'undo':0,'tamper_rejected':0}
    roots=[]
    for p in O.glob('TEST_*.json.gz'):
        rows=json.loads(gzip.decompress(p.read_bytes()));assert rows[-1]['returncode']==0 and rows[-1]['argv'][2]=='undo'
        counts['commands']+=len(rows)
        for row in rows:
            for name,phrase in [('generation_gates','GENOS_RELEASE_GATE PASS'),('tls_success','SERVICE_TLS_BOOTSTRAP PASS'),
                ('tls_untrusted_rejected','SERVICE_TLS_UNTRUSTED_REJECTED PASS'),('undo','CODE_RESTORED;')]:counts[name]+=phrase in row['stdout']
            counts['tamper_rejected']+=bool(row['returncode']!=0 and row['argv'][0]=='bash')
            if 'installed_runner.py' in str(row['argv']):
                assert row['returncode']==0 and 'INSTALLED_RUNTIME_IMPORTS PASS' in row['stdout'];roots.append(row['argv'][2])
    assert counts==dict(commands=53,generation_gates=2,tls_success=2,tls_untrusted_rejected=2,undo=2,tamper_rejected=4),counts
    b=json.loads(gzip.decompress((O/'BUILD_TEST_TRANSCRIPT.json.gz').read_bytes()))
    assert [r['returncode'] for r in b]==[1,0,0,0,0,0,1,0]
    same=[n for n,v in source['field_variants'].items() if set(v.values())=={source['source_files'][n]}]
    variations=[n for n in source['source_files'] if n not in same]
    v={'revision':N,'local_release':main['pointer'],'qualified_contracts':410,'regressions':{'passed':817,'skipped':1,'failed':0},
       'installed_contracts':installed,'installed_total':239,'delivery_tests':3,'query_installer_checks':counts,
       'build_installer_commands':8,'build_installer_tamper_rejections':2,'build_dependencies':len(build['dependencies']),
       'known_query_inventories':source['known_predecessors'],'query_files':len(source['source_files']),
       'query_files_identical_to_qualified_source':same,'field_compatibility_variants':variations,
       'field_compatibility_reasons':{'investigation_diagnostics.py':'Preserve field choice to omit duplicate raw traceback; add typed diagnostics',
           'request_entry.py':'Preserve field entry without wiki-recall activation; add bounded admission recovery'},
       'build_files':len(build['files']),'verified_query_roots':roots,'model_calls':0,'real_genos_or_external_network_calls':0,
       'transport_test':'Loopback TLS and synthetic model discovery only',
       'sys_executable':sys.executable,'python':sys.version.split()[0],
       'packages':{n:importlib.metadata.version(n) for n in ('jsonschema','referencing','requests','fastapi','pytest')},
       'genos_field_status':'NOT_VERIFIED','field_commit':None,'field_generation':None,'field_manifest_sha256':None,
       'field_serving_revision':None,'field_workflow_test':None,'email_sent':False,
       'limits':['Not actual model error-frequency or legal quality measurement',
           'Query prerequisite inventory must match; unknown versions remain unchanged',
           'Build install requires exact 261 dependency/asset and preimage hashes; older builds can require rebase',
           'GENOS Python, internal model, actual data and workflow/build execution unverified']}
    (O/'VALIDATION.json').write_bytes(enc(v))
    summary='''스키마 복구 R1 검증 결과
동결 합성 계약410개 통과. 기존 회귀817개 통과/1수집 제외/0실패.
로컬 MAIN62 선택302파일 및 실제 service.service 상태/검색/목록/실패 경계 확인.
GENOS 형식의 질의 설치본178개, 구축 설치본61개 검사 통과.
질의 설치2조합: 실제 RUN53명령, 재적용/원복, 변조거부4회, 같은 committed checkout generation gate2회.
실제 localhost TLS 부팅2회 및 미신뢰 인증서 거부2회. 내부/외부 실제 모델 호출0회.
구축 설치8명령: check/apply/reapply/verify/설치본61검사, 미확인 변경2회 거부, 원복.
질의330 inventory 지원. 변경20파일 중18파일은 동결 후보와 동일,2파일은 명시된 현장 동작 보존.
구축 전용12파일은 동결 후보와 동일. 정확한261 의존/자산 해시와 사전 파일이 필요.
초기 패키지 병합 거부/fixture 준비 실패는 failures/에 보존. 최종 검사에 면제한 실패 없음.
GENOS 반입·commit/push·리비전·워크플로우/구축 실행은 미확인. 실제 오류 빈도 감소는 미측정.
'''
    (O/'VALIDATION_SUMMARY.txt').write_text(summary)
    for p in O.glob('*.xml'):p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    for p in (O/'failures').glob('*'):
        if p.is_file() and p.suffix!='.gz':p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    files=['apply_patch.py','build_delivery.py','installed_runner.py','test_delivery.py','seal_delivery.py',
        'build_apply.py','build_check.py','build_runner.py','test_build_delivery.py','BUILD_SOURCE_BINDING.json',
        'PATCH_SPEC.json.gz','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz','VALIDATION.json','VALIDATION_SUMMARY.txt',
        'GUIDE_UTF8.txt',N+'_RUN.txt','GENOS_SCHEMA_BUILD_20261014_R1_RUN.txt']
    files += [str(p.relative_to(O)) for folder in ('payload','build-payload','preimage','merges') for p in (O/folder).rglob('*') if p.is_file()]
    files += [str(p.relative_to(O)) for folder in (O,O/'failures') for p in folder.glob('*.gz')]
    files=sorted(set(files));manifest={'version':N,'files':[]}
    for n in files:
        raw=(O/n).read_bytes()
        if n.endswith('.py'):ast.parse(raw,feature_version=(3,10))
        manifest['files'].append({'path':n,'sha256':sha(raw),'bytes':len(raw)})
    (O/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    archive=O/(N+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in files+['CODE_MANIFEST.json']:z.write(O/n,n)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        for row in manifest['files']:assert sha(z.read(row['path']))==row['sha256']
        assert z.read(N+'_RUN.txt')==(O/(N+'_RUN.txt')).read_bytes()
    attachments=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json']
    (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
    print(json.dumps({'archive':str(archive.relative_to(R)),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'installed_contracts':239}))
if __name__=='__main__':main()
