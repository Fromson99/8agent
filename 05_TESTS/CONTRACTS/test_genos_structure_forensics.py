import importlib.util
import json
from pathlib import Path
import subprocess

from lawrag.pipeline.genos_status import Ledger

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '06_TOOLS/OFFLINE/genos_structure_forensics.py'
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_STRUCTURE_FORENSICS_R2_UTF8.txt'
spec = importlib.util.spec_from_file_location('forensics', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def node(block, span, level=1, children=()):
    return {'block': block, 'span': span, 'level': level, 'children': list(children), 'page': 1}


def test_span_diagnostics_identify_shared_blocks_and_parent():
    blocks = [{'idx': 0, 'page': 1, 'text': 'PRIVATE'}, {'idx': 1, 'page': 1, 'text': 'PRIVATE'}]
    errors = module.tree_issues([node(0, [0, 1]), node(0, [0, 2])], blocks)
    assert errors[0]['same_source_block'] is True
    assert errors[0]['previous']['span'] == [0, 1]
    assert 'PRIVATE' not in json.dumps(errors)
    errors = module.tree_issues([node(0, [0, 1], children=[node(1, [1, 2], 2)])], blocks)
    assert errors[0]['code'] == 'invalid_tree_parent'
    assert module.tree_issues([node(0, [0, 2], children=[node(1, [1, 2], 2)])], blocks) == []


def test_journal_calls_hold_and_no_prompts(tmp_path):
    blocks = [{'idx': 0, 'page': 1, 'text': 'PRIVATE'}]
    (tmp_path / 'blocks.json').write_text(json.dumps(blocks))
    (tmp_path / 'baseline.json').write_text(json.dumps({'tree': [node(0, [0, 1])]}))
    events = [{'event': 'model.response', 'call': 2, 'seconds': 1.4, 'prompt': 'PRIVATE'},
              {'event': 'recipe.review.result', 'verdict': 'hold'},
              {'event': 'run.needs_review', 'reason': 'overlapping_sibling_spans'}]
    (tmp_path / 'events.jsonl').write_text('\n'.join(json.dumps(x) for x in events))
    out = module.journal_report(tmp_path)
    assert out['verdicts'] == {'hold': 1}
    assert out['call_budget_exhausted_recorded'] is False
    assert 'PRIVATE' not in json.dumps(out)
    assert 'PRIVATE' in json.dumps(module.journal_report(tmp_path, True))


def test_main_read_only_report(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    logs = tmp_path / 'LOGS/original'
    logs.mkdir(parents=True)
    folder = tmp_path / 'STRUCTURE/key'
    journal = folder / 'structure-recipe-runs/a'
    journal.mkdir(parents=True)
    (journal / 'blocks.json').write_text('[]')
    ledger = Ledger(logs).start([{'document_id': 'one', 'relative': 'external/test.pdf', 'name': 'test'}], 'structure')
    ledger.update('one', 'structure', 'FAILED', output_path=str(folder), error='invalid_tree_parent')
    ledger.finish('FAILED')
    ledger.close()
    before = {p: p.read_bytes() for base in (logs, folder) for p in base.rglob('*') if p.is_file()}
    assert module.main(['--run-id', 'original']) == 0
    assert all(p.read_bytes() == content for p, content in before.items())
    result = json.loads(next((tmp_path / 'LOGS').glob('structure-forensics-*/diagnostics.json')).read_text())
    assert result['phase_counts']['structure']['FAILED'] == 1
    assert result['documents'][0]['journals'][0]['blocks']['count'] == 0


def test_standalone_txt_exact_source():
    text = TXT.read_text().split("<<'GENOS_FORENSICS_PY'\n", 1)[1].rsplit('GENOS_FORENSICS_PY', 1)[0]
    assert text == SCRIPT.read_text()
    subprocess.run(['bash', '-n', str(TXT)], check=True)


def test_console_bounded_to_ten_screens():
    result = {'run_id': 'run', 'phase_counts': {}, 'documents': [
        {'title': '긴제목'*100, 'document_id': str(i), 'relative': 'example.pdf',
         'phases': {'structure': {'state': 'FAILED', 'error': 'e'*1000}}, 'journals': []}
        for i in range(15)]}
    lines = module.capture_screens(result)
    assert len(lines) == 220
    assert sum(line.startswith('===== CAPTURE ') for line in lines) == 10
    assert max(len(line) for line in lines) <= 101
