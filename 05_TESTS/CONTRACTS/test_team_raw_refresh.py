"""Registration repair uses synthetic bytes; no internal data or model calls."""
import importlib.util
import json

import pytest

from lawrag.pipeline import genos_build as build, team_raw, team_raw_refresh
from semantic_runtime.contracts import sha


def setup(data, entries):
    files = {}
    for rel, content in entries.items():
        p = data / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        files[rel] = {'sha256': sha(p), 'team': 'risk_team',
                      'export_allowed': False, 'security_class': 'restricted',
                      'original_path': rel}
    build.atomic(data / 'CATALOG/TEAM_LAYOUT.json',
                 {'schema_version': team_raw.VERSION, 'files': files})


def test_changed_pdf_is_readmitted_with_history_and_cli(tmp_path, monkeypatch):
    from lawrag.pipeline import genos_stages, raw_preprocess
    rel = 'RAW/internal/risk_team/a.pdf'
    setup(tmp_path, {rel: b'old pdf'})
    old = team_raw.config(tmp_path)
    (tmp_path / rel).write_bytes(b'new pdf')
    preview = team_raw_refresh.refresh(tmp_path)
    assert preview['counts'] == {'CONTENT_CHANGED': 1}
    assert team_raw.config(tmp_path) == old
    spec = importlib.util.spec_from_file_location('refresh_cli', build.ROOT / '06_TOOLS/COMMANDS/prepare_data.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda _: tmp_path)
    assert cli.main(['--refresh-team-layout', '--apply']) == 0
    current = team_raw.config(tmp_path)
    assert current['files'][rel]['sha256'] == sha(tmp_path / rel)
    history = tmp_path / current['refresh']['receipt']
    assert json.loads(history.with_name('before.json').read_text()) == old
    # Current hash is accepted by the actual preparation/collection consumers.
    raw_preprocess.run(build.ROOT, tmp_path, tmp_path / 'LOGS/test',
                       execute=False, unzip=False, pdf=False)
    plan, report = team_raw.collect(tmp_path, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 1
    assert team_raw_refresh.refresh(tmp_path, apply=True)['status'] == 'UNCHANGED'


def test_move_and_doc_pdf_pairing(tmp_path):
    doc = 'RAW/internal/risk_team/old/a.doc'
    pdf = 'RAW/internal/risk_team/old/a.pdf'
    setup(tmp_path, {doc: b'doc bytes', pdf: b'pdf bytes'})
    for rel in (doc, pdf):
        target = tmp_path / rel.replace('/old/', '/new/')
        target.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).rename(target)
    result = team_raw_refresh.refresh(tmp_path, apply=True)
    assert result['counts'] == {'MOVED': 2}
    plan, report = team_raw.collect(tmp_path, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 1
    assert plan['files'][0]['path'].endswith('/new/a.pdf')
    assert len(plan['files'][0]['representations']) == 2


def test_changed_bytes_do_not_inherit_export_approval(tmp_path):
    rel = 'RAW/external/risk_team/a.pdf'
    setup(tmp_path, {rel: b'public version'})
    value = team_raw.config(tmp_path)
    value['files'][rel].update(export_allowed=True, security_class='public',
                              source_metadata={'export_allowed': True})
    build.atomic(tmp_path / 'CATALOG/TEAM_LAYOUT.json', value)
    (tmp_path / rel).write_bytes(b'edited version')
    team_raw_refresh.refresh(tmp_path, apply=True)
    item = team_raw.config(tmp_path)['files'][rel]
    assert item['export_allowed'] is False
    assert item['source_metadata']['export_allowed'] is False


def test_ambiguous_move_and_stale_derivative_are_not_certified(tmp_path):
    a = 'RAW/internal/risk_team/a.docx'
    b = 'RAW/internal/risk_team/b.docx'
    setup(tmp_path, {a: b'same', b: b'same'})
    (tmp_path / a).rename(tmp_path / a.replace('a.docx', 'c.docx'))
    (tmp_path / b).unlink()
    original = team_raw.config(tmp_path)
    with pytest.raises(ValueError, match='여러 개'):
        team_raw_refresh.refresh(tmp_path, apply=True)
    assert team_raw.config(tmp_path) == original


def test_stale_derivative_and_symlink_fail_without_registration_change(tmp_path):
    origin = 'RAW/internal/risk_team/a.docx'
    derived = 'RAW/internal/risk_team/a.pdf'
    setup(tmp_path, {origin: b'original', derived: b'pdf'})
    build.atomic(tmp_path / 'CATALOG/RAW_DERIVATIVES.json', {'files': {derived: {
        'origin': origin, 'origin_sha256': sha(tmp_path / origin),
        'sha256': sha(tmp_path / derived)}}})
    (tmp_path / origin).write_bytes(b'new original')
    before = team_raw.config(tmp_path)
    with pytest.raises(ValueError, match='파생본'):
        team_raw_refresh.refresh(tmp_path, apply=True)
    assert team_raw.config(tmp_path) == before
    (tmp_path / 'RAW/internal/risk_team/link').symlink_to(tmp_path / origin)
    with pytest.raises(ValueError, match='symlink'):
        team_raw_refresh.refresh(tmp_path, apply=True)


def test_file_change_during_scan_is_not_committed(tmp_path, monkeypatch):
    rel = 'RAW/internal/risk_team/a.pdf'
    setup(tmp_path, {rel: b'original'})
    (tmp_path / rel).write_bytes(b'updated')
    original_inputs = team_raw.inputs
    calls = 0
    def racing_inputs(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            (tmp_path / rel).write_bytes(b'changed during refresh')
        yield from original_inputs(*args, **kwargs)
    monkeypatch.setattr(team_raw, 'inputs', racing_inputs)
    before = team_raw.config(tmp_path)
    with pytest.raises(ValueError, match='갱신 도중'):
        team_raw_refresh.refresh(tmp_path, apply=True)
    assert team_raw.config(tmp_path) == before
