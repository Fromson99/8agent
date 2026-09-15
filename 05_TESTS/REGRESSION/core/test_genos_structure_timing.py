"""Synthetic diagnostic contracts; no model calls or performance comparisons."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('structure_timing', ROOT / '06_TOOLS/COMMANDS/genos_structure_timing.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_timing_records_failures_and_restores(tmp_path):
    def fail():
        raise ValueError('fixture')
    module = SimpleNamespace(action=fail)
    timer = tool.Timing(tmp_path)
    timer.wrap(module, 'action', 'child')
    with pytest.raises(ValueError), timer.stage('parent'):
        module.action()
    assert timer.rows['child']['calls'] == 1
    assert timer.rows['child']['failures'] == 1
    assert timer.rows['parent']['seconds_inclusive'] >= timer.rows['child']['seconds_inclusive']
    assert not timer.stack
    timer.close()
    assert module.action is fail
    events = [json.loads(line) for line in (tmp_path/'timing.jsonl').read_text().splitlines()]
    assert sum(e['event']=='FAIL' for e in events) == 2


def test_select_rejects_ambiguous_and_symlink(tmp_path):
    (tmp_path/'STRUCTURE').mkdir()
    for key in ('a', 'b'):
        folder = tmp_path/'STRUCTURE'/key
        folder.mkdir()
        (folder/'structure-receipt.json').write_text(json.dumps({'input_row': {'relative': 'law/a.xml'}}))
    timer = tool.Timing(tmp_path)
    args = argparse.Namespace(cache=None, document='law/a.xml', from_run=None)
    try:
        with pytest.raises(ValueError, match='2개'):
            tool.select_cache(tmp_path, args, timer)
        (tmp_path/'alias').symlink_to(tmp_path/'STRUCTURE'/'a', target_is_directory=True)
        with pytest.raises(ValueError, match='Symlink'):
            tool.plain(tmp_path/'alias')
    finally:
        timer.close()


@pytest.mark.parametrize('rebuild', [False, True])
def test_main_single_document_isolated(tmp_path, monkeypatch, rebuild):
    from lawrag.pipeline import genos_stages as stages, genos_build as build
    from semantic_runtime.contracts import sha
    root = tmp_path/'dev'
    code = root/'02_BACKEND/lawrag/pipeline'
    code.mkdir(parents=True)
    (code/'genos_stages.py').touch()
    data = root/'01_DATA'
    raw = data/'RAW/law'
    raw.mkdir(parents=True)
    source = raw/'sample.xml'
    source.write_text('fixture')
    cache = data/'STRUCTURE/key'
    cache.mkdir(parents=True)
    receipt = dict(input_row=dict(path=str(source), relative='law/sample.xml', document_id='fixture', sha256=sha(source)),
                   plan={'files': []}, parser={'fixture': True})
    (cache/'structure-receipt.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(build, 'ROOT', root)
    monkeypatch.setattr(stages, 'parser_identity', lambda _: {'fixture': True})
    # Synthetic source files live outside fake root; replace provenance hashing only.
    for m in (stages, build):
        monkeypatch.setattr(m, '__file__', str(code/'genos_stages.py'))
    from lawrag.pipeline import genos_doc
    from semantic_runtime import contracts
    monkeypatch.setattr(genos_doc, '__file__', str(code/'genos_stages.py'))
    monkeypatch.setattr(contracts, '__file__', str(code/'genos_stages.py'))
    calls = []
    def verify(folder):
        calls.append(('verify', folder))
        return receipt
    def structure(row, plan, target, dependencies, timeout, emit):
        assert row['path'] == str(source)
        assert target.is_relative_to(data/'LOGS')
        assert not target.exists()
        calls.append(('rebuild', target))
        return target, plan
    monkeypatch.setattr(stages, 'verify_structure', verify)
    monkeypatch.setattr(stages, 'structure', structure)
    monkeypatch.setattr(tool, 'summarize_source', lambda folder, timer: {'document': 1})
    original = (cache/'structure-receipt.json').read_bytes()
    args = ['--root', str(root), '--document', 'law/sample.xml'] + (['--rebuild'] if rebuild else [])
    assert tool.main(args) == 0
    assert [c[0] for c in calls] == ['rebuild' if rebuild else 'verify']
    assert (cache/'structure-receipt.json').read_bytes() == original
    report = json.loads(next((data/'LOGS').glob('*/summary.json')).read_text())
    assert report['status'] == 'COMPLETED'
    assert report['llm_calls'] == 0
    assert stages.verify_structure is verify
