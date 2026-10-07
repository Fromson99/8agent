"""Create R3 from immutable R2, adding same-view intent/action correction."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r2'
OUT = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r3'
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20260929-turn-intent-repair'
BUNDLE_ID = 'genos-turn-intent-20260929-r3'
PREFIX = 'GENOS_MODEL_DECISION_REPAIR_20260929_R3'
OLD_PROMPT = (
    'DRAFT when sufficient or bounded; CLARIFY only for decisive missing user facts. Neither executes tools. ')
NEW_PROMPT = (
    'If actions is non-empty, intent MUST be CONTINUE; inspect their results in the next turn. '
    'DRAFT when sufficient or bounded; CLARIFY only for decisive missing user facts. '
    'DRAFT and CLARIFY MUST return actions=[]. Never combine either intent with a tool action. ')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    if (OUT / 'EMAIL_SENT.json').exists():
        raise ValueError('Sent R3 is immutable; create a new revision')
    spec = importlib.util.spec_from_file_location('turn_intent_transform', SOURCE / 'bundle/decision_transform.py')
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
        b"BUNDLE_ID = 'genos-selective-20260929-r1'", ("BUNDLE_ID = '" + BUNDLE_ID + "'").encode())
    assert BUNDLE_ID.encode() in apply
    (bundle / 'apply.py').write_bytes(apply)
    feature['assets']['apply.py'] = sha(apply)
    provenance = []
    for name, qualified in [
        ('02_BACKEND/semantic_runtime/legal_agent/obligation_protocol.py', 'validate_wire'),
        ('02_BACKEND/semantic_runtime/legal_agent/question_obligations.py', 'PROMPTS'),
    ]:
        sources = [('audit-before', (AUDIT / 'before' / name).read_bytes())]
        for folder in (
            '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-20260929-r1/code',
            '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-repair-20260929-r1/code',
            '08_DEPLOYMENT/GENOS/patches/prompt_compaction_20260928_r1/payload',
            '08_DEPLOYMENT/GENOS/patches/final_review_disabled_20260928_r1/payload',
        ):
            path = ROOT / folder / name
            if path.is_file():
                sources.append((folder, path.read_bytes()))
        with zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFFS/20260929-rag-main-integrated/code.zip') as zipped:
            sources.append(('integrated-mail-code.zip', zipped.read(name)))
        nodes = []
        seen = set()
        for label, raw in sources:
            before = transform.node_for(raw, qualified)
            if qualified == 'validate_wire':
                after = (ROOT / name).read_bytes()
            else:
                # Replace only the intended guidance in each approved variant;
                # preserve every other prompt and site function.
                if OLD_PROMPT.encode() not in raw:
                    raise ValueError('unapproved prompt variant: ' + label)
                after = raw.replace(OLD_PROMPT.encode(), NEW_PROMPT.encode(), 1)
            after_node = transform.node_for(after, qualified)
            before_ast, after_ast = transform.signature(before), transform.signature(after_node)
            provenance.append({'path': name, 'qualified': qualified, 'source': label,
                               'source_sha256': sha(raw), 'before_ast': before_ast, 'after_ast': after_ast})
            if before_ast in seen:
                continue
            seen.add(before_ast)
            asset = 'intent/' + str(len(nodes)) + '-' + Path(name).name
            path = bundle / asset
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(transform.snippet(after, after_node)[2])
            feature['assets'][asset] = sha(path.read_bytes())
            nodes.append({'before_ast': before_ast, 'after_ast': after_ast, 'after': asset})
        feature['files'][name] = {'nodes': [{'qualified': qualified, 'variants': nodes, 'optional': False}]}
    feature['source_patch'] = 'model-decision-repair-20260929-r3'
    manifest.update(bundle=BUNDLE_ID, handoff_revision='MODEL_DECISION_REPAIR_R3_INTENT_ACTION',
                    intent_variant_sources=provenance)
    (bundle / 'SELECTIVE_MANIFEST.json').write_bytes(dump(manifest))
    names = sorted(set(feature['assets']) | {'SELECTIVE_MANIFEST.json'})
    rows = [{'path': name, 'bytes': len((bundle / name).read_bytes()),
             'sha256': sha((bundle / name).read_bytes())} for name in names]
    archive = OUT / (PREFIX + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for row in rows:
            zipped.write(bundle / row['path'], row['path'])
        zipped.writestr('CODE_MANIFEST.json', dump({
            'format': '8agent-code/1', 'patch': BUNDLE_ID, 'files': rows}))
    old_zip = SOURCE / 'GENOS_MODEL_DECISION_REPAIR_20260929_R2.zip'
    txt = (SOURCE / 'GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt').read_text()
    txt = txt.replace('GENOS_MODEL_DECISION_REPAIR_20260929_R2', PREFIX)
    txt = txt.replace(sha(old_zip.read_bytes()), sha(archive.read_bytes()))
    txt = txt.replace('MODEL_DECISION_REPAIR R2 PHOTO_COMPATIBLE', 'MODEL_DECISION_REPAIR R3 INTENT_ACTION')
    txt = txt.replace('genos-selective-20260929-r1', BUNDLE_ID)
    txt = txt.replace('# R1 대신 이 R2 ZIP/TXT를 같은 폴더에 저장하고 실행합니다.',
                      '# R2 적용 후에도 발생한 intent/actions 충돌을 같은 입력에서 모델에 재수정 요청합니다.')
    txt = txt.replace('# 사진의 코드 판 또는 통합판에서 판단 오류 수정만 적용합니다.',
                      '# 기존 R2 수정 기능을 포함합니다. 사진 기준 코드·R2 적용 코드·통합판을 지원합니다.')
    path = OUT / (PREFIX + '_APPLY.txt')
    path.write_text(txt)
    subprocess.run(['bash', '-n', str(path)], check=True)
    (OUT / 'DELIVERY.json').write_bytes(dump({
        'patch': BUNDLE_ID, 'zip': archive.name, 'zip_sha256': sha(archive.read_bytes()),
        'txt': path.name, 'txt_sha256': sha(path.read_bytes()),
        'source_r2_sha256': sha(old_zip.read_bytes()),
        'changed_runtime_files': list(feature['files']),
        'code_root': str(ROOT), 'commit': None, 'selected_generation': None,
        'generation_manifest_sha256': None, 'code_serving_revision': None,
        'generation_modified': False, 'workflow_modified': False,
        'email_sent': False, 'genos_deployed': False,
    }))
    print(json.dumps({'zip': str(archive), 'txt': str(path), 'sha256': sha(archive.read_bytes())}))


if __name__ == '__main__':
    main()
