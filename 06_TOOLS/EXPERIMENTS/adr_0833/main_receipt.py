from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0833-compact-delivery-qualification'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==78 and p['release_id']=='compact-evidence-delivery-20261016-r1'
release=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');active=read(A/'artifacts/active-consumer-v2.json');working=read(A/'artifacts/working-consumer-v2.json')
assert release['files']==f['serving_files']
assert all(sha(R/release['code_root']/n)==h for n,h in release['files'].items())
assert active['status']=='PASS' and len(active['checks'])==13 and not active['entry']['app_injected']
assert working['status']=='PASS' and working['qualified_component_hashes_match']
assert '109 passed, 1 deselected' in (A/'artifacts/working-api.log').read_text()
integration=read(A/'artifacts/working-integration.json')
assert all(sha(R/r['path'])==r['after'] for r in integration['changes'])
receipt={'status':'PASS','active_pointer':p,'release':ref(R/p['manifest_path']),
 'working_changes':len(integration['changes']),'working_api_passed':109,'retained_development_passed':317,'retained_known_failures':6,
 'finite_census_passed':160,'active_service_checks':13,'active_service_entry':active['entry'],
 'data':active['actual_data'],'frozen_candidate':ref(A/'artifacts/design/freeze.json'),
 'working_integration':ref(A/'artifacts/working-integration.json'),'working_tests':ref(A/'artifacts/working-api.log'),
 'active_consumer':ref(A/'artifacts/active-consumer-v2.json'),'qualification':ref(A/'artifacts/run-001/result.json'),
 'original831_failure_preserved':True,'fresh_model_verification':'Reserved834; report separately when complete',
 'quality_certified':False,'genos_deployed':False,
 'rollback':'Current78 to previous77 only: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main; verify active pointer before executing. Working backups in artifacts/working-before; never overwrite other edits.'}
(A/'MAIN_RESULT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
text='Compact 원문 전달 기록 수정 — 로컬 MAIN78 반영\n\n실제831에서 compact ASSESS의 원문 옵션 전달 기록 누락으로 최종 발행이 실패했다. 정확한 원문 조각을 현재 요청 원장에 결속하며 발행·권한·해시 검사는 유지했다.\n\n작업 코드33파일(구현2+연결pin31), 다른 변경39개 보존. 고정160조건, 기존317통과/기존6실패, 통합109검사, 실제 활성 서비스13검사 통과. 앱 주입 없이 작업 서비스 진입점이 MAIN78을 선택한 binding을 MAIN_RESULT.json에 기록했다. 실제 모델 결과는 ADR0834에서 별도로 검증한다. 법률 정확도·GENOS 성능 인증 아님.\n\n원본831 실패 기록은 불변이며 후속 지표로 소급 변경하지 않는다.\n'
(A/'MAIN_RESULT.txt').write_text(text)
D=R/'09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance'
(D/'FOLLOWUP_MAIN78.txt').write_text(text+'\n정본: '+str((A/'MAIN_RESULT.json').relative_to(R))+'\n')
print('MAIN78 same-code/active-service receipt saved')
