"""rehash-engines re-pins edited runtime code and schemas; data pins are only checked."""
import hashlib
import json

from semantic_runtime.control import rehash_engines


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace(tmp_path):
    code = tmp_path/'02_BACKEND/runtime'; code.mkdir(parents=True)
    (code/'stages.py').write_text('def retrieve(i,p,c):return {}\n')
    schema = tmp_path/'00_SYSTEM/SCHEMAS/s.json'; schema.parent.mkdir(parents=True); schema.write_text('{}')
    index = tmp_path/'01_DATA/index'; index.mkdir(parents=True); (index/'manifest.json').write_text('{}')
    manifest = tmp_path/'02_BACKEND/ENGINES/retrieve.json'; manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'entrypoint': {'path': '02_BACKEND/runtime/stages.py', 'function': 'retrieve'},
                                    'files': {'02_BACKEND/runtime/stages.py': sha(code/'stages.py')}}, indent=2)+'\n')
    pipeline = {'contracts': {'a': {'schema_path': '00_SYSTEM/SCHEMAS/s.json', 'schema_sha256': sha(schema)}},
                'engines': {'r@1': {'manifest': '02_BACKEND/ENGINES/retrieve.json', 'sha256': sha(manifest)}},
                'profiles': {'legal-rag': {'nodes': [{'parameters': {'term_agent': {
                    'index': {'path': '01_DATA/index', 'manifest_sha256': sha(index/'manifest.json')}}}}]}}}
    (tmp_path/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(pipeline, indent=2)+'\n')
    return code, manifest, index


def test_check_reports_edits_and_apply_repins_code_only(tmp_path):
    code, manifest, index = workspace(tmp_path)
    assert rehash_engines(tmp_path)['engine_manifests'] == []
    (code/'stages.py').write_text('def retrieve(i,p,c):return {"x":1}\n')
    (code/'new_module.py').write_text('X=1\n')
    (index/'manifest.json').write_text('{"changed":true}')
    before = (tmp_path/'00_SYSTEM/PIPELINE.json').read_text()
    report = rehash_engines(tmp_path)
    assert report['changed_code'] == ['02_BACKEND/runtime/stages.py'] and not report['applied']
    assert report['unlisted_runtime_files'] == ['02_BACKEND/runtime/new_module.py']
    assert (tmp_path/'00_SYSTEM/PIPELINE.json').read_text() == before
    report = rehash_engines(tmp_path, apply=True, add_new=True)
    pipeline = json.loads((tmp_path/'00_SYSTEM/PIPELINE.json').read_text())
    files = json.loads(manifest.read_text())['files']
    assert files == {'02_BACKEND/runtime/new_module.py': sha(code/'new_module.py'),
                     '02_BACKEND/runtime/stages.py': sha(code/'stages.py')}
    assert pipeline['engines']['r@1']['sha256'] == sha(manifest)
    # A changed data artifact is reported, never silently re-pinned.
    assert report['data_pins_checked_not_rewritten'] == [{'pin': 'index', 'path': '01_DATA/index', 'ok': False}]
    assert pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']['index']['manifest_sha256'] != sha(index/'manifest.json')
    assert rehash_engines(tmp_path)['engine_manifests'] == []
