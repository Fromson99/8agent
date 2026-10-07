"""Package verified compact-v2 code for the existing GENOS DEV checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_compact_lifecycle as previous
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1'
STEM='GENOS_REFERENCE_BUILD_20261003_R1'
BASE=previous.BASE
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/genos-reference-build-20261003'
SCRIPT=previous.SCRIPT.replace('compact-lifecycle-logs','reference-build-logs').replace('compact-v1','compact-v2').replace('financial_risk-success-20261003-compact-r2','financial_risk-success-20261003-reference-r1')


def main():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    prior=json.loads((previous.OUT/'CODE_MANIFEST.json').read_text())
    rows_by_name={r['path']:dict(r) for r in prior['files']}
    required={r['path']:r for r in prior['required_files']}
    pins=json.loads((AUDIT/'ENGINE_PINS.json').read_text())
    names=set(rows_by_name)|set(pins['changed_code'])|{r['manifest'] for r in pins['engine_manifests']}|{'00_SYSTEM/PIPELINE.json'}
    rows=[]
    for name in sorted(names):
        prior_row=rows_by_name.get(name) or required.get(name)
        predecessors=set(prior_row.get('allowed_predecessors',[]) if prior_row else [])
        if prior_row:predecessors.add(prior_row['sha256'])
        path=ROOT/name
        rows.append({'path':name,'role':'code','sha256':sha(path),'bytes':path.stat().st_size,
                     'allowed_predecessors':sorted(predecessors),'allowed_absent':prior_row.get('allowed_absent',False) if prior_row else True})
    requirements=[]
    for name,row in sorted(required.items()):
        if name in names:continue
        assert sha(ROOT/name)==row['sha256'],'Unrelated dependency drift: '+name
        requirements.append(row)
    manifest={'format':'8agent-code/1','id':STEM,'scope':'Completed-source/glossary reuse, exact suffix lookup, shared reference bodies, direct construction audit, compact-v2 recovery',
              'base_code_manifest_sha256':sha(BASE),'parent_handoff_manifest_sha256':sha(previous.OUT/'CODE_MANIFEST.json'),
              'files':rows,'required_files':requirements,'experiment':'ADR-0634-experiment-v1/compact',
              'activated':False,'requires_rebuilt_generation':True}
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/(STEM+'.zip')
    if archive.exists():raise ValueError('Immutable handoff already exists; use a new version')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for row in rows:
            info=zipfile.ZipInfo(row['path'],date_time=(2026,10,3,0,0,0));info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(ROOT/row['path']).read_bytes())
        info=zipfile.ZipInfo('CODE_MANIFEST.json',date_time=(2026,10,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
    script=OUT/(STEM+'.txt');script.write_text(SCRIPT.replace('__STEM__',STEM).replace('__ZIP_SHA__',sha(archive)))
    subprocess.run(['bash','-n',str(script)],check=True)
    (OUT/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    record={'files':{p.name:sha(p) for p in (archive,script)},'changed_or_packaged_files':len(rows),
            'required_unchanged_files':len(requirements),'base_code_manifest_sha256':sha(BASE),
            'field_commit':None,'field_generation':None,'field_revision':None,'git_pushed':False,
            'generation_activated':False,'genos_deployed':False,'field_performance_measured':False}
    (OUT/'HANDOFF.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record,ensure_ascii=False))
if __name__=='__main__':main()
