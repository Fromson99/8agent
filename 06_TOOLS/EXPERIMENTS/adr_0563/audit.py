"""Explicit frozen research consumer; contract audit, no model/search calls."""
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

from fixtures import ADR, CANDIDATE, ROOT, KEY, capabilities, lift_parent, load, sha


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def main():
    manifest = json.loads((ADR/'실험/manifest.json').read_text())
    if not manifest['design']['criteria_frozen_before_run']:
        raise ValueError('design not frozen')
    for path, expected in manifest['design']['frozen_inputs'].items():
        if sha(ROOT/path) != expected:
            raise ValueError('frozen input changed: '+path)
    isolation = manifest['design']['code_isolation']['candidates'][0]
    if sha(ROOT/isolation['manifest_path']) != isolation['manifest_sha256']:
        raise ValueError('candidate manifest changed')
    if sha(ROOT/isolation['runner_path']) != isolation['runner_sha256']:
        raise ValueError('runner changed')
    output = ADR/'artifacts/run-001'
    output.mkdir(exist_ok=False)
    check = subprocess.run([str(ROOT/'.venv/bin/python'), '-m', 'pytest', '-q',
        str(Path(__file__).with_name('test_contracts.py')), '--junitxml='+str(output/'contracts.xml')],
        cwd=ROOT, capture_output=True, text=True)
    (output/'contracts.log').write_text(check.stdout+check.stderr)
    if check.returncode:
        raise RuntimeError('contract checks failed; exact output preserved')
    suite = ElementTree.parse(output/'contracts.xml').getroot()
    cases = [{'name': c.attrib['name'], 'passed': c.find('failure') is None and c.find('error') is None}
        for c in suite.iter('testcase')]
    m = load(); data, projection = lift_parent(m)
    write(output/'portable-memory.json', data)
    result = m.Memory(data, projection, {KEY}).observe(
        m.observation(projection, 'source_located', ['new-node-1'], origin_tool='vector_knn'),
        capabilities('fetch_fragment'))
    actions = [a for i in result['items'] for a in m.compile_actions(i, projection, capabilities('fetch_fragment'), {KEY})]
    write(output/'result.json', {'status': 'complete', 'classification': 'SYNTHETIC',
        'contract_tests': cases, 'passed': sum(c['passed'] for c in cases), 'total': len(cases),
        'parent_concepts': len(data['concepts']), 'parent_episodes': data['provenance']['episode_count'],
        'guidance': result, 'translated_actions': actions,
        'model_calls': 0, 'search_calls': 0, 'answer_quality_measured': False,
        'latency_improvement_measured': False, 'production_wiring': 'unchanged',
        'mapping_adapter': 'Synthetic original-span mapping only; production ingestion projection not connected.'})
    print(json.dumps({'passed':len(cases),'concepts':len(data['concepts']), 'model_calls':0}))


if __name__ == '__main__':
    main()
