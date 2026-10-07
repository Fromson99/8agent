"""Pinned compact lifecycle patch, installed into the existing GENOS DEV checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_sqlite_read_reuse as previous
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/compact_lifecycle_20261003_r2'
STEM='GENOS_COMPACT_LIFECYCLE_20261003_R2'
BASE=previous.BASE
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/genos-compact-lifecycle-20261003'
SCRIPT=previous.SCRIPT.replace('sqlite-read-reuse-logs','compact-lifecycle-logs').replace("'financial-risk-success-20261001-r3'","'financial_risk-success-20261002-index-r8'").replace("'financial-risk-success-20261003-sqlite-r1'","'financial_risk-success-20261003-compact-r2'")
SCRIPT=SCRIPT.replace("'--serving','--fulltext-granularity','unit'", "'--serving','--fulltext-granularity','unit','--storage-profile','compact-v1'")
SCRIPT=SCRIPT.replace("  if not target.is_file() or digest(target) not in allowed:", "  if not target.exists() and not applied and r.get('allowed_absent'):continue\n  if not target.is_file() or digest(target) not in allowed:")
SCRIPT=SCRIPT.replace('python3 - "$task_dir/', 'if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\npython3 - "$task_dir/')


def main():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    old={r['path']:r for r in json.loads(BASE.read_text())['files']}
    with zipfile.ZipFile(previous.OUT/(previous.STEM+'.zip')) as z:
        p1={r['path']:r for r in json.loads(z.read('CODE_MANIFEST.json'))['files']}
    pins=json.loads((AUDIT/'ENGINE_PINS.json').read_text())
    names=set(p1)|set(pins['changed_code'])|{r['manifest'] for r in pins['engine_manifests']}|{'06_TOOLS/OFFLINE/genos_code_replace.py'}
    required_names={n for n in old if n.startswith(('00_SYSTEM/','02_BACKEND/ENGINES/','02_BACKEND/semantic_runtime/','02_BACKEND/lawrag/core/','02_BACKEND/lawrag/pipeline/','02_BACKEND/lawrag/platform/','02_BACKEND/PIPELINE/'))}|{'06_TOOLS/OFFLINE/genos_reindex_logging.py','06_TOOLS/OFFLINE/genos_meaning_variants.py','service.py','service/service.py','requirements.txt','requirements-serving.txt','requirements-pipeline.txt'}
    rows=[]
    for n in sorted(names):
        preds=sorted({d[n]['sha256'] for d in (old,p1) if n in d})
        rows.append({'path':n,'role':'code','bytes':(ROOT/n).stat().st_size,'sha256':sha(ROOT/n),'allowed_predecessors':preds,'allowed_absent':not preds})
    required=[]
    for n in sorted(required_names-names):
        assert sha(ROOT/n)==old[n]['sha256'],'Unrelated baseline change: '+n
        required.append({'path':n,'role':'code','sha256':sha(ROOT/n)})
    manifest={'format':'8agent-code/1','id':STEM,'scope':'Compact source/navigation/glossary, resumable prepared reuse, bounded lexical build and request journal','base_code_manifest_sha256':sha(BASE),'files':rows,'required_files':required,'experiment':'ADR-0632-experiment-v1/io','activated':False,'requires_rebuilt_generation':True}
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/(STEM+'.zip')
    if archive.exists():raise ValueError('Immutable handoff already exists; use a new version')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for row in rows:
            info=zipfile.ZipInfo(row['path'],date_time=(2026,10,3,0,0,0));info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,(ROOT/row['path']).read_bytes())
        info=zipfile.ZipInfo('CODE_MANIFEST.json',date_time=(2026,10,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
    script=OUT/(STEM+'.txt');script.write_text(SCRIPT.replace('__STEM__',STEM).replace('__ZIP_SHA__',sha(archive)))
    subprocess.run(['bash','-n',str(script)],check=True)
    (OUT/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    record={'files':{p.name:sha(p) for p in (archive,script)},'changed_or_packaged_files':len(rows),'required_unchanged_files':len(required),'base_code_manifest_sha256':sha(BASE),'field_commit':None,'field_generation':None,'field_revision':None,'git_pushed':False,'generation_activated':False,'genos_deployed':False}
    (OUT/'HANDOFF.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
