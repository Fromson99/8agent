"""Seal the exact tested scoped fulltext installer and its source lineage."""
import ast,gzip,json,platform,subprocess,zipfile,xml.etree.ElementTree as ET
from datetime import datetime,timezone
import build_delivery as b
OUT,ROOT,NAME=b.OUT,b.ROOT,b.NAME

def passed_xml(path,count=None):
    cases=list(ET.parse(path).iter('testcase'))
    assert cases and (count is None or len(cases)==count),path
    assert not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped')),path
    return len(cases)

def main():
    archive=OUT/(NAME+'.zip');assert not archive.exists(),'Preserve sealed delivery'
    hand=json.loads((OUT/'HANDOFF.json').read_bytes())
    spec=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    assert b.sha((OUT/(NAME+'_RUN.txt')).read_bytes())==hand['run_txt_sha256']
    assert b.sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())==hand['local_active_pointer_sha256']
    assert b.sha((b.RELEASE/'release.json').read_bytes())==hand['source_release_manifest_sha256']
    assert b.sha((b.RELEASE/'code'/b.TARGET).read_bytes())==hand['source_unit_fulltext_sha256']
    passed_xml(OUT/'TESTS.xml',3);passed_xml(OUT/'INSTALLED_TESTS.xml',2)
    contracts={p.name:passed_xml(p) for p in sorted(OUT.glob('CONTRACTS_*.xml'))}
    assert len(contracts)==2
    evidence=[]
    for p in sorted(OUT.glob('TEST_*.json.gz')):
        rows=json.loads(gzip.decompress(p.read_bytes()))
        failures=[r for r in rows if r['returncode']]
        assert len(failures)==3
        assert "UnitFulltextIndex.article_groups_page() got an unexpected keyword argument 'unit_keys'" in failures[0]['stderr']
        assert any('R3_REAL_ARTICLE_MENU PASS' in r['stdout'] and r['returncode']==0 for r in rows)
        assert any('GENOS_RELEASE_GATE PASS' in r['stdout'] and r['returncode']==0 for r in rows)
        assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in r['stdout'] for r in rows)==2
        evidence.append({'path':p.name,'sha256':b.sha(p.read_bytes()),'commands':len(rows),
                         'expected_r2_typeerror':1,'expected_tamper_rejections':2})
    assert len(evidence)==3
    counts={'installation_states':3,'r2_article_menu_typeerror_reproductions':3,'r3_article_menu_pass':3,
        'service_boot_200_before_and_after':6,'same_committed_checkout_mock_generation_gates':3,
        'commands':sum(r['commands'] for r in evidence),'expected_tamper_rejections':6,
        'installed_contracts':sum(contracts.values()),'known_r2_inventories':len(spec['predecessors']),
        'unit_fulltext_variants':len(spec['variants']),'real_network_calls':0,'real_model_inferences':0}
    validation={'status':'PASS','environment':'WSL local, synthetic fulltext/source generation, mocked model discovery',
        'python':platform.python_version(),'counts':counts,'commands':evidence,'installed_contracts':contracts,
        'run_txt_sha256':hand['run_txt_sha256'],'test_sources':{p.name:b.sha(p.read_bytes()) for p in OUT.glob('test_*.py')},
        'test_results':{p.name:b.sha(p.read_bytes()) for p in OUT.glob('*.xml')},
        'inventory_bindings_sha256':b.sha((OUT/'INVENTORY_BINDINGS.json.gz').read_bytes()),
        'preserved':['unmodified methods within each installed unit_fulltext variant','all other implementation files',
                     'source generation bytes','local MAIN53 pointer','R1/R2/CM/transport/budget/workflow bytes'],
        'limitations':['Synthetic contract tests are not answer-quality or internal-model tests.',
                       'All 330 inventories checked statically; only the three listed installation states executed end to end.',
                       'Scoped queries intentionally bypass unrestricted result projections, as MAIN53 does.',
                       'GENOS field commit, revision and generation hashes unknown; workflow not executed.']}
    (OUT/'VALIDATION.json').write_bytes(b.encoded(validation))
    summary=f'''GENOS RAG R3 SELECT unit_keys 오류 정정 — 검증 결과

원인: R1은 범위 제한 검색 호출을 포함했지만 unit_fulltext.py의 대응 변경을 누락했습니다.
R2는 초기화 설정 검증만 수정하여 이 결함이 남았습니다.
대표 3종(R3 캐시/R4 캐시/R4 캐시+표시 R5)의 R1·R2 적용본에서 실제 article_menu 호출의
사진과 동일한 TypeError를 재현했습니다. R3 적용 후 같은 호출과 범위 제한 조회가 통과했습니다.
실제 service.service 초기화도 적용 전/후 6회 모두 200입니다. GET /models만 모의 응답입니다.

최종 독립 RUN 및 준비 명령 {counts['commands']}개: 오류 재현 3회, 의도한 변조 거부 6회,
check/apply/재실행/verify/undo, 동일 committed checkout의 모의 generation gate 3회 확인.
원복 후 R2 전체 코드/manifest 바이트와 선택 generation 불변 확인.
선택 키·권한 교집합, 빈 범위, 범위 변경 커서 거부, 미제한 캐시 재사용과 제한 검색 격리 확인.
설치된 두 캐시 계열에서 기존 구조 탐색/SEARCH_BODY/원문 읽기/캐시 회귀 {counts['installed_contracts']}개 통과.
해당 회귀에는 fixture 구축용 지원 파일을 추가했으며, 배포 게이트는 별도 순수 설치 checkout에서 실행했습니다.
전체 허용 R2 inventory 330종의 해시·pin·정확한 역변환을 정적으로 확인했습니다.
unit_fulltext 2종의 변경은 4개 범위 조회 함수에 한정했고 나머지 함수는 원본 그대로입니다.

WSL Python {platform.python_version()}; Python 3.10 구문 검사와 Bash 구문 검사 통과.
로컬 MAIN53과 데이터 세대/DB/CM/모델/전송/서비스 예산/워크플로우를 변경하지 않았습니다.
실제 네트워크/모델 추론 0회. 검색 품질·성능 측정이나 내부 모델 인증은 아닙니다.
GENOS 실제 반입·commit/push·새 리비전·워크플로우 성공 및 현장 Python 실행은 미확인입니다.
'''
    (OUT/'VALIDATION_SUMMARY.txt').write_text(summary)
    source={k:hand[k] for k in ('version','source_release','source_release_manifest_sha256','source_code_root',
        'required_predecessor','prior_code_zip_sha256','source_unit_fulltext_sha256','unit_variants','local_active_pointer_sha256')}
    source.update(target=b.TARGET,selection_generation=53,requires_rebuilt_generation=False,cache_implementation_changed=False,
        changed_methods=['_page_query','law_groups_page','article_groups_page','hit_page'],
        field_code_root='~/DEV',field_git_commit=None,field_generation=None,field_generation_manifest_sha256=None,
        field_code_serving_revision=None,workflow_test='NOT_RUN')
    (OUT/'SOURCE_BINDING.json').write_bytes(b.encoded(source))
    ast.parse((OUT/'apply_patch.py').read_bytes(),feature_version=(3,10))
    payloads=[]
    for p in sorted((OUT/'payload').glob('*/unit_fulltext.py')):
        ast.parse(p.read_bytes(),feature_version=(3,10));assert b.sha(p.read_bytes())==p.parent.name
        payloads.append(p.relative_to(OUT).as_posix())
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    assert '.venv/bin/python' not in (OUT/(NAME+'_RUN.txt')).read_text()
    files=['apply_patch.py','PATCH_SPEC.json.gz',NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt',
           'VALIDATION.json','SOURCE_BINDING.json','FIELD_OBSERVATION.json','INVENTORY_BINDINGS.json.gz',*payloads]
    manifest={'schema_version':'genos-transfer-overlay-v1','id':NAME,'transfer_only':True,
        'deployment_zip':'apply creates APPLIED_CODE.zip from actual DEV; use that archive for gate',
        'validation':counts,'files':[{'path':n,'sha256':b.sha((OUT/n).read_bytes()),'bytes':(OUT/n).stat().st_size} for n in files]}
    (OUT/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
    (OUT/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((OUT/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in files:z.write(OUT/n,n)
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        assert all(b.sha(z.read(row['path']))==row['sha256'] for row in manifest['files'])
        assert z.read(NAME+'_RUN.txt')==(OUT/(NAME+'_RUN.txt')).read_bytes()
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    hand.update(sealed_at_utc=datetime.now(timezone.utc).isoformat(),code_zip_sha256=b.sha(archive.read_bytes()),
                code_zip_bytes=archive.stat().st_size,code_manifest_sha256=b.sha((OUT/'CODE_MANIFEST.json').read_bytes()),validation=counts)
    (OUT/'HANDOFF.json').write_bytes(b.encoded(hand))
    (OUT/'SHA256SUMS.txt').write_text(''.join(b.sha((OUT/n).read_bytes())+'  '+n+'\n' for n in [archive.name,NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']))
    print(json.dumps({'zip':str(archive),'sha256':hand['code_zip_sha256'],'bytes':hand['code_zip_bytes'],**counts},ensure_ascii=False))

if __name__=='__main__':
    from pathlib import Path
    main()
