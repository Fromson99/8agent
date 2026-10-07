"""Build one immutable R4 handoff: R3 repair plus literal received LLM logging."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r3'
OUT = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-raw-log-r4'
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20260929-llm-raw-log'
BUNDLE_ID = 'genos-llm-raw-log-20260929-r4'
PREFIX = 'GENOS_MODEL_DECISION_REPAIR_RAW_LOG_20260929_R4'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    if (OUT / 'EMAIL_SENT.json').exists():
        raise ValueError('Sent R4 is immutable; create a new revision')
    spec = importlib.util.spec_from_file_location('raw_log_transform', SOURCE / 'bundle/decision_transform.py')
    transform = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transform)
    manifest = json.loads((SOURCE / 'bundle/SELECTIVE_MANIFEST.json').read_bytes())
    feature = manifest['features']['decision-repair']
    bundle = OUT / 'bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    for name in feature['assets']:
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((SOURCE / 'bundle' / name).read_bytes())
    apply = (SOURCE / 'bundle/apply.py').read_bytes().replace(
        b"BUNDLE_ID = 'genos-turn-intent-20260929-r3'", ("BUNDLE_ID = '" + BUNDLE_ID + "'").encode())
    assert BUNDLE_ID.encode() in apply
    (bundle / 'apply.py').write_bytes(apply)
    feature['assets']['apply.py'] = sha(apply)
    current = (ROOT / REPORT).read_bytes()
    poll = transform.node_for(current, '_LiveLog._poll_journal')
    helper = transform.snippet(current, poll.body[0])[2]
    assert b'def raw_model_block(' in helper
    sources = [('audit-before', (AUDIT / 'before' / REPORT).read_bytes())]
    for folder in (
        '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-20260929-r1/code',
        '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-repair-20260929-r1/code',
        '08_DEPLOYMENT/GENOS/patches/response_overhead_20260928_r3/payload',
        '08_DEPLOYMENT/GENOS/patches/team_request_logs_20260928_r1/payload',
        '08_DEPLOYMENT/GENOS/patches/thinking_log_20260928_r2/payload',
    ):
        path = ROOT / folder / REPORT
        if path.is_file():
            sources.append((folder, path.read_bytes()))
    for path in sorted((ROOT / '08_DEPLOYMENT/GENOS/patches/response_overhead_20260928_r3').glob(
            '*/**/request_report.py')):
        sources.append((str(path.relative_to(ROOT)), path.read_bytes()))
    with zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFFS/20260929-rag-main-integrated/code.zip') as zipped:
        sources.append(('integrated-mail-code.zip', zipped.read(REPORT)))
    variants = {name: [] for name in ('_LiveLog._poll_journal', 'live_log')}
    seen = {name: set() for name in variants}
    provenance = []
    for label, raw in sources:
        modified = raw
        original_poll = transform.node_for(raw, '_LiveLog._poll_journal')
        assert original_poll is not None, 'missing journal reader: ' + label
        start, end, method = transform.snippet(raw, original_poll)
        marker = b'    def _poll_journal(self) -> None:\n'
        assert method.count(marker) == 1, 'unknown reader header: ' + label
        method = method.replace(marker, marker + helper + b'\n', 1)
        anchor = re.search(rb'(?m)^([ \t]*)blocks\.append\(\(seq, [\"\']MODEL RESPONSE / LLM ANSWER', method)
        assert anchor, 'unknown model response reader: ' + label
        indent = anchor[1]
        view = b'presented' if b'presented = {}' in method else b'{}'
        injection = (indent + b"blocks.append((seq, 'MODEL RAW RESPONSE',\n" +
                     indent + b'               raw_model_block(data, phase, ' + view + b'), stamp))\n')
        method = method[:anchor.start()] + injection + method[anchor.start():]
        lines = modified.splitlines(keepends=True)
        modified = b''.join(lines[:start]) + method + b''.join(lines[end:])
        marker = b'    handler = _LiveLog(request_id, stream, runtime)\n'
        assert modified.count(marker) == 1, 'unknown live-log constructor: ' + label
        modified = modified.replace(marker, marker + b'    handler.log_path = path\n', 1)
        compile(modified, '<raw-log-variant>', 'exec')
        for name in variants:
            before = transform.signature(transform.node_for(raw, name))
            after_node = transform.node_for(modified, name)
            after = transform.signature(after_node)
            provenance.append({'path': REPORT, 'qualified': name, 'source': label,
                'source_sha256': sha(raw), 'before_ast': before, 'after_ast': after})
            if before in seen[name]:
                continue
            seen[name].add(before)
            asset = 'raw-log/' + name.replace('.', '-') + '-' + str(len(variants[name])) + '.py'
            path = bundle / asset
            path.parent.mkdir(parents=True, exist_ok=True)
            snippet = transform.snippet(modified, after_node)[2]
            path.write_bytes(b'class _LiveLog:\n' + snippet if name.startswith('_LiveLog.') else snippet)
            feature['assets'][asset] = sha(path.read_bytes())
            variants[name].append({'before_ast': before, 'after_ast': after, 'after': asset})
    feature['files'][REPORT] = {'nodes': [
        {'qualified': name, 'variants': rows, 'optional': False} for name, rows in variants.items()]}
    feature['source_patch'] = 'model-decision-repair-raw-log-20260929-r4'
    manifest.update(bundle=BUNDLE_ID, handoff_revision='MODEL_DECISION_REPAIR_R4_LLM_RAW',
                    raw_log_variant_sources=provenance)
    (bundle / 'SELECTIVE_MANIFEST.json').write_bytes(dump(manifest))
    names = sorted(set(feature['assets']) | {'SELECTIVE_MANIFEST.json'})
    rows = [{'path': name, 'bytes': len((bundle / name).read_bytes()),
             'sha256': sha((bundle / name).read_bytes())} for name in names]
    archive = OUT / (PREFIX + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for row in rows:
            assert Path(row['path']).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs')
            zipped.write(bundle / row['path'], row['path'])
        zipped.writestr('CODE_MANIFEST.json', dump({'format': '8agent-code/1', 'patch': BUNDLE_ID, 'files': rows}))
    old_zip = SOURCE / 'GENOS_MODEL_DECISION_REPAIR_20260929_R3.zip'
    txt = (SOURCE / 'GENOS_MODEL_DECISION_REPAIR_20260929_R3_APPLY.txt').read_text()
    txt = txt.replace('GENOS_MODEL_DECISION_REPAIR_20260929_R3', PREFIX)
    txt = txt.replace(sha(old_zip.read_bytes()), sha(archive.read_bytes()))
    txt = txt.replace('MODEL_DECISION_REPAIR R3 INTENT_ACTION', 'MODEL_DECISION_REPAIR R4 LLM_RAW')
    txt = txt.replace('genos-turn-intent-20260929-r3', BUNDLE_ID)
    txt = txt.replace('# R2 적용 후에도 발생한 intent/actions 충돌을 같은 입력에서 모델에 재수정 요청합니다.',
        '# R2/R3 대신 이 R4를 사용합니다. 기존 판단 수정 + intent/actions 수정 + 수신 응답 원문 로그를 포함합니다.')
    txt = txt.replace('# 기존 R2 수정 기능을 포함합니다. 사진 기준 코드·R2 적용 코드·통합판을 지원합니다.',
        '# 기존 ~/DEV에 백업 후 필요한 함수만 적용합니다. 코드 commit/push와 새 서빙 리비전 배포가 필요합니다.\n'
        '# 배포 후 워크플로우 테스트 화면에서 재현하고 요청 .log의 MODEL RAW RESPONSE를 확인합니다.\n'
        '# 같은 폴더/파일명 .llm_raw.jsonl에 호출별 원문·재시도·finish_reason·수신 본문이 저장됩니다.\n'
        '# 이 원문은 LLM 서빙에서 받은 값입니다. 가드레일 적용 전 내부 출력 복원은 아닙니다.')
    path = OUT / (PREFIX + '_APPLY.txt')
    path.write_text(txt)
    subprocess.run(['bash', '-n', str(path)], check=True)
    (OUT / 'CODE_MANIFEST.json').write_bytes(dump({'format': '8agent-code/1', 'patch': BUNDLE_ID, 'files': rows}))
    (OUT / 'DELIVERY.json').write_bytes(dump({
        'patch': BUNDLE_ID, 'zip': archive.name, 'zip_sha256': sha(archive.read_bytes()),
        'txt': path.name, 'txt_sha256': sha(path.read_bytes()),
        'source_r3_sha256': sha(old_zip.read_bytes()), 'changed_runtime_files': list(feature['files']),
        'code_root': str(ROOT), 'commit': None, 'selected_generation': None,
        'generation_manifest_sha256': None, 'code_serving_revision': None,
        'generation_modified': False, 'workflow_modified': False,
        'email_sent': False, 'genos_deployed': False,
    }))
    print(json.dumps({'zip': str(archive), 'txt': str(path), 'sha256': sha(archive.read_bytes()),
                      'raw_log_variants': {name: len(rows) for name, rows in variants.items()}}))


if __name__ == '__main__':
    main()
