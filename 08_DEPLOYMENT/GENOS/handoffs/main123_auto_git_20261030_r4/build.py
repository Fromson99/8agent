"""Reuse the immutable R3 product; add the RAG-only Git publication wrapper."""
from pathlib import Path
import ast, hashlib, json, subprocess, tempfile, zipfile
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
PRIOR=OUT.parent/'main123_full_overwrite_20261030_r3'
NAME='GENOS_MAIN123_RAG_AUTO_GIT_20261030_R4'
RUN=NAME+'_RUN.txt'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
prior_record=json.loads((PRIOR/'HANDOFF.json').read_text())
row=next(r for r in prior_record['attachments'] if r['filename'].endswith('.zip'))
source=PRIOR/row['filename'];assert sha(source.read_bytes())==row['sha256']
with zipfile.ZipFile(source) as z:
    members={n:z.read(n) for n in z.namelist()}
spec=json.loads(members.pop('PACKAGE.json'))
original_code=dict(spec['code'])
spec['version']=NAME
spec['git_publish']={'scope':'rag-code-serving','branch':'main','remotes':{
'risk_team':'http://llmops-gitea-service:3000/llmops/623.git',
'financial_team':'http://llmops-gitea-service:3000/llmops/701.git'}}
members['GUIDE.txt']=(OUT/'GUIDE.txt').read_bytes()
members['genos_rag_git_publish.py']=(ROOT/'06_TOOLS/COMMANDS/genos_rag_git_publish.py').read_bytes()
members['runner.py']=members['runner.py'].replace(b'APPLIED MAIN123 FULL R3:',b'APPLIED MAIN123 RAG R4:')
binding=json.loads(members['SOURCE_BINDING.json'])
binding.update(source_r3_zip_sha256=row['sha256'],git_publish=spec['git_publish'],
               password_embedded=False,git_push_verified_in_field=False)
members['SOURCE_BINDING.json']=encoded(binding)
for n,b in members.items():
    if n.endswith('.py'):ast.parse(b,filename=n,feature_version=(3,11))
    assert Path(n).suffix.lower() not in {'.zip','.js','.jsx','.mjs','.cjs'}
for n,h in original_code.items():assert sha(members[spec['payload_paths'][n]])==h
code_zip_sha=spec['payload']['code.zip']
spec['payload']={n:sha(b) for n,b in members.items()}
spec['payload']['code.zip']=code_zip_sha
spec_raw=encoded(spec);members['PACKAGE.json']=spec_raw
with zipfile.ZipFile(OUT/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n,b in sorted(members.items()):z.writestr(n,b)
(OUT/'EXPECTED_PACKAGE.json').write_bytes(spec_raw)
zip_sha=sha((OUT/(NAME+'.zip')).read_bytes())
bootstrap=(OUT/'bootstrap.py').read_text().replace('__ZIP_SHA256__',zip_sha).replace('__SPEC_SHA256__',sha(spec_raw))
bootstrap=(OUT/'materialize.py').read_text()+'\n'+bootstrap
compile(bootstrap,'bootstrap','exec')
shell='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_LOG_DIR="$PWD/main123-rag-auto-git-r4-logs"
if [[ -L "$TASK_LOG_DIR" ]]; then echo "Refuse symlink log folder" >&2; exit 2; fi
mkdir -p "$TASK_LOG_DIR"
TASK_LOG="$TASK_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_RC=$?; printf "%s\\n" "$TASK_RC" > "$TASK_LOG.exit"; echo "MAIN123_AUTO_GIT_EXIT=$TASK_RC LOG=$TASK_LOG"' EXIT
python3 -u - "$@" <<'MAIN123_AUTO_GIT_PY'
'''
(OUT/RUN).write_text(shell+bootstrap+'\nMAIN123_AUTO_GIT_PY\n')
subprocess.run(['bash','-n',str(OUT/RUN)],check=True)
record={'main':123,'product_changes_from_r3':0,'code_files':len(original_code),
'package_sha256':sha(spec_raw),'source_r3_zip_sha256':row['sha256'],
'git_publish':spec['git_publish'],'password_embedded':False,
'field_deployment_verified':False,'attachments':[]}
for n in [NAME+'.zip',RUN,'GUIDE.txt']:
    p=OUT/n;record['attachments'].append({'filename':n,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())})
(OUT/'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps({'files':len(original_code),'product_changes':0,'attachments':[{k:v for k,v in r.items() if k!='path'} for r in record['attachments']]},ensure_ascii=False))
