"""Frozen, read-only structural smoke against one public source article."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0579-structured-unit-fallback-read'
MODULE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0579/unit-read/snapshot/02_BACKEND/semantic_runtime/legal_agent/unit_access.py'
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from semantic_runtime.storage import Store


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    manifest = json.loads((ADR/'실험/manifest.json').read_text())
    if not manifest['design']['criteria_frozen_before_run']:
        raise ValueError('design not frozen')
    for relative, expected in manifest['design']['frozen_inputs'].items():
        if sha(ROOT/relative) != expected:
            raise ValueError('frozen input changed: '+relative)
    spec = importlib.util.spec_from_file_location('adr_0579_unit_access', MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cases = json.loads((ADR/'artifacts/design/cases.json').read_text())
    store = Store(ROOT/cases['generation'])
    try:
        did, article_id = cases['document_id'], cases['article_unit_id']
        units = {}
        for row in store.db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?', (did,)):
            value = json.loads(row['json'])
            value['parent'] = row['parent_id']
            units[(did, row['unit_id'])] = value
        root = units[(did, article_id)]
        lo, hi = root['span']
        article_chars = store.db.execute('SELECT sum(length(text)) FROM source_block WHERE document_id=? '
            'AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<?', (did, lo, hi)).fetchone()[0]
        results = []
        for case in cases['cases']:
            uid, basis = module.choose_unit(store, units, did, article_id, case['query'])
            context = module.neighborhood(store, units, did, uid)
            extent = module.first_read_extent(article_id, uid)
            selected_chars = (article_chars if extent == 'article' else
                              sum(len(block['text']) for block in module.direct_blocks(store, did, uid)))
            results.append({'id': case['id'], 'expected_unit_id': case['expected_unit_id'],
                'chosen_unit_id': uid, 'correct': uid == case['expected_unit_id'],
                'basis': basis, 'read_extent': extent, 'article_chars': article_chars,
                'first_read_chars': selected_chars,
                'preview_chars': sum(len(item['preview']) for item in context['before']+context['after']),
                'expansion_available': bool(context['expansion']['neighbor_unit_ids'] or context['expansion']['parent_unit_id'])})
    finally:
        store.close()
    test = subprocess.run([str(ROOT/'.venv/bin/python'), '-m', 'pytest', '-q',
        str(Path(__file__).with_name('test_unit_access.py'))], cwd=ROOT,
        capture_output=True, text=True)
    if test.returncode:
        raise RuntimeError(test.stdout+test.stderr)
    output = ADR/'artifacts/run-001'
    output.mkdir(exist_ok=False)
    report = {'status':'complete', 'classification':'LOCAL_PUBLIC_SOURCE_PROTOTYPE',
        'cases':results, 'correct':sum(item['correct'] for item in results),
        'total':len(results), 'synthetic_contracts':'4 passed',
        'model_calls':0, 'answer_quality_measured':False,
        'latency_improvement_measured':False,
        'production_wiring':'unchanged',
        'note':'Queries are fixed article-local probes; they do not measure end-to-end RAG recall.'}
    (output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'correct':report['correct'], 'total':report['total'],
                      'first_read_chars':[item['first_read_chars'] for item in results],
                      'article_chars':article_chars}))


if __name__ == '__main__':
    main()
