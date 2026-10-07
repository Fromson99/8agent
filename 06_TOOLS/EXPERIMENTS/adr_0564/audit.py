"""Frozen synthetic DB policy audit; no FTS5, ANN, native RAG or model calls."""
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree
from fixtures import ADR, ROOT, OPS, ToolAdapter, build, load, sha


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    manifest=json.loads((ADR/'실험/manifest.json').read_text())
    if not manifest['design']['criteria_frozen_before_run']:
        raise ValueError('design not frozen')
    for path,expected in manifest['design']['frozen_inputs'].items():
        if sha(ROOT/path)!=expected:raise ValueError('frozen input changed: '+path)
    c=manifest['design']['code_isolation']['candidates'][0]
    if sha(ROOT/c['manifest_path'])!=c['manifest_sha256'] or sha(ROOT/c['runner_path'])!=c['runner_sha256']:
        raise ValueError('explicit candidate or runner changed')
    out=ADR/'artifacts/run-001';out.mkdir(exist_ok=False)
    checked=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','pytest','-q',
        str(Path(__file__).with_name('test_contracts.py')),'--junitxml='+str(out/'contracts.xml')],
        cwd=ROOT,capture_output=True,text=True)
    (out/'contracts.log').write_text(checked.stdout+checked.stderr)
    if checked.returncode:raise RuntimeError('contract failure; original output preserved')
    cases=[{'name':n.attrib['name'],'passed':n.find('failure') is None and n.find('error') is None}
        for n in ElementTree.parse(out/'contracts.xml').getroot().iter('testcase')]
    m=load();g=build(m,out/'investigation-ontology.sqlite')
    results={name:ToolAdapter(name,op).execute(g) for name,op in OPS.items()}
    graph={table:[dict(row) for row in g.db.execute('SELECT * FROM '+table)]
        for table in ('concept','relation','resource','membership','node')}
    g.close();write(out/'ontology.json',graph)
    write(out/'result.json',{'status':'complete','classification':'SYNTHETIC','passed':sum(c['passed'] for c in cases),
        'total':len(cases),'contracts':cases,'adapter_results':results,'model_calls':0,'retrieval_calls':0,
        'search_latency_measured':False,'semantic_context_matcher_implemented':False,
        'native_tool_handlers_connected':False,'production_wiring':'unchanged'})
    print(json.dumps({'passed':len(cases),'operation_adapters':len(results),'model_calls':0}))


if __name__=='__main__':main()
