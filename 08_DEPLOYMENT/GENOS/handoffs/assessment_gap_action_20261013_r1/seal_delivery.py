"""Seal verified scoped repair; retain unrelated failures as explicit limitations."""
import gzip,hashlib,json,re,zipfile,xml.etree.ElementTree as E
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_ASSESSMENT_GAP_ACTION_20261013_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def main():
 source=json.loads((O/'SOURCE_BINDING.json').read_bytes());assert all(sha((R/n).read_bytes())==h for n,h in source['source_files'].items())
 assert '63 passed' in (O/'CONTRACTS_final.log').read_text()
 contracts={}
 for name in ('query_latency_20261007_r3','query_latency_20261007_r4'):
  xml=E.parse(O/('CONTRACTS_'+name+'.xml'));cases=list(xml.iter('testcase'))
  assert cases and all(t.find('failure') is None and t.find('error') is None for t in cases)
  contracts[name]=len(cases)
 assert '2 passed' in (O/'DELIVERY_CONTRACTS.log').read_text()
 traces=[]
 for p in sorted(O.glob('TEST_*.json.gz')):
  rows=json.loads(gzip.decompress(p.read_bytes()))
  assert any('GENOS_RELEASE_GATE PASS' in row['stdout'] and row['returncode']==0 for row in rows)
  assert any('CODE_RESTORED' in row['stdout'] and row['returncode']==0 for row in rows)
  assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in row['stdout'] for row in rows)==2
  traces.append({'path':p.name,'sha256':sha(p.read_bytes()),'commands':len(rows),'expected_rejections':sum(row['returncode']!=0 for row in rows)})
 assert len(traces)==4
 active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes());selected=json.loads((R/active['manifest_path']).read_bytes())
 old=E.parse(O/'PREIMAGE_RECOVERY.xml');old_fail=[t.get('name') for t in old.iter('testcase') if t.find('failure') is not None]
 assert len(old_fail)==4
 validation={'status':'PASS_SCOPED_REPAIR_WITH_KNOWN_UNRELATED_FAILURES','environment':'WSL; synthetic data and model doubles; no GENOS access',
 'working_new_contracts':63,'working_regressions':{'passed':276,'failed':4,'preimage_same_failures':old_fail,'preimage_passed':6,'note':'Pre-fix 3 sources and matching pins in isolated current code reproduce the same 4 legacy recovery contracts. No global recovery pass claim.'},
 'installed_contracts':contracts,'installation_states':4,'service_boots':8,'same_committed_checkout_mock_generation_gates':4,'installer_evidence':traces,
 'real_model_calls':0,'known_predecessor_inventories':source['known_predecessors'],'source_files':source['source_files'],
 'selected_release_at_seal':{'release_id':active['release_id'],'generation':active['generation'],'changed_by_this_task':False,'patch_selected':all(selected['files'].get(n)==h for n,h in source['source_files'].items())},
 'field':{'code_root':'~/DEV','git_commit':None,'generation':None,'generation_manifest_sha256':None,'code_serving_revision':None,'applied':False,'deployed':False,'workflow_test':'NOT_RUN'},
 'limitations':['First ASSESS rejection visible; second rejection payload unavailable. Fix covers the confirmed source-gap/action conflict, not all 422 causes.','No legal semantic quality or GENOS internal-model claim.','Global failure-policy items documented as unimplemented remain follow-up work.'],
 'development_failures':['Initial 4 native tests stopped before API behavior on stale engine pins; selective repinning fixed them.','Installed fixtures initially omitted explicit runtime_root and used local workspace layout; corrected fixtures without changing installed runtime.','Empty-claim test assumed newer public failure envelope; assertion now checks either supported failure envelope plus HTTP 422 and original internal cause.'],
 'evidence_hashes':{p.name:sha(p.read_bytes()) for p in O.iterdir() if p.is_file() and (p.suffix in ('.log','.xml') or p.name=='PREIMAGE_RECOVERY.log.gz')},
 'run_txt_sha256':sha((O/(N+'_RUN.txt')).read_bytes()),'installer_sha256':sha((O/'apply_patch.py').read_bytes())}
 (O/'VALIDATION.json').write_bytes(enc(validation))
 (O/'VALIDATION_SUMMARY.txt').write_text('판단 원문 gap 행동 충돌 수정 R1 검증\n\n신규 작업 계약/API: 63개 통과\n확대 회귀: 276개 통과, 기존 복구 계약4개 실패\n수정 전 3파일 복원 격리 코드에서도 같은 4개 실패 (별도 후속)\n'+f'실제 설치 코드 계약: {sum(contracts.values())}개 통과 (캐시2계열)\n'+f'설치4상태/서비스 초기화8회/같은 committed checkout 모의 generation gate4회\n설치 명령 {sum(t["commands"] for t in traces)}개 / 변조 거부 {sum(t["expected_rejections"] for t in traces)}회\n알려진 선행 inventory660종 해시 연결\n'+f'선택된 로컬 MAIN{active["generation"]}에는 이번 3파일 수정 미포함; 본 작업에서 승격하지 않음\n'+'원문 부족/사용자 사실/권한/잘못된 근거/재진입 한도/중복 요청/근거 없음 중단을 검사\n실제 모델 호출0회. GENOS 반입/배포/워크플로우 성공은 미확인\n전역 코딩 지침 전체를 구현 완료했다는 뜻이 아님\n')
 (O/'HANDOFF.json').write_bytes(enc({'version':N,'predecessors':['MODEL_STREAM_FIX R1','AD_REQUEST_LOGS R2'],'field':validation['field'],'email_status':'NOT_SENT','rebuild_required':False,'workflow_editor_change_required':False,'requires_new_code_serving_revision':True,'requires_sse_restart':True}))
 files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION.json','VALIDATION_SUMMARY.txt','HANDOFF.json','SOURCE_BINDING.json']
 for n in source['source_files']:
  p=O/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/n).read_bytes());files.append(str(p.relative_to(O)))
 manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,'deployment_zip':'Apply builds APPLIED_CODE.zip from the exact installed checkout.',
  'files':[{'path':n,'sha256':sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
 (O/'CODE_MANIFEST.json').write_bytes(enc(manifest));files.append('CODE_MANIFEST.json')
 (O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
 with zipfile.ZipFile(O/(N+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in files:z.write(O/n,n)
 with zipfile.ZipFile(O/(N+'.zip')) as z:
  assert z.testzip() is None
  for row in manifest['files']:assert sha(z.read(row['path']))==row['sha256']
 (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in [N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']))
 print(json.dumps({'installed_contracts':sum(contracts.values()),'install_states':len(traces),'zip_bytes':(O/(N+'.zip')).stat().st_size,'active_generation':active['generation']}))
if __name__=='__main__':main()
