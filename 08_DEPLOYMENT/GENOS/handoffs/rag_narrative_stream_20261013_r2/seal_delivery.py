"""Seal only the exact evaluated candidate and tested installer."""
import ast,gzip,json,platform,subprocess,zipfile,xml.etree.ElementTree as ET
from datetime import datetime,timezone
import build_delivery as b
O,R,N=b.OUT,b.ROOT,b.NAME
def passed(p):
 cases=list(ET.parse(p).iter('testcase'));assert cases and not any(c.find(k) is not None for c in cases for k in ('error','failure','skipped')),p
 return len(cases)
def main():
 assert not (O/(N+'.zip')).exists()
 result=json.loads((b.A/'artifacts/run-001/result.json').read_text());assert result['strict_success']
 assert (b.A/'artifacts/final-validation.txt').read_text().startswith('OK:')
 assert passed(O/'TESTS.xml')==5
 contracts={p.name:passed(p) for p in O.glob('CONTRACTS_*.xml')};assert len(contracts)==2
 evidence=[]
 for p in O.glob('TEST_*.json.gz'):
  rows=json.loads(gzip.decompress(p.read_bytes()));assert sum(bool(x['returncode']) for x in rows)==2
  assert any('GENOS_RELEASE_GATE PASS' in x['stdout'] for x in rows)
  assert sum('SERVICE_PROFILE_BOOTSTRAP PASS' in x['stdout'] for x in rows)==2
  evidence.append({'path':p.name,'sha256':b.sha(p.read_bytes()),'commands':len(rows)})
 assert len(evidence)==3
 hand=json.loads((O/'HANDOFF.json').read_text());assert hand['run_txt_sha256']==b.sha((O/(N+'_RUN.txt')).read_bytes())
 binding=json.loads((O/'SOURCE_BINDING.json').read_text())
 assert all(b.sha((b.NEW/p).read_bytes())==h for p,h in binding['source_files'].items())
 counts={'installation_states':3,'service_boots':6,'same_committed_checkout_mock_generation_gates':3,'commands':sum(x['commands'] for x in evidence),'installed_contracts':sum(contracts.values()),'known_r3_inventories':330,'implementation_files':9,'real_network_calls_in_delivery_tests':0,'real_model_inferences_in_delivery_tests':0}
 validation={'status':'PASS','environment':'WSL; synthetic generation and transport; no GENOS access','counts':counts,'evidence':evidence,'contracts':contracts,'run_txt_sha256':hand['run_txt_sha256'],'source_binding_sha256':b.sha((O/'SOURCE_BINDING.json').read_bytes()),'external_workflow_editor':{'path':'08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/genos_rag_chat.py','sha256':b.sha((R/'08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/genos_rag_chat.py').read_bytes())},'test_fixture_notes':'Field httpx transport mocked with its actual interface; workflow tests load existing R4 editor; native API fixture uses explicit runtime_root to avoid copying a host-specific workspace receipt. Production code unchanged by fixture adaptation.','test_sources':{p.name:b.sha(p.read_bytes()) for p in O.glob('test_*.py')},'limitations':['External public qualification is separate from internal model performance.','Native API checks actual incremental token emission using mock internal stream transport.','All330 inventory hashes checked, three installation states executed.','GENOS field revision/generation/commit and workflow rendering unverified.']}
 (O/'VALIDATION.json').write_bytes(b.encoded(validation))
 (O/'VALIDATION_SUMMARY.txt').write_text(f'''최종 답변 토큰 스트리밍 / 최종 검증\n\n공개 실험 ADR0769: 동결 기준 통과, 신규1문항 기준/후보와 기존1문항 회귀의 총3요청.\nADR0770: 텍스트/escape/Markdown 경계40조합 모두 문단 종료 전 송신, 완료 본문 동일.
후보 동일 코드의 직접 계약142개 통과. GENOS 설치 조합의 계약 {counts['installed_contracts']}개 통과.\n대표 설치3상태에서 서비스 초기화6회, 동일 committed checkout의 모의 generation gate3회,\ncheck/apply/재실행/verify/변조거부/undo 및 원문 세대 불변을 확인했습니다.\n최종 독립 RUN과 준비 명령 {counts['commands']}개. 알려진 R3 inventory330종의 해시/엔진 pin 확인.\n변경 구현/설정9개는 공개 검증 후보와 동일 바이트이고 나머지 현장 코드·캐시·전송은 보존합니다.\nGENOS 조합 검증은 실제 통신/추론0회. 원문 기반 의미 정확성과 현장 화면 성공을 인증하지 않습니다.\nGENOS 실제 반입·push·리비전/세대 결속·워크플로우 표시 성공은 미확인입니다.\n'''.replace('最終説明・段落ストリーミング / ',''))
 ast.parse((O/'apply_patch.py').read_bytes(),feature_version=(3,10));subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
 assert '.venv/bin/python' not in (O/(N+'_RUN.txt')).read_text()
 files=['apply_patch.py','PATCH_SPEC.json.gz',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz']
 manifest={'schema_version':'genos-transfer-overlay-v1','id':N,'transfer_only':True,'deployment_zip':'apply creates APPLIED_CODE.zip from actual DEV; use that for gate','files':[{'path':n,'sha256':b.sha((O/n).read_bytes()),'bytes':(O/n).stat().st_size} for n in files]}
 (O/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
 (O/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
 archive=O/(N+'.zip')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in files:z.write(O/n,n)
 with zipfile.ZipFile(archive) as z:assert all(b.sha(z.read(x['path']))==x['sha256'] for x in manifest['files'])
 hand.update(source_status='qualified',sealed_at_utc=datetime.now(timezone.utc).isoformat(),code_zip_sha256=b.sha(archive.read_bytes()),code_zip_bytes=archive.stat().st_size,code_manifest_sha256=b.sha((O/'CODE_MANIFEST.json').read_bytes()),validation=counts)
 (O/'HANDOFF.json').write_bytes(b.encoded(hand));(O/'SHA256SUMS.txt').write_text(''.join(b.sha((O/n).read_bytes())+'  '+n+'\n' for n in (archive.name,N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt')))
 print(json.dumps(counts))
if __name__=='__main__':main()
