"""Seal only code, installer and reviewable handoff records; no data or secrets."""
import ast,base64,gzip,hashlib,json,subprocess,zipfile,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
import build_delivery as b
OUT=b.OUT;ROOT=b.ROOT;NAME=b.NAME

def main():
 hand=json.loads((OUT/'HANDOFF.json').read_bytes());v=json.loads((OUT/'VALIDATION.json').read_bytes())
 assert v['run_txt_sha256']==hand['run_txt_sha256']==b.sha((OUT/(NAME+'_RUN.txt')).read_bytes())
 assert b.sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())==hand['local_active_pointer_sha256']
 assert len(v['variants'])==8 and all(row['passed'] for row in v['variants'])
 def tests(name):
  cases=list(ET.parse(OUT/name).iter('testcase'));assert cases
  assert not any(c.find('error') is not None or c.find('failure') is not None or c.find('skipped') is not None for c in cases)
  return len(cases)
 counts={'patched_code_contracts':tests('CONTRACTS.xml'),'same_checkout_mock_generation_gates':tests('GATE_TESTS.xml'),'installation_states':len(v['variants']),'txt_commands':v['txt_commands'],'known_inventory_signatures':hand['known_code_signatures'],'model_calls':0}
 spec=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
 for raw in spec['blobs'].values():ast.parse(base64.b64decode(raw),feature_version=(3,10)) if base64.b64decode(raw).lstrip().startswith((b'"""',b'from ',b'import ')) else None
 for p in (OUT/'payload').rglob('*.py'):ast.parse(p.read_bytes(),feature_version=(3,10))
 subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
 assert '.venv/bin/python' not in (OUT/(NAME+'_RUN.txt')).read_text()
 summary=f'''GENOS RAG 최적화 패치 R1 검증 결과\n\n로컬 MAIN53: focused-rules-20261013-r1 / 완료 계약 v8\nGENOS 인계 조합의 모의 RAG 계약: {counts['patched_code_contracts']}개 통과\n실제 첨부 RUN: {counts['installation_states']}개 대표 설치 상태 / {counts['txt_commands']}개 명령 통과\n알려진 기존 코드 inventory {counts['known_inventory_signatures']}종의 engine/schema/output hash 확인\n같은 committed checkout + 모의 generation gate: {counts['same_checkout_mock_generation_gates']}개 통과\n적용/재실행/검증/원복/변경된 코드 거부와 캐시·서비스·모델 전송·워크플로우 파일 보존 확인\nPython 3.10 문법 / Bash 구문 / JavaScript 제외 / ZIP 내부·별도 RUN 동일 바이트 확인\n신규 외부 모델 호출 0. 로컬 MAIN53 포인터와 원문 세대 변경 없음.\n\n시험 환경: WSL 로컬. fixture 생성용 schema와 factorized_audit 보조 파일만 시험 폴더에 추가.\nHTTP 모의 검사는 GENOS service와 같이 runtime_root를 명시. 해당 보조 파일/시험 수정은 인계 코드에 포함하지 않음.\n초기 시험 환경 경로 누락·로컬 기본 layout 불일치 기록은 보존하고 위 조건으로 다시 검증함.\nGENOS 실제 반입/commit/push/리비전/워크플로우 화면은 현장 확인 전 미확인.\n조건 AND/OR 의미 판단·의미상 반복·모델 형식 복구 지연은 남아 있음.\n'''
 (OUT/'VALIDATION_SUMMARY.txt').write_text(summary)
 files=['apply_patch.py','PATCH_SPEC.json.gz',NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SOURCE_BINDING.json','REVIEWED_MERGES.json']
 files += [p.relative_to(OUT).as_posix() for p in sorted((OUT/'payload').rglob('*.py'))]
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in files)
 manifest={'schema_version':'genos-transfer-overlay-v1','id':NAME,'transfer_only':True,'deployment_zip':'apply creates APPLIED_CODE.zip from actual DEV; use that archive for the gate','source_release':'focused-rules-20261013-r1','source_release_manifest_sha256':hand['source_release_manifest_sha256'],'validation':counts,'files':[{'path':n,'sha256':b.sha((OUT/n).read_bytes()),'bytes':(OUT/n).stat().st_size} for n in files]}
 (OUT/'CODE_MANIFEST.json').write_bytes(b.encoded(manifest));files.append('CODE_MANIFEST.json')
 (OUT/'PACKAGE_SHA256SUMS.txt').write_text(''.join(b.sha((OUT/n).read_bytes())+'  '+n+'\n' for n in files));files.append('PACKAGE_SHA256SUMS.txt')
 archive=OUT/(NAME+'.zip')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in files:z.write(OUT/n,n)
 with zipfile.ZipFile(archive) as z:
  assert len(z.namelist())==len(set(z.namelist()))
  assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
  assert z.read(NAME+'_RUN.txt')==(OUT/(NAME+'_RUN.txt')).read_bytes()
  assert all(b.sha(z.read(row['path']))==row['sha256'] for row in manifest['files'])
 hand.update(created_at=datetime.now(timezone.utc).isoformat(),code_zip_sha256=b.sha(archive.read_bytes()),code_zip_bytes=archive.stat().st_size,code_manifest_sha256=b.sha((OUT/'CODE_MANIFEST.json').read_bytes()),validation=counts)
 (OUT/'HANDOFF.json').write_bytes(b.encoded(hand))
 attachments=[archive.name,NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt']
 (OUT/'SHA256SUMS.txt').write_text(''.join(b.sha((OUT/n).read_bytes())+'  '+n+'\n' for n in attachments))
 print(json.dumps({'zip':str(archive),'sha256':hand['code_zip_sha256'],'bytes':archive.stat().st_size,**counts},ensure_ascii=False))
if __name__=='__main__':main()
