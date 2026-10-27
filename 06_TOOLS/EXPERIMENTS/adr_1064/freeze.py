"""Freeze nine closed source cells and this audit before revised accounting."""
from datetime import datetime,timezone
from common import ROOT,ADR,ART,SOURCE,TOOLS,read,save,sha,rel,canonical_digest


def main():
    assert not (ART/'design-freeze.json').exists()
    assert not (ART/'result.json').exists()
    source=read(SOURCE/'design-freeze.json')
    assert read(SOURCE/'matrix-stop.json')['reason']=='FIRST_NINE_GATE_FAILED'
    assert read(SOURCE/'gate.json')['passed'] is False
    paths=[SOURCE/n for n in ('design-freeze.json','matrix-stop.json','gate.json')]
    cells=[]
    for cell in source['execution_order'][:9]:
        name=f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}";folder=SOURCE/'matrix'/name
        result=read(folder/'result.json');resources=SOURCE/'matrix'/(name+'.resources.json')
        assert result['cell']==cell and result['completed'] is True
        assert read(resources)['process_reaped'] is True
        paths.append(resources)
        required=('reservation.json','result.json','request.json','response.json','metrics.json',
                  'evidence-audit.json','execution-audit.json','physical-calls.jsonl')
        for name_ in required:
            assert (folder/name_).is_file();paths.append(folder/name_)
        paths.extend(p for p in (folder/'model').rglob('*') if p.is_file())
        journals=sorted(folder.glob('runtime/legal-agent/runs/*/*/journal.sqlite'))
        assert journals
        for path in journals:
            assert not PathExistsNonempty(path.with_name(path.name+'-wal')),'uncheckpointed source WAL'
            paths.append(path)
        cells.append({'cell':cell,'directory':rel(folder),'journals':[rel(p) for p in journals]})
    product=ROOT/source['code_root']
    for path,expected in source['files'].items():assert sha(product/path)==expected
    parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1060-exact-wire-reference-audit/실험/manifest.json'
    manifest=read(ADR/'실험/manifest.json')
    assert sha(parent)==manifest['lineage']['parents'][0]['manifest_sha256']
    assert manifest['design']['criteria_frozen_before_run'] is True
    tools={rel(p):sha(p) for p in sorted(TOOLS.glob('*.py'))}
    source_tools={rel(ROOT/'06_TOOLS/EXPERIMENTS/adr_1063'/n):sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1063'/n)
                  for n in ('wire_audit.py','common.py')}
    inputs={rel(p):sha(p) for p in sorted(set(paths))}
    value={'schema_version':'native-delivery-reference-audit-freeze-v1',
        'frozen_at':datetime.now(timezone.utc).isoformat(),'cells':cells,'inputs':inputs,
        'inputs_digest':canonical_digest(inputs),'tool_files':tools,'source_tools':source_tools,
        'implementation_plan_sha256':sha(ART/'implementation-plan.json'),
        'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),
        'parent_manifest_sha256':sha(parent),'source_design_freeze_sha256':sha(SOURCE/'design-freeze.json'),
        'model_calls':0,'source_database_access':False,'gate_reevaluation':False,'semantic_regrade':False}
    save(ART/'design-freeze.json',value)
    print('Frozen nine source cells and audit code; audit has not run.')


def PathExistsNonempty(path):return path.exists() and path.stat().st_size>0


if __name__=='__main__':main()
