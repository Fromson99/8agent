"""Samsung ZIP + separate runnable TXT handoff; no operating data."""
import base64, hashlib, json, subprocess, tempfile, zipfile
from pathlib import Path

OUT=Path(__file__).resolve().parent
NAME='JOIN_VERIFY_RECOVER_20261007_R1'
DATA='genos-rag-data-20261007T002029Z-7c0b050f'
R3='GENOS_TRANSFER_NFS_LIST_20261007_R3'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
dump=lambda obj:(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()

def main():
    archive=OUT/(NAME+'.zip')
    if archive.exists():raise FileExistsError('Frozen handoff; use another revision')
    runner=OUT/(NAME+'_RUN.txt')
    validated=json.loads((OUT/'VALIDATION.json').read_text())
    assert validated['runner_sha256']==sha(runner.read_bytes()) and validated['passed']==12
    guide=f'''분할 조각 크기 제한 없이 전체 원본 SHA로 확인하는 병합·복구 도구

기존 NFS/코드서빙 R3 실행본은 유지하고, 병합만 이번 보조 도구로 먼저 수행합니다.
사진의 part000030은 49,000,001 bytes이고 다른 조각은 SHA가 일치했습니다.
Windows의 47,852KB 표시는 반올림이므로 1바이트 차이를 구별하지 못합니다.

1. {NAME}.zip을 ~/DEV/TRANSFER에 올리고 코드스페이스 터미널에서 해제합니다.

cd ~/DEV
python3 -m zipfile -e TRANSFER/{NAME}.zip TRANSFER/{NAME}
(cd TRANSFER/{NAME} && sha256sum -c SHA256SUMS.txt)
bash TRANSFER/{NAME}/{NAME}_RUN.txt {DATA}.zip.parts

다른 데이터면 마지막 .zip.parts 이름만 바꿉니다. 인자를 생략하면 이름을 질문합니다.
조각/원본 해시 파일을 읽고 크기 상한 없이 현재 조각의 병합 SHA를 먼저 계산합니다.
전체 SHA가 ORIGINAL.sha256과 같으면 그대로 VERIFIED_ZIP을 생성합니다.
불일치 시 한 조각의 끝 1바이트를 제외한 내용이 PARTS.sha256의 해당 원본 해시와
일치하는 경우만 복원 후보로 선택합니다. 후보 전체 SHA도 ORIGINAL.sha256과 같아야
출력합니다. 원본 조각/메타데이터는 수정하지 않습니다. 1바이트가 어디서 추가됐는지
확정하지 않으며 중간 삽입/다른 내용 변경/여러 조각 변경은 복원 성공으로 처리하지 않습니다.

성공 시 기존 조각 폴더의 상위 TRANSFER에 {DATA}_verified.zip 및 .zip.sha256이 생깁니다.
기존 동일 ZIP은 해시 확인 후 재사용하고 다른 파일은 덮어쓰지 않습니다.
실패하면 RUN.log/STATUS.json/EXIT_STATUS.json을 확인합니다. 후보가 원본 SHA와 다르면
데이터 복원으로 진행하지 않고 해당 조각을 다시 반입해야 합니다.

2. 성공 출력의 VERIFIED_ZIP 경로를 기존 R3에 직접 전달합니다. 조각 폴더를 다시 지정하면
원본 part000030이 보존되어 있으므로 기존 PARTS.sha256 검사에서 다시 실패합니다.

cd ~/DEV
bash TRANSFER/{R3}/{R3}_RUN.txt inspect TRANSFER/{DATA}_verified.zip

3. 검사 보고서 검토/대상 RAG·AD 쓰기 정상 종료 후:
bash TRANSFER/{R3}/{R3}_RUN.txt all TRANSFER/{DATA}_verified.zip --writers-stopped --accept-live-archive

기존 R3 안내대로 정확한 commit의 새 코드서빙 리비전, SERVING_ENV_PATHS.txt,
WORKFLOW_PASTE_ALL.txt 편집기 반영과 워크플로우 테스트 화면을 각각 확인합니다.
새 도구는 코드 적용/Git/NFS를 변경하지 않습니다. FINAL ZIP을 R3에 넘긴 후의 복원은 별도입니다.

모의 검사12개: 정상 병합, 49MB 초과 원본 해시 일치, 30번 끝 추가 1바이트 복원,
재실행, 중간 삽입/내용 변경/복수 변경/전체 SHA 불일치/누락/추가/심볼릭 링크 차단,
다른 기존 출력 보존. 원본 조각 불변과 R3의 직접 ZIP 입력 소비를 확인했습니다.
GENOS 현장 원인/복구·복원·배포 성공은 아직 미확인입니다.
'''
    (OUT/(NAME+'_GUIDE.txt')).write_text(guide,encoding='utf-8')
    members={p.name:p.read_bytes() for p in (runner,OUT/(NAME+'_GUIDE.txt'),OUT/'VALIDATION.json')}
    assert all(Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for name in members)
    members['SHA256SUMS.txt']=''.join(f'{sha(raw)}  {name}\n' for name,raw in sorted(members.items())).encode()
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in members.items():z.writestr(name,raw)
    with tempfile.TemporaryDirectory(prefix='join-delivery-extract-') as temporary:
        extracted=Path(temporary)
        subprocess.run(['python3','-m','zipfile','-e',str(archive),str(extracted)],check=True)
        subprocess.run(['sha256sum','-c','SHA256SUMS.txt'],cwd=extracted,capture_output=True,check=True)
        subprocess.run(['bash','-n',str(extracted/runner.name)],check=True)
        assert (extracted/runner.name).read_bytes()==runner.read_bytes()
    record={'version':NAME,'zip_sha256':sha(archive.read_bytes()),'runner_sha256':sha(runner.read_bytes()),
            'members':{name:{'bytes':len(raw),'sha256':sha(raw)} for name,raw in members.items()},
            'validated_tests':12,'zip_extraction_and_syntax_verified':True,'operating_data_included':False,
            'field_execution':False,'nfs_changed':False,'git_changed':False,'genos_main_changed':False,
            'existing_r3_runner_unchanged':True,'original_parts_preserved':True}
    (OUT/'HANDOFF.json').write_bytes(dump(record))
    body=f'''<p>사진에서 30번 조각이 49,000,001바이트이며 SHA가 달랐습니다. Windows의 KB
표시는 반올림이어서 1바이트 차이는 보이지 않습니다. 전달 중 증가했는지 편집됐는지는 미확인입니다.</p>
<p>요청하신 대로 <b>크기 상한 없이 전체 병합 SHA로 판정하는 보조 도구</b>를 보냅니다.
그대로 합친 SHA가 원본과 같으면 사용합니다. 다른 경우 한 조각의 끝 1바이트를 제외한
내용이 해당 원본 조각 SHA 및 전체 ZIP SHA와 모두 같을 때만 복원합니다.
<b>현재 조각 파일은 그대로 보존</b>하고 새 _verified.zip을 만듭니다.</p>
<pre>cd ~/DEV
python3 -m zipfile -e TRANSFER/{NAME}.zip TRANSFER/{NAME}
(cd TRANSFER/{NAME} &amp;&amp; sha256sum -c SHA256SUMS.txt)
bash TRANSFER/{NAME}/{NAME}_RUN.txt {DATA}.zip.parts</pre>
<p>성공하여 VERIFIED_ZIP이 출력되면 <b>조각 폴더 대신 새 ZIP을 기존 R3에 직접 지정</b>합니다.</p>
<pre>bash TRANSFER/{R3}/{R3}_RUN.txt inspect TRANSFER/{DATA}_verified.zip</pre>
<p>이후 보고서 검토와 대상 쓰기 정상 종료 후의 all 명령, 리비전 배포와 워크플로우 반영은
첨부 안내를 따릅니다. ZIP+별도 실행 TXT+안내 TXT 세 첨부이며 ZIP 안에도 실행/안내가
있습니다. 모의 검사12개와 ZIP 해제/해시/구문을 확인했습니다. 현장 복원·배포 성공은 미확인입니다.</p>'''
    attachments=[archive,runner,OUT/(NAME+'_GUIDE.txt')]
    request={'to':'hyungjininfocz.son@partner.samsung.com',
             'subject':'[8-AGENT] 30번 조각 검증 병합·추가 1바이트 복구 — 원본 SHA 일치 필수',
             'reply_message_id':'1a1165280958c314',
             'payload':{'mime_type':'multipart/mixed','parts':[
                 {'mime_type':'text/html','charset':'UTF-8','body':{'content':body}},
                 *[{'mime_type':'application/zip' if p.suffix=='.zip' else 'text/plain',
                     'charset':None if p.suffix=='.zip' else 'UTF-8','filename':p.name,
                     'content_disposition':'attachment',
                     'body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}}
                    for p in attachments]]}}
    (OUT/'EMAIL_REQUEST.json').write_bytes(dump(request))
    print(json.dumps({'version':NAME,'attachments':[p.name for p in attachments],
                      'zip_bytes':archive.stat().st_size,'tests':12}))

if __name__=='__main__':main()
