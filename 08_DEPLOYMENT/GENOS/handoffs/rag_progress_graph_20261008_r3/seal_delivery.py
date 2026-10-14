"""Package only the validated runnable delivery and prepare the authorized mail."""
from pathlib import Path
import ast
import base64
import hashlib
import json
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261008-rag-progress-graph-r3-delivery'
NAME='GENOS_RAG_PROGRESS_GRAPH_20261008_R3'
sha=lambda data:hashlib.sha256(data).hexdigest()
encoded=lambda value:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def main():
    archive=OUT/(NAME+'.zip');assert not archive.exists(),'Preserve a sealed delivery'
    prior_raw=(AUDIT/'pre-r15-VALIDATION.json').read_bytes()
    validation=json.loads(prior_raw)
    extension=json.loads((OUT/'VALIDATION_EXTENSION.json').read_bytes())
    equivalence=json.loads((OUT/'EXTENSION_EQUIVALENCE.json').read_bytes())
    assert equivalence['every_prior_patch_output_and_source_identical']
    assert sha((OUT/'apply_display.py').read_bytes())==equivalence['unchanged_installer_sha256']
    for row in validation['variants']:row['tested_run_sha256']=equivalence['prior_run_sha256']
    for row in extension['variants']:row['tested_run_sha256']=equivalence['final_run_sha256']
    validation['variants']+=extension['variants']
    validation['txt_commands']+=extension['txt_commands']
    validation['contracts']+=extension['contracts']
    validation['run_verification']={'prior_69_commands':690,'final_extension_commands':extension['txt_commands'],
        'prior_validation_sha256':sha(prior_raw),'extension_equivalence_sha256':sha((OUT/'EXTENSION_EQUIVALENCE.json').read_bytes()),
        'installer_and_all_prior_transforms_identical':True}
    (OUT/'VALIDATION.json').write_bytes(encoded(validation))
    handoff=json.loads((OUT/'HANDOFF.json').read_bytes())
    assert len(validation['variants'])==handoff['known_code_signatures']
    assert all(row['passed'] for row in validation['variants'])
    assert '5 passed' in (AUDIT/'gate-budget-r15-final.log').read_text()
    assert '63 passed' in (AUDIT/'working-tests.log').read_text()
    pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    assert sha(pointer.read_bytes())==handoff['local_active_pointer_sha256']
    run=OUT/(NAME+'_RUN.txt');workflow=OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')
    assert sha(run.read_bytes())==handoff['run_txt_sha256']
    assert sha(workflow.read_bytes())==handoff['workflow_txt_sha256']
    subprocess.run(['bash','-n',str(run)],check=True)
    ast.parse(workflow.read_text(),feature_version=(3,10))
    prerequisite=OUT/'GENOS_DB_LOG_ROLLBACK_20261007_R3_RUN.txt'
    shutil.copyfile(OUT.with_name('db_log_rollback_20261007_r3')/prerequisite.name,prerequisite)
    subprocess.run(['bash','-n',str(prerequisite)],check=True)
    example=OUT/(NAME+'_EXAMPLE.png')
    shutil.copyfile(ROOT/'09_ARTIFACTS/AUDITS/20261008-rag-flow-svg-r9/모의-두갈래-근거.png',example)
    summary=OUT/'VALIDATION_SUMMARY.txt'
    summary.write_text('GENOS SVG R9 + 핵심 진행 표시 재반영 R3 검증\n\n'
        +'확인한 코드 지문: '+str(len(validation['variants']))+'종\n'
        +'동일 설치기 check/apply/재실행/verify/undo/변조 거부: 기존69종/690명령 + 최종 확장 TXT의 R15 12종/120명령 통과\n'
        +'설치기·기존69종 모든 변환/결과/소스 불변을 EXTENSION_EQUIVALENCE.json으로 확인\n'
        +'코드 계열별 표시·진행·JSON/SSE/분리 소비자: '+str(len(validation['contracts']))+'계열, 각63개 통과\n'
        +'현재 작업 코드의 같은 계약: 63개 통과\n'
        +'동일 committed checkout의 모의 generation gate: 검색 캐시 R3/R4·시스템 로그 R1, 3개 통과\n'
        +'CM R14/R15의 조사 예산·service.py·선택 generation binding 보존 및 후속 미확인 수정 거부: 2개 통과\n'
        +'R15가 보존한 오류 로그 R10의 전체 오류 원문·보고서·model 오류·해시 pin 유지 확인\n'
        +'단위 원문·CURRENT·모의 runtime/SQL 파일 보존, 현재 실행 entrypoint/표시 R9·모든 profile pin 확인\n'
        +'Bash 문법 및 Python3.10 워크플로우 문법 통과, JavaScript 첨부·ZIP member 없음\n'
        +'신규 모델 호출0회. 로컬 MAIN45 및 실제 NFS generation/CURRENT는 변경하지 않음\n'
        +'GENOS 실제 반입/commit/push/리비전/워크플로우 화면/NFS 상태는 미확인\n\n'
        +'실행 ZIP은 TRANSFER용 패치/검증 묶음입니다. DEV에는 RUN으로 적용합니다.\n'
        +'실제 적용 후 APPLIED_CODE.zip은 해당 DEV에서 만들어 같은 checkout gate에 사용합니다.\n'
        +'분리 워크플로우 편집기는 WORKFLOW_PASTE_ALL.txt를 별도로 반영해야 합니다.\n'
        +'첨부 PNG는 모의 규정의 표시 예시이며 실제 내부 모델 결과가 아닙니다.\n\n'
        +'작업 중 실패 이력은 PREVIOUS_FAILURE.txt와 원래 감사 로그에 보존했습니다.\n')
    (OUT/'PREVIOUS_FAILURE.txt').write_text('R3 로컬 반입 검증 중의 실패 이력 — 미발송 staging\n\n'
        +'1. 기존 SSE 오류 안내 문자열 fixture를 현재 전체 오류 표시 계약으로 갱신했습니다. 오류 상태와 원문은 유지합니다.\n'
        +'2. 가장 초기 코드 ZIP은 WORKSPACE pin 차이가 있어 직접 허용하지 않았습니다. 기존 검증한 선행 DB 로그 롤백 R3 경로를 안내합니다.\n'
        +'3. Bash 초기 로그 수집이 child의 stderr를 합치던 부분을 수정해 원본 stdout/stderr를 따로 보존했습니다.\n'
        +'4. CM inventory의 JSON 키 순서가 코드 지문에 영향을 주던 부분을 정렬한 내용 기반 지문으로 수정했습니다.\n'
        +'5. gate fixture 최초 수집의 PYTHONPATH 오류를 로컬 검사 실행 환경에서 수정했습니다. 현장 TXT에는 WSL 전용 경로를 넣지 않습니다.\n\n'
        +'감사 로그: 09_ARTIFACTS/AUDITS/20261008-rag-progress-graph-r3-delivery/\n'
        +'이 파일에 적힌 실패 상태는 보내지 않았으며 최종 같은 RUN의 재검증 통과를 확인한 뒤 봉인합니다.\n')
    members={name:path.read_bytes() for name,path in {
        'apply_display.py':OUT/'apply_display.py','PATCH_SPEC.json.gz':OUT/'PATCH_SPEC.json.gz',
        'SOURCE_BINDING.json':OUT/'SOURCE_BINDING.json',run.name:run,workflow.name:workflow,
        'EXTENSION_EQUIVALENCE.json':OUT/'EXTENSION_EQUIVALENCE.json','VALIDATION_EXTENSION.json':OUT/'VALIDATION_EXTENSION.json',
        prerequisite.name:prerequisite,'GUIDE_UTF8.txt':OUT/'GUIDE_UTF8.txt',
        'VALIDATION_SUMMARY.txt':summary,'VALIDATION.json':OUT/'VALIDATION.json',
        'PREVIOUS_FAILURE.txt':OUT/'PREVIOUS_FAILURE.txt',example.name:example}.items()}
    for path in sorted((OUT/'payload').rglob('*')):
        if path.is_file():members[path.relative_to(OUT).as_posix()]=path.read_bytes()
    assert all(Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for name in members)
    manifest={'schema_version':'genos-display-delivery-v1','id':NAME,'purpose':'TRANSFER runnable display-only overlay; use RUN on existing DEV',
              'files':[{'path':name,'bytes':len(raw),'sha256':sha(raw)} for name,raw in sorted(members.items())],
              'display_revision':handoff['display_revision'],'progress_revision':handoff['progress_revision'],
              'known_code_signatures':handoff['known_code_signatures'],'field_deployed':False}
    members['CODE_MANIFEST.json']=encoded(manifest)
    members['PACKAGE_SHA256SUMS.txt']=''.join(sha(raw)+'  '+name+'\n' for name,raw in sorted(members.items())).encode()
    (OUT/'CODE_MANIFEST.json').write_bytes(members['CODE_MANIFEST.json'])
    (OUT/'PACKAGE_SHA256SUMS.txt').write_bytes(members['PACKAGE_SHA256SUMS.txt'])
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(members.items()):z.writestr(name,raw)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist())==set(members)
        assert z.read(run.name)==run.read_bytes() and z.read(workflow.name)==workflow.read_bytes()
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    sums=OUT/'SHA256SUMS.txt'
    external=(archive,run,workflow,prerequisite,OUT/'GUIDE_UTF8.txt',summary,example)
    sums.write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in external))
    handoff.update(code_zip_sha256=sha(archive.read_bytes()),code_zip_bytes=archive.stat().st_size,
                   code_manifest_sha256=sha(members['CODE_MANIFEST.json']),zip_members=len(members),
                   validation={'signatures':len(validation['variants']),'txt_commands':validation['txt_commands'],
                               'contract_families':len(validation['contracts']),'contracts_each':63,'generation_budget_tests':5,
                               'prior69_transforms_unchanged':True,'final_extension_txt_commands':extension['txt_commands']})
    (OUT/'HANDOFF.json').write_bytes(encoded(handoff))
    paths=(*external,sums)
    attachments=[{'path':str(p),'filename':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),
                  'mime_type':'application/zip' if p.suffix=='.zip' else 'image/png' if p.suffix=='.png' else 'text/plain'} for p in paths]
    (OUT/'EMAIL_ATTACHMENTS.json').write_bytes(encoded(attachments))
    payload={'to':'hyungjininfocz.son@partner.samsung.com',
             'subject':'[8-AGENT] SVG R9 개선본 + 짧은 진행 로그 재반영 R3 — 이전 R2 대신 적용',
             'reply_message_id':'1a11580903a8c6a3','response_fields':['id','thread_id','label_ids'],
             'payload':{'mime_type':'multipart/mixed','parts':[{'mime_type':'text/html','charset':'UTF-8',
                 'body':{'content':(OUT/'EMAIL_BODY.html').read_text()}}]}}
    for row in attachments:
        payload['payload']['parts'].append({'mime_type':row['mime_type'],'filename':row['filename'],
             'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(Path(row['path']).read_bytes()).decode().rstrip('=')}})
    (OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=True,separators=(',',':')))
    print(json.dumps({'zip_bytes':archive.stat().st_size,'members':len(members),'attachments':len(attachments),
                      'attachment_bytes':sum(r['bytes'] for r in attachments),'mail_payload_bytes':(OUT/'EMAIL_PAYLOAD.json').stat().st_size}))

if __name__=='__main__':main()
