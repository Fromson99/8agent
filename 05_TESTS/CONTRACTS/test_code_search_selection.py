"""Code-relative latest selection retains original data and API visibility."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from lawrag.pipeline.search_selection import plan, activate, rollback, encode
from semantic_runtime.contracts import sha
import semantic_runtime.search_selection as runtime
from semantic_runtime.storage import Store
from test_search_selection import metadata_generation


def install(root, generation, value=None):
    target = root / runtime.CODE_SELECTION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encode(value or plan(generation, latest=True)))
    config = root / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    config.write_bytes(encode(dict(schema_version='genos-serving-paths-v1',
        selection='operator-fixed', generation=str(generation), runtime=str(root/'runtime'),
        generation_manifest_sha256=sha(generation/'manifest.json'),
        search_selection=dict(path=runtime.CODE_SELECTION_PATH, sha256=sha(target)))))
    return target, config


@pytest.fixture
def bound(tmp_path, monkeypatch):
    g = metadata_generation(tmp_path, [('a','internal/규정(20240101).docx',{}),
                                      ('b','internal/규정(20250101).docx',{})])
    root = tmp_path/'DEV'; target, config = install(root, g)
    monkeypatch.setattr(runtime, 'CODE_ROOT', root)
    return g, root, target, config


def test_no_nfs_sidecar_and_deployed_root_relocation(bound, monkeypatch, tmp_path):
    g, root, target, config = bound
    before = {p.name:sha(p) for p in g.iterdir()}
    assert not runtime.selection_path(g).exists()
    for deployed in (root, tmp_path/'app/src/service'):
        if deployed != root: shutil.copytree(root, deployed)
        monkeypatch.setattr(runtime, 'CODE_ROOT', deployed)
        with closing(Store(g, verify=False)) as store:
            store.selection.require_latest()
            assert store.selection.path == deployed/runtime.CODE_SELECTION_PATH
            assert [r[0] for r in store.db.execute('SELECT document_id FROM document')] == ['b']
            with pytest.raises(sqlite3.DatabaseError): store.db.execute('DELETE FROM main.document')
    assert before == {p.name:sha(p) for p in g.iterdir()}


@pytest.mark.parametrize('fault', ['missing','hash','path','manifest','symlink','marks','metadata'])
def test_code_selection_invalid_never_falls_back_to_valid_nfs(bound, fault):
    g, root, target, config = bound
    nfs = runtime.selection_path(g); nfs.parent.mkdir(); nfs.write_bytes(target.read_bytes())
    value = json.loads(config.read_bytes())
    if fault == 'missing': target.unlink()
    elif fault == 'hash': target.write_bytes(target.read_bytes()+b' ')
    elif fault == 'path': value['search_selection']['path'] = '../../generation.json'
    elif fault == 'manifest': value['generation_manifest_sha256'] = '0'*64
    elif fault == 'symlink': target.unlink(); target.symlink_to(nfs)
    else:
        data = json.loads(target.read_bytes())
        if fault == 'marks':
            data['latest_documents'][0]['is_latest'] = True
            data['excluded'] = []
        else: data['metadata_sha256'] = '0'*64
        target.write_bytes(encode(data)); value['search_selection']['sha256'] = sha(target)
    config.write_bytes(encode(value))
    with pytest.raises(ValueError): Store(g, verify=False)


@pytest.mark.parametrize('fault', ['config','selection','remove_config','switch'])
def test_running_store_rejects_changed_binding(bound, fault):
    g, root, target, config = bound
    with closing(Store(g, verify=False)) as store:
        if fault == 'selection': target.write_bytes(target.read_bytes()+b' ')
        elif fault == 'remove_config': config.unlink()
        elif fault == 'config': config.write_bytes(config.read_bytes()+b' ')
        else:
            value=json.loads(config.read_bytes()); value.pop('search_selection')
            config.write_bytes(encode(value))
        with pytest.raises(ValueError): store.check_unchanged()


def test_other_generation_keeps_legacy_and_legacy_writer_refused(bound, tmp_path):
    g, root, target, config = bound
    with pytest.raises(ValueError, match='code-bundled'): activate(plan(g,latest=True))
    other = tmp_path/'other'; other.mkdir()
    g2=metadata_generation(other,[('c','internal/다른규정.docx',{})])
    receipt=activate(plan(g2,latest=True))
    with closing(Store(g2,verify=False)) as store:
        store.selection.require_latest()
        assert store.selection.path == runtime.selection_path(g2)
    rollback(receipt['receipt'])


def test_legacy_rollback_refused_when_code_bundle_active(tmp_path,monkeypatch):
    g=metadata_generation(tmp_path,[('a','internal/규정.docx',{})])
    root=tmp_path/'DEV'; monkeypatch.setattr(runtime,'CODE_ROOT',root)
    receipt=activate(plan(g,latest=True))
    install(root,g)
    with pytest.raises(ValueError,match='code-bundled'): rollback(receipt['receipt'])


@pytest.mark.parametrize('mode',['legacy','compact-v2'])
def test_deployed_code_json_real_api(tmp_path,monkeypatch,term_glossary,mode):
    import test_search_selection as original
    import test_legal_agent_v5 as v5
    import test_legal_agent_double_harness as harness
    code=Path(runtime.__file__).resolve().parents[2]
    root=tmp_path/'app/src/service'
    monkeypatch.setattr(runtime,'CODE_ROOT',root)
    monkeypatch.setattr(v5,'ROOT',code); monkeypatch.setattr(harness,'ROOT',code)
    monkeypatch.setattr(original,'plan',lambda g:plan(g,latest=True))
    def code_activate(value):
        g=Path(value['generation_path']); install(root,g,value)
        assert not runtime.selection_path(g).exists()
        return {'receipt':str(root/'00_SYSTEM/GENOS_SERVING_PATHS.json')}
    def code_rollback(receipt): Path(receipt).unlink()
    monkeypatch.setattr(original,'activate',code_activate)
    monkeypatch.setattr(original,'rollback',code_rollback)
    original.test_existing_database_search_and_actual_api(tmp_path,monkeypatch,term_glossary,mode)
