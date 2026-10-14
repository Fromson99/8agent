"""Repackage the immutable tested R1 as a ZIP with runnable TXT inside/outside."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
PREV = OUT.parent / 'data_transfer_list_20261007_r1'
PARTS = OUT.parent / 'zip_parts_bash_20261007_r4'
NAME = 'GENOS_TRANSFER_NFS_LIST_20261007_R3'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
dump = lambda obj: (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    archive_path = OUT / (NAME + '.zip')
    if archive_path.exists():
        raise FileExistsError('Published packages are immutable; use a new revision')
    original = json.loads((PREV / 'HANDOFF.json').read_text())
    runner = (PREV / 'GENOS_TRANSFER_NFS_LIST_20261007_R1_RUN.txt').read_bytes()
    assert sha(runner) == original['runner_sha256']
    guide = f'''GENOS 데이터 분할 → DEV → NFS → 워크플로우 목록: ZIP 인계 R3

이번에는 R3 ZIP을 사용하세요. 이전 R1 TXT 단독 인계를 대신하는 포장 변경입니다.
실행 코드와 NFS 경로는 검증한 R1 그대로입니다. ZIP 내부 RUN.txt와 별도 첨부
RUN.txt는 같은 바이트입니다. 별도 TXT를 Bash가 읽지 못하면 ZIP을 코드스페이스에
올리고 거기서 해제한 내부 RUN.txt를 사용합니다. 확장자는 .txt 그대로 둡니다.
코드 ZIP 안에는 실행 TXT, 안내, 분할/병합 TXT, 코드 manifest, SHA256SUMS.txt가 있습니다.
운영 데이터는 이 코드 ZIP에 포함하지 않습니다. 기존 데이터 .zip.parts 폴더를 별도로
~/DEV/TRANSFER에 올리고 모든 조각과 PARTS.sha256, ORIGINAL.sha256을 보존하세요.

1. 첨부 {NAME}.zip을 대상 코드스페이스의 ~/DEV/TRANSFER에 올립니다.
   Windows에서 해제/재저장하지 않고 코드스페이스 터미널에서 해제합니다.

cd ~/DEV
python3 -m zipfile -e TRANSFER/{NAME}.zip TRANSFER/{NAME}
(cd TRANSFER/{NAME} && sha256sum -c SHA256SUMS.txt)

2. ZIP 안에서 꺼낸 실행 TXT로 검사합니다. 질문에는 실제 .zip.parts 폴더 이름을 입력합니다.

bash TRANSFER/{NAME}/{NAME}_RUN.txt inspect

사진에 있던 데이터 폴더를 그대로 사용한다면:
bash TRANSFER/{NAME}/{NAME}_RUN.txt inspect genos-rag-data-20261007T002029Z-7c0b050f.zip.parts

3. 변경 보고서를 검토하고 대상 RAG/AD 쓰기를 정상 종료한 뒤 복원/준비/push합니다.

bash TRANSFER/{NAME}/{NAME}_RUN.txt all --writers-stopped --accept-live-archive

실제 팀 문서명을 확인하려면 --team-id 실제팀명 을 추가합니다.
경로: /nfs-root/diamo/8-agent
generation: /nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation
runtime: /nfs-root/diamo/8-agent/runtime
별도 state: 미설정

출력된 RUN_DIR/STATUS.json과 commit을 확인합니다. 코드서빙은 해당 commit으로
새 리비전을 배포하고 SERVING_ENV_PATHS.txt를 반영합니다. WORKFLOW_PASTE_ALL.txt
전체를 워크플로우 Python 단계에 별도로 붙여 넣고 워크플로우 테스트 화면에서 확인합니다.
기존 GENOS_BASE_URL, GENOS_CODESERVING_ID, 인증키 설정을 사용합니다.
코드 적용, NFS 복원, push, 코드서빙 리비전, 워크플로우 결과는 각각 확인합니다.

분할/병합 스크립트는 ZIP 안에 함께 넣었습니다. 이들은 기존 R4의 같은 바이트입니다.
bash TRANSFER/{NAME}/SPLIT_TRANSFER_ZIP.txt
bash TRANSFER/{NAME}/JOIN_TRANSFER_ZIP.txt "TRANSFER/자료.zip.parts"

기존 검증 코드의 기능 결과는 아래 R1 상세 안내를 따릅니다. R3는 포장 변경이며
ZIP 해제 뒤 해시/구문/실행 검사를 추가합니다. GENOS 현장 DRM/실행 성공은 미확인입니다.

----- 같은 실행 코드의 R1 상세 안내 (실행 경로는 위 R3 경로를 사용) -----
'''.encode() + (PREV / 'GENOS_TRANSFER_NFS_LIST_20261007_R1_GUIDE.txt').read_bytes()
    members = {
        NAME + '_RUN.txt': runner,
        NAME + '_GUIDE.txt': guide,
        'SPLIT_TRANSFER_ZIP.txt': (PARTS / 'SPLIT_TRANSFER_ZIP.txt').read_bytes(),
        'JOIN_TRANSFER_ZIP.txt': (PARTS / 'JOIN_TRANSFER_ZIP.txt').read_bytes(),
        'CODE_MANIFEST.json': (PREV / 'CODE_MANIFEST.json').read_bytes(),
    }
    assert sha(members['CODE_MANIFEST.json']) == original['code_manifest_sha256']
    for name, raw in members.items():
        assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
        (OUT / name).write_bytes(raw)
        if name.endswith('_RUN.txt') or name in ('SPLIT_TRANSFER_ZIP.txt', 'JOIN_TRANSFER_ZIP.txt'):
            subprocess.run(['bash', '-n', str(OUT / name)], check=True)
    members['SHA256SUMS.txt'] = ''.join(f'{sha(raw)}  {name}\n' for name, raw in sorted(members.items())).encode()
    (OUT / 'SHA256SUMS.txt').write_bytes(members['SHA256SUMS.txt'])
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(members.items()):
            archive.writestr(name, raw)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(members)
        assert all(archive.read(name) == raw for name, raw in members.items())
    handoff = {
        **original, 'version': NAME, 'parent': original['version'],
        'packaging_only': True, 'runner_bytes_identical_to_r1': True,
        'runner_name': NAME + '_RUN.txt', 'zip_sha256': sha(archive_path.read_bytes()),
        'zip_members': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in members.items()},
        'email_attachments_plain_txt_only': False,
        'preferred_execution': 'Extract ZIP in GENOS codespace and execute its internal RUN TXT',
        'field_drm_verified': False,
    }
    (OUT / 'HANDOFF.json').write_bytes(dump(handoff))
    body = f'''<p>요청하신 기존 방식대로 <b>ZIP + 별도 실행 TXT + 안내 TXT</b>로 다시 보냅니다.
이번 <b>R3 ZIP</b>을 사용하세요. 이전 R1 TXT 단독 인계를 대체합니다.
ZIP 안에도 전체 실행 TXT와 안내, 분할/병합 TXT를 넣었습니다. 코드와 NFS 경로는
검증한 R1 그대로이며 기존 데이터를 변경한 새 버전은 아닙니다.</p>
<p>ZIP과 기존 데이터 .zip.parts 폴더를 <b>~/DEV/TRANSFER</b>에 올리고,
<b>코드스페이스 터미널에서 ZIP을 해제한 내부 TXT</b>를 실행하세요.</p>
<pre>cd ~/DEV
python3 -m zipfile -e TRANSFER/{NAME}.zip TRANSFER/{NAME}
(cd TRANSFER/{NAME} &amp;&amp; sha256sum -c SHA256SUMS.txt)
bash TRANSFER/{NAME}/{NAME}_RUN.txt inspect</pre>
<p>질문에는 실제 데이터 .zip.parts 폴더 이름을 넣습니다. 사진의 이름은
genos-rag-data-20261007T002029Z-7c0b050f.zip.parts 입니다. 모든 조각과
PARTS.sha256, ORIGINAL.sha256이 있어야 합니다.</p>
<p>검사 보고서 검토 및 대상 쓰기 정상 종료 후:</p>
<pre>bash TRANSFER/{NAME}/{NAME}_RUN.txt all --writers-stopped --accept-live-archive</pre>
<p>이후 출력된 commit으로 코드서빙 새 리비전 배포, SERVING_ENV_PATHS.txt 설정,
WORKFLOW_PASTE_ALL.txt 편집기 반영, 워크플로우 테스트 화면 확인을 진행합니다.
팀 문서명을 원하면 실제 --team-id 값을 추가하세요. 자세한 내용은 ZIP 내부 안내를 따릅니다.</p>
<p>NFS root /nfs-root/diamo/8-agent와 기존 generation/runtime, state 미설정을 유지합니다.
운영 데이터는 첨부 코드 ZIP에 포함하지 않았습니다. ZIP 내부 파일의 동일 바이트·해시·
스크립트 구문과 해제한 실행본 검사를 확인했습니다. GENOS 현장 DRM·복원·배포 성공은
현장 확인 전까지 미확인입니다.</p>'''
    attachments = [archive_path, OUT / (NAME + '_RUN.txt'), OUT / (NAME + '_GUIDE.txt')]
    request = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[8-AGENT] 분할 ZIP → NFS → 데이터 목록 R3 — 기존 ZIP 인계 방식',
        'reply_message_id': '1a115df82c32b2f5',
        'payload': {'mime_type': 'multipart/mixed', 'parts': [
            {'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}},
            *[{'mime_type': 'application/zip' if p.suffix == '.zip' else 'text/plain',
                'charset': None if p.suffix == '.zip' else 'UTF-8',
                'filename': p.name, 'content_disposition': 'attachment',
                'body': {'base64_url_content': base64.urlsafe_b64encode(p.read_bytes()).decode()}}
              for p in attachments]]}}
    (OUT / 'EMAIL_REQUEST.json').write_bytes(dump(request))
    print(json.dumps({'version': NAME, 'attachments': [p.name for p in attachments],
        'runner_sha256': sha(runner), 'zip_sha256': handoff['zip_sha256'],
        'zip_bytes': archive_path.stat().st_size}, ensure_ascii=False))


if __name__ == '__main__':
    main()
