"""Seal the tested R4 RUN and prepare the authorized Samsung email."""
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261008-rag-progress-graph-r4-delivery'
NAME = 'GENOS_RAG_PROGRESS_GRAPH_20261008_R4'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda obj: (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    archive = OUT / (NAME + '.zip')
    assert not archive.exists(), 'Preserve an already sealed ZIP'
    handoff = json.loads((OUT / 'HANDOFF.json').read_bytes())
    static = json.loads((OUT / 'STATIC_VALIDATION.json').read_bytes())
    validation = json.loads((OUT / 'VALIDATION.json').read_bytes())
    origin = json.loads((AUDIT / 'ORIGIN.json').read_bytes())
    prior_zip = ROOT / origin['prior_delivery'] / 'GENOS_RAG_PROGRESS_GRAPH_20261008_R3.zip'
    assert sha(prior_zip.read_bytes()) == origin['prior_zip_sha256']
    assert len(static['variants']) == handoff['known_code_signatures'] == 123
    assert all(row['passed'] for row in static['variants'])
    assert all(row['passed'] for row in validation['variants'])
    assert validation['txt_commands'] == 10 * len(validation['variants'])
    assert len(validation['contracts']) == 9
    assert all('69 passed' in row['output'] for row in validation['contracts'])
    assert '6 passed' in (AUDIT / 'gate-budget.log').read_text()
    source_audit = ROOT / origin['source_audit']
    working = json.loads((source_audit / 'WORKING_BINDING.json').read_bytes())
    assert working['tests_passed'] == 69 and working['service_calls_per_request'] == 1
    for name, expected in working['working_source_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    # Logger modules are taken from the immutable original handoff, rather
    # than from unrelated, more recent working files.
    for name, expected in handoff['source_sha256'].items():
        raw = (OUT / 'payload' / name).read_bytes()
        assert sha(raw) == expected, name
        if name not in {'genos_diagnostics.py', 'genos_log_runner.py'}:
            assert sha((ROOT / name).read_bytes()) == expected, name
        if name.endswith('.py'):
            ast.parse(raw, feature_version=(3, 10))
    pointer = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    assert sha(pointer.read_bytes()) == handoff['local_active_pointer_sha256']
    run = OUT / (NAME + '_RUN.txt')
    workflow = OUT / (NAME + '_WORKFLOW_PASTE_ALL.txt')
    assert sha(run.read_bytes()) == handoff['run_txt_sha256'] == validation['run_txt_sha256']
    assert sha(workflow.read_bytes()) == handoff['workflow_txt_sha256']
    subprocess.run(['bash', '-n', str(run)], check=True)
    ast.parse(workflow.read_text(), feature_version=(3, 10))
    assert '.venv/bin/python' not in run.read_text()
    prerequisite = OUT / 'GENOS_DB_LOG_ROLLBACK_20261007_R3_RUN.txt'
    shutil.copyfile(OUT.with_name('db_log_rollback_20261007_r3') / prerequisite.name, prerequisite)
    subprocess.run(['bash', '-n', str(prerequisite)], check=True)
    summary = OUT / 'VALIDATION_SUMMARY.txt'
    summary.write_text(
        'GENOS main_workflow.py 반영 적용 R4 검증\n\n'
        '패키지 R4 / 내부 서버 revision genos-external-workflow-svg-20261008-r3\n'
        'SVG judgment-knowledge-svg-20261008-r9 / 핵심 진행 rag-key-progress-20261007-r1\n'
        '전체 허용123종: 실제 설치기의 prepared()로 입력/출력 hash·엔진/스키마 pin·service/CM/선택 binding 정적 확인\n'
        f"실제 첨부 RUN: 대표{len(validation['variants'])}개 상태 / {validation['txt_commands']}개 명령 통과\n"
        '각 계열의 적용 전과 R3 적용 후 상태에서 check/apply/재실행/verify/undo/실제 변경 파일 및 백업 변조 거부 확인\n'
        '설치한9개 코드 계열: 각69개 표시/JSON/SSE/분리 소비자 계약 검사 통과\n'
        '현재 작업 코드의 같은69개 검사 통과, 기존 service 호출1회·원래 응답/상태 보존 확인\n'
        '현재 요청/응답/표시 SHA·revision 결속과 서버 표시 재사용/미일치 fallback·45,000자 오류 원문 보존 확인\n'
        '같은 committed checkout 모의 generation gate4개 및 CM R14/R15 예산/전체 오류 보존2개: 합계6개 통과\n'
        '모의 runtime 파일/CURRENT 보존, 설치 APPLIED_CODE.zip=실제DEV bytes 확인\n'
        'Bash 문법·Python3.10 문법·ZIP 무결성·추출 후 체크섬 검사 통과, JavaScript 첨부/ZIP member 없음\n'
        '신규 모델 호출0회. 로컬 MAIN45·실제 NFS generation/CURRENT·이전 발송 R3 ZIP 변경 없음\n'
        'GENOS 실제 반입/commit/push/리비전/워크플로우 화면 성공은 미확인\n\n'
        '이번 ZIP은 TRANSFER용 적용/검증 묶음입니다. 기존DEV에 RUN으로 적용합니다.\n'
        'RUN이 해당DEV에서 APPLIED_CODE.zip을 만들며 commit 후 같은 checkout/generation gate에 사용합니다.\n'
        '분리 워크플로우 편집기는 WORKFLOW_PASTE_ALL.txt 전체를 별도로 교체해야 합니다.\n'
        '전체123종의 정적 확인과 대표 상태의 실제 명령 실행을 구분합니다. 모든 조합을 현장에서 실행했다는 뜻이 아닙니다.\n'
        '테스트 fixture 실패 이력은 PREVIOUS_FAILURE.txt 및 원래 감사 로그에 보존했습니다.\n'
    )
    (OUT / 'PREVIOUS_FAILURE.txt').write_text(
        'R4 로컬 테스트 fixture 실패 이력 — 메일 발송 전\n\n'
        '1. 두 기존 subprocess 테스트가 ROOT/.venv/bin/python을 가정했습니다. 배포 코드에 없는 로컬 테스트 interpreter 링크만 제공해 재실행했습니다.\n'
        '2. R3 적용 후 R4는 PIPELINE pin을 바꾸지 않아 그 파일이 R4 원복 receipt에 없습니다. 변조 거부 검사의 대상만 모든 R4 recipe가 실제 변경하는 main_workflow.py로 고쳤습니다.\n'
        '두 수정 모두 검증 fixture의 변경입니다. 설치기/첨부 RUN/제품 코드 bytes는 그대로 두고 같은 RUN을 재검증했습니다.\n'
        '실패 원문과 hash는 09_ARTIFACTS/AUDITS/20261008-rag-progress-graph-r4-delivery/에 무손실 압축 보존했습니다.\n'
    )
    filenames = ['apply_display.py', 'PATCH_SPEC.json.gz', 'SOURCE_BINDING.json', run.name,
                 workflow.name, prerequisite.name, 'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt',
                 'VALIDATION.json', 'STATIC_VALIDATION.json', 'GATE_BUDGET_VALIDATION.json', 'PREVIOUS_FAILURE.txt']
    members = {name: (OUT / name).read_bytes() for name in filenames}
    for path in sorted((OUT / 'payload').rglob('*')):
        if path.is_file():
            members[path.relative_to(OUT).as_posix()] = path.read_bytes()
    assert all(Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for name in members)
    manifest = {'schema_version': 'genos-display-delivery-v1', 'id': NAME,
                'purpose': 'TRANSFER runnable display overlay; use RUN on existing DEV',
                'files': [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(members.items())],
                'display_revision': handoff['display_revision'], 'progress_revision': handoff['progress_revision'],
                'main_workflow_revision': handoff['main_workflow_revision'],
                'known_code_signatures': 123, 'field_deployed': False}
    members['CODE_MANIFEST.json'] = encoded(manifest)
    members['PACKAGE_SHA256SUMS.txt'] = ''.join(sha(raw) + '  ' + name + '\n' for name, raw in sorted(members.items())).encode()
    (OUT / 'CODE_MANIFEST.json').write_bytes(members['CODE_MANIFEST.json'])
    (OUT / 'PACKAGE_SHA256SUMS.txt').write_bytes(members['PACKAGE_SHA256SUMS.txt'])
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(members.items()):
            z.writestr(name, raw)
    with zipfile.ZipFile(archive) as z, TemporaryDirectory(prefix='display-r4-seal-') as td:
        assert z.testzip() is None and set(z.namelist()) == set(members)
        z.extractall(td)
        subprocess.run(['sha256sum', '-c', 'PACKAGE_SHA256SUMS.txt'], cwd=td, check=True, capture_output=True)
        for name, raw in members.items():
            assert (Path(td) / name).read_bytes() == raw
    sums = OUT / 'SHA256SUMS.txt'
    external = (archive, run, workflow, prerequisite, OUT / 'GUIDE_UTF8.txt', summary)
    sums.write_text(''.join(sha(p.read_bytes()) + '  ' + p.name + '\n' for p in external))
    subprocess.run(['sha256sum', '-c', str(sums)], cwd=OUT, check=True, capture_output=True)
    handoff.update(code_zip_sha256=sha(archive.read_bytes()), code_zip_bytes=archive.stat().st_size,
                   code_manifest_sha256=sha(members['CODE_MANIFEST.json']), zip_members=len(members),
                   validation={'static_signatures': 123, 'runtime_states': len(validation['variants']),
                               'txt_commands': validation['txt_commands'], 'contract_families': 9,
                               'contracts_each': 69, 'generation_budget_tests': 6},
                   prior_r3_zip_sha256=origin['prior_zip_sha256'])
    (OUT / 'HANDOFF.json').write_bytes(encoded(handoff))
    attachments = [{'path': str(p), 'filename': p.name, 'bytes': p.stat().st_size,
                    'sha256': sha(p.read_bytes()), 'mime_type': 'application/zip' if p.suffix == '.zip' else 'text/plain'}
                   for p in (*external, sums)]
    assert len(attachments) == 7
    (OUT / 'EMAIL_ATTACHMENTS.json').write_bytes(encoded(attachments))
    payload = {'to': 'hyungjininfocz.son@partner.samsung.com',
               'subject': '[8-AGENT] main_workflow.py 반영 적용 R4 — SVG R9·짧은 진행 로그, 이전 R3 대신',
               'reply_message_id': '1a118e1acfd55379', 'response_fields': ['id', 'thread_id', 'label_ids'],
               'payload': {'mime_type': 'multipart/mixed', 'parts': [{'mime_type': 'text/html', 'charset': 'UTF-8',
                            'body': {'content': (OUT / 'EMAIL_BODY.html').read_text()}}]}}
    for row in attachments:
        raw = Path(row['path']).read_bytes()
        data = base64.urlsafe_b64encode(raw).decode().rstrip('=')
        assert base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)) == raw
        payload['payload']['parts'].append({'mime_type': row['mime_type'], 'filename': row['filename'],
            'content_disposition': 'attachment', 'body': {'base64_url_content': data}})
    mail_raw = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode()
    (OUT / 'EMAIL_PAYLOAD.json').write_bytes(mail_raw)
    (OUT / 'EMAIL_PRE_SEND_CHECK.json').write_bytes(encoded({
        'payload_sha256': sha(mail_raw), 'payload_bytes': len(mail_raw), 'recipient': payload['to'],
        'subject': payload['subject'], 'attachments': attachments, 'model_calls': 0,
        'field_deployed': False, 'local_MAIN45_pointer_unchanged': True, 'prior_R3_zip_unchanged': True,
        'validation': handoff['validation'], 'zip_extracted_checksums': 'PASS'}))
    print(json.dumps({'zip_bytes': archive.stat().st_size, 'members': len(members), 'attachments': 7,
                      'attachment_bytes': sum(row['bytes'] for row in attachments), 'mail_payload_bytes': len(mail_raw),
                      'validation': handoff['validation']}))


if __name__ == '__main__':
    main()
