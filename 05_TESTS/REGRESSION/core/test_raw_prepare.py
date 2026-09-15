"""Shared local/GENOS preparation safety contracts; synthetic inputs, no model calls."""
import importlib.util
import json
from pathlib import Path

import pytest

from lawrag.datasets.publisher import _package_blob, digest
from lawrag.pipeline import raw_prepare as prep
from lawrag.pipeline import genos_corpus
from semantic_runtime.contracts import sha
from .test_genos_build import XML


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(prep.encoded(value) if isinstance(value, dict) else value.encode())


@pytest.fixture
def packages(tmp_path):
    pins = []
    for source in prep.SOURCES:
        folder = tmp_path / f'01_DATA/PACKAGES/EXTERNAL/source-{source}/gen-one'
        raw = folder / 'ARTIFACTS/법령 제목/원문.xml'
        save(raw, XML.replace('가상규정', source + '규정'))
        sm = folder / 'ARTIFACTS/SOURCE_MANIFEST.json'
        save(sm, {'items': [{'name': source, 'status': 'ok',
            'file': f'data/corpus/{source}/법령 제목/원문.xml', 'sha256': sha(raw),
            'body_file': f'01_DATA/corpus/{source}/법령 제목/원문.xml', 'body_sha256': sha(raw)}]})
        artifacts = [{'logical_id': f'source:{source}:manifest', 'role': 'raw',
                     'path': 'ARTIFACTS/SOURCE_MANIFEST.json', 'sha256': sha(sm), 'media_type': 'application/json'},
                    {'logical_id': f'source:{source}:body', 'role': 'raw',
                     'path': 'ARTIFACTS/법령 제목/원문.xml', 'sha256': sha(raw), 'media_type': 'application/xml'}]
        manifest = folder / 'manifest.json'
        save(manifest, _package_blob(package_id='source-' + source, dataset_id='source-' + source,
             generation_seed=sha(sm), source_origin='public_external', security_class='public',
             authority='authoritative', code_revision='synthetic-test', artifacts=artifacts))
        pins.append({'source': source, 'manifest': str(manifest.relative_to(tmp_path)), 'sha256': sha(manifest)})
    selection = tmp_path / '08_DEPLOYMENT/CONFIG/raw-source-packages.json'
    save(selection, {'schema_version': 'raw-package-selection-v1', 'packages': pins})
    save(tmp_path / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json', {'generation': 1})
    return tmp_path, tmp_path / '01_DATA', selection


def test_preview_copy_repeat_portability_and_independence(packages):
    root, data, selection = packages
    before = prep.scan(data / 'PACKAGES')
    assert prep.import_packages(root, data, selection)['status'] == 'PREVIEW_ONLY'
    assert not (data / 'RAW').exists() and not (data / 'LOGS').exists()
    result = prep.import_packages(root, data, selection, apply=True)
    assert result['status'] == 'IMPORTED' and result['raw_files'] == 7
    assert (data / 'RAW/internal').is_dir() and not list((data / 'RAW/internal').iterdir())
    for stage in prep.STAGES:
        assert (data / stage).is_dir()
    for source in prep.SOURCES:
        manifest = json.loads((data / 'RAW' / source / 'manifest.json').read_text())
        item = manifest['items'][0]
        assert item['file'] == '법령 제목/원문.xml'
        p = genos_corpus.raw_path(data / 'RAW', source, item['file'])
        assert sha(p) == item['sha256']
        original = root / json.loads(selection.read_text())['packages'][list(prep.SOURCES).index(source)]['manifest']
        assert p.stat().st_ino != (original.parent / 'ARTIFACTS/법령 제목/원문.xml').stat().st_ino
        assert manifest['raw_package_provenance']['source_origin'] == 'public_external'
    save(data / 'RAW/internal/부서/팀/새 문서.xml', XML)
    result = prep.import_packages(root, data, selection, apply=True)
    assert result['status'] == 'ALREADY_IMPORTED' and result['additional_files_preserved'] == 1
    assert prep.scan(data / 'PACKAGES') == before
    assert prep.protected(data)['ACTIVE']['local/ACTIVE_RELEASE.json']['bytes'] > 0


def test_no_overwrite(packages):
    root, data, selection = packages
    save(data / 'RAW/user.txt', 'mine')
    with pytest.raises(FileExistsError):
        prep.import_packages(root, data, selection, apply=True)
    assert (data / 'RAW/user.txt').read_text() == 'mine'


@pytest.mark.parametrize('problem', ['pin', 'raw', 'symlink', 'scope', 'duplicate', 'traversal'])
def test_bad_inputs_no_raw_created(packages, problem):
    root, data, selection = packages
    pins = json.loads(selection.read_text())
    if problem == 'pin':
        pins['packages'][0]['sha256'] = '0' * 64
    elif problem in ('raw', 'symlink'):
        path = root / pins['packages'][0]['manifest']
        raw = path.parent / 'ARTIFACTS/법령 제목/원문.xml'
        raw.unlink()
        if problem == 'raw': raw.write_text('changed')
        else: raw.symlink_to(path)
    elif problem == 'scope': pins['packages'][0]['source'] = 'internal'
    elif problem == 'duplicate': pins['packages'][0] = pins['packages'][1]
    else: pins['packages'][0]['manifest'] = '../escape/manifest.json'
    save(selection, pins)
    with pytest.raises((ValueError, OSError)):
        prep.import_packages(root, data, selection, apply=True)
    assert not (data / 'RAW').exists()


@pytest.mark.parametrize('value', ['/outside.xml', '../outside.xml', 'missing.xml'])
def test_manifest_invalid_reference(value):
    with pytest.raises(ValueError):
        prep.normalized_manifest({'body_file': value, 'body_sha256': 'a'}, 'law', {})


def test_recovery_before_and_after_rename(packages, monkeypatch):
    root, data, selection = packages
    original = prep.rename_no_replace
    def interrupt(source, target):
        if target == data / 'RAW':
            raise KeyboardInterrupt
        return original(source, target)
    monkeypatch.setattr(prep, 'rename_no_replace', interrupt)
    with pytest.raises(KeyboardInterrupt):
        prep.import_packages(root, data, selection, apply=True)
    assert not (data / 'RAW').exists()
    monkeypatch.setattr(prep, 'rename_no_replace', original)
    real_atomic = prep.atomic
    def fail_receipt(path, obj):
        if obj['status'] == 'COMPLETED': raise KeyboardInterrupt
        real_atomic(path, obj)
    monkeypatch.setattr(prep, 'atomic', fail_receipt)
    with pytest.raises(KeyboardInterrupt):
        prep.import_packages(root, data, selection, apply=True)
    assert (data / 'RAW').is_dir()
    monkeypatch.setattr(prep, 'atomic', real_atomic)
    assert prep.import_packages(root, data, selection, apply=True)['status'] == 'IMPORTED'


def test_drift_between_copy_and_publish(packages, monkeypatch):
    root, data, selection = packages
    real_copy = prep.shutil.copyfile
    def drift(*a, **kw):
        result = real_copy(*a, **kw)
        save(data / 'ACTIVE/local/ACTIVE_RELEASE.json', {'generation': 2})
        return result
    monkeypatch.setattr(prep.shutil, 'copyfile', drift)
    with pytest.raises(ValueError, match='입력/보호 자료 변경'):
        prep.import_packages(root, data, selection, apply=True)
    assert not (data / 'RAW').exists()


def test_imported_file_change_refused(packages):
    root, data, selection = packages
    prep.import_packages(root, data, selection, apply=True)
    p = data / 'RAW/law/법령 제목/원문.xml'
    p.write_text('user changed')
    with pytest.raises(ValueError, match='해시 불일치'):
        prep.import_packages(root, data, selection, apply=True)
    assert p.read_text() == 'user changed'


def test_shared_entrypoint_packages_and_genos_legacy(packages, monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[3] / '06_TOOLS/COMMANDS/prepare_data.py'
    spec = importlib.util.spec_from_file_location('prepare_data_test', script)
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    root, data, _ = packages
    monkeypatch.setattr(cli, 'ROOT', root)
    monkeypatch.setattr('lawrag.pipeline.genos_stages.offline_data_root', lambda r: r / '01_DATA')
    assert cli.main([]) == 0 and not (data / 'RAW').exists()
    assert cli.main(['--apply']) == 0
    assert cli.main(['--source', str(data / 'PACKAGES/EXTERNAL'), '--apply']) == 1
    assert (data / 'PACKAGES/EXTERNAL').is_dir()
    genos = tmp_path / 'genos'
    save(genos / 'data/corpus/internal/팀/원문.xml', XML)
    monkeypatch.setattr(cli, 'ROOT', genos)
    assert cli.main([]) == 0 and (genos / 'data/corpus').exists()
    assert cli.main(['--apply']) == 0 and not (genos / 'data/corpus').exists()
    assert (genos / '01_DATA/RAW/internal/팀/원문.xml').exists()
    assert cli.main(['--apply']) == 0


@pytest.mark.parametrize('key,value', [('source_origin', 'restricted_internal'),
                                      ('security_class', 'restricted'), ('representation', 'mock')])
def test_restricted_or_example_package_not_imported(packages, key, value):
    root, data, selection = packages
    pins = json.loads(selection.read_text())
    p = root / pins['packages'][0]['manifest']
    package = json.loads(p.read_text())
    package[key] = value
    package.pop('manifest_sha256')
    package['manifest_sha256'] = digest(package)
    save(p, package)
    pins['packages'][0]['sha256'] = sha(p)
    save(selection, pins)
    with pytest.raises(ValueError):
        prep.import_packages(root, data, selection, apply=True)
    assert not (data / 'RAW').exists()
