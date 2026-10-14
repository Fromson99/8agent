"""Freeze the whole-dataset cache over verified cumulative system logging."""
import ast,base64,hashlib,json,os,subprocess,sys,tempfile,zipfile,zlib
from datetime import datetime,timezone
from io import BytesIO
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
PARENT=OUT.parent/'system_logging_20261007_r1';NAME='GENOS_QUERY_LATENCY_20261007_R4'
OWNED=('02_BACKEND/semantic_runtime/unit_fulltext.py','02_BACKEND/semantic_runtime/term_index.py',
       '02_BACKEND/semantic_runtime/request_report.py','02_BACKEND/semantic_runtime/storage.py',
       '02_BACKEND/semantic_runtime/fulltext.py','02_BACKEND/semantic_runtime/navigation_agent.py',
       '02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','06_TOOLS/OFFLINE/genos_query_latency_summary.py')
ADDED=('02_BACKEND/semantic_runtime/runtime_cache.py','02_BACKEND/semantic_runtime/resident_data.py',
       '07_DOCS/REFERENCE/OPERATIONS/GENOS_PROCESS_SEARCH_CACHE_20261007_R4.md')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def embedded(name,raw):
    packed=base64.b64encode(zlib.compress(raw,9)).decode()
    return (f'_raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(_raw).hexdigest()=={sha(raw)!r}\n'
            f'_mod=types.ModuleType({name!r})\n_mod.__file__=str(Path.cwd()/{(name+".py")!r})\n'
            f'sys.modules[{name!r}]=_mod\nexec(compile(_raw,_mod.__file__,"exec"),_mod.__dict__)\n')

def main():
    target=OUT/(NAME+'.zip');assert not target.exists(),'Use a new revision for a sealed ZIP'
    record=json.loads((PARENT/'HANDOFF.json').read_text());raw=(PARENT/(record['version']+'.zip')).read_bytes()
    assert sha(raw)==record['code_zip_sha256']
    with zipfile.ZipFile(BytesIO(raw)) as z:
        manifest_raw=z.read('CODE_MANIFEST.json');assert sha(manifest_raw)==record['code_manifest_sha256']
        parent=json.loads(manifest_raw);payload={row['path']:z.read(row['path']) for row in parent['files']}
    rows={row['path']:dict(row) for row in parent['files']}
    for path in (*OWNED,*ADDED):payload[path]=(ROOT/path).read_bytes()
    # Pins are calculated over precisely these frozen bytes, preserving concurrent
    # progress/UI work in the working tree without shipping an unverified variant.
    with tempfile.TemporaryDirectory(prefix='resident-code-pins-') as directory:
        snapshot=Path(directory)
        for path,raw in payload.items():
            dest=snapshot/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
        for entry in pipeline['engines'].values():
            path=snapshot/entry['manifest'];engine=json.loads(path.read_text())
            if any(p in engine['files'] for p in OWNED):
                for module in ADDED[:2]:engine['files'][module]=sha(payload[module])
                path.write_bytes(encode(engine))
        # Data pins are checked and never rewritten. Only missing small manifests
        # are provided for the pin checker; no original SQLite is copied locally.
        for node in pipeline['profiles']['legal-rag']['nodes']:
            term=node.get('parameters',{}).get('term_agent')
            if not term:continue
            needed=[str(Path(term['index']['path'])/'manifest.json')]
            if term.get('fulltext'):needed.append(str(Path(term['index']['path']).parent/term['fulltext']['path']/'manifest.json'))
            needed.extend(b['path'] for kind in ('origin_projections','alias_projections') for b in term.get(kind,[]))
            for path in needed:
                dest=snapshot/path
                if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/path).read_bytes())
        done=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/semantic_runtime.py'),
            '--root',str(snapshot),'rehash-engines','--apply','--add-new'],capture_output=True,text=True,check=True)
        result=json.loads(done.stdout);assert all(v['ok'] for v in result['data_pins_checked_not_rewritten'])
        (OUT/'FROZEN_ENGINE_CHECK.json').write_bytes(encode(result))
        for path in ('00_SYSTEM/PIPELINE.json',*(e['manifest'] for e in pipeline['engines'].values())):
            payload[path]=(snapshot/path).read_bytes()
    changed=[]
    for path,raw in payload.items():
        if path in rows:
            if sha(raw)!=rows[path]['sha256']:
                changed.append(path);old=rows[path]['sha256']
                rows[path].update(sha256=sha(raw),bytes=len(raw),allowed_predecessors=sorted({old,*rows[path].get('allowed_predecessors',[])}))
        else:rows[path]={'path':path,'sha256':sha(raw),'bytes':len(raw),'allow_missing_predecessor':True}
        assert Path(path).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.sqlite','.db','.pem','.key'}
        if path.endswith('.py'):ast.parse(raw,filename=path,feature_version=(3,10) if '/workflow/' in path else (3,11))
    excluded=[{'path':p,'working_sha256':sha((ROOT/p).read_bytes()),'delivery_sha256':sha(raw)}
              for p,raw in payload.items() if p not in (*OWNED,*ADDED) and (ROOT/p).read_bytes()!=raw]
    required={r['path']:r for r in parent['required_files']}
    for path in (*required,*ADDED):required[path]={'path':path,'sha256':rows[path]['sha256']}
    candidate=dict(parent['main_basis']['candidate_serving_files']);candidate.update({p:sha(payload[p]) for p in (*OWNED,*ADDED) if p.endswith('.py')})
    manifest={**parent,'id':NAME,'files':[rows[p] for p in sorted(rows)],'required_files':[required[p] for p in sorted(required)],
        'parent_code_zip_sha256':record['code_zip_sha256'],'main_basis':{**parent['main_basis'],'candidate_serving_files':candidate},
        'scope':{'updated_files':sorted(changed),'added_files':list(ADDED),'unrelated_working_drift_preserved_excluded':excluded},
        'query_latency':{**parent['query_latency'],'metadata_cache_scope':'server-process-cross-request','max_match_cache_rows':50000},
        'resident_data':{'revision':'resident-data-20261007-r1','default_mode':'auto','ram_budget_mib':8192,
            'server_ram_user_reported_gib':16,'ttl':None,'query_independent':True,'whole_snapshot_eviction':False,
            'insufficient_ram':'complete-local-snapshot','local_directory':'/var/tmp','copies_original_generation':False},
        'field_deployment_status':'NOT_VERIFIED'}
    body=encode(manifest);buffer=BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,raw in sorted({**payload,'CODE_MANIFEST.json':body}.items()):z.writestr(path,raw)
    zip_raw=buffer.getvalue()
    inner=(PARENT/'INNER_APPLY.txt').read_text();assert sha(inner.encode())==record['inner_apply_txt_sha256']
    inner=inner.replace(record['version'],NAME).replace(record['code_zip_sha256'],sha(zip_raw))
    inner=inner.replace('system-logging-r1-artifacts','resident-data-r4-artifacts')
    marker="assert REVISION=='query-latency-20261007-r1' and MATCH_CACHE_ROWS==50000"
    assert marker in inner
    inner=inner.replace(marker,marker+"\nfrom semantic_runtime.resident_data import POOL,REVISION as RESIDENT_REVISION\nassert RESIDENT_REVISION=='resident-data-20261007-r1'\nassert POOL.mode in ('auto','memory','local','off')\nprint('RESIDENT_DATA_CONTRACT PASS',POOL.mode,POOL.max_memory_bytes,flush=True)")
    header='import base64,hashlib,os,sys,types,zlib\nfrom pathlib import Path\n'
    bootstrap=header+embedded('genos_diagnostics',payload['genos_diagnostics.py'])+embedded('genos_log_runner',payload['genos_log_runner.py'])
    bootstrap+=("os.environ['GENOS_SYSTEM_HANDOFF_DIR']=str(Path(sys.argv[1]).resolve().parent)\n"
        "os.environ.setdefault('GENOS_SYSTEM_LOG_DIR','/nfs-root/diamo/8-agent/logs/system')\n"
        "os.environ.setdefault('GENOS_LOG_RUN_ID','deploy-'+sys.modules['genos_diagnostics'].uuid.uuid4().hex[:16])\n"
        "os.environ.setdefault('GENOS_HANDOFF_LOG_DIR',str(Path(os.environ['GENOS_SYSTEM_LOG_DIR'])/os.environ['GENOS_LOG_RUN_ID']/'deployment-artifacts'))\n"
        f"_script=zlib.decompress(base64.b64decode({base64.b64encode(zlib.compress(inner.encode(),9)).decode()!r})).decode()\n"
        f"assert hashlib.sha256(_script.encode()).hexdigest()=={sha(inner.encode())!r}\n"
        "raise SystemExit(sys.modules['genos_log_runner'].main(['--phase','deploy','--','bash','-c',_script,sys.argv[1],*sys.argv[2:]]))\n")
    script='#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n'+('if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi\n')+"python3 - \"${BASH_SOURCE[0]}\" \"$@\" <<'SYSTEM_LOG_BOOTSTRAP'\n"+bootstrap+'SYSTEM_LOG_BOOTSTRAP\n'
    workflow=header+embedded('genos_diagnostics',payload['genos_diagnostics.py'])+payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'].decode()
    push=(OUT.parent/'query_latency_20261007_r3/GENOS_QUERY_LATENCY_20261007_R3_PUSH_NEW_REMOTE.txt').read_text()
    push=push.replace('GENOS_QUERY_LATENCY_20261007_query-latency R3_APPLY.txt',NAME+'_APPLY.txt').replace('query-latency R3','whole-dataset cache R4')
    assert NAME+'_APPLY.txt' in push
    ast.parse(bootstrap,feature_version=(3,11));ast.parse(workflow,feature_version=(3,10))
    ast.parse(inner.split("<<'LOADER_PY'\n",1)[1].rsplit('\nLOADER_PY',1)[0],feature_version=(3,11))
    for path in (*OWNED,*ADDED):assert payload[path]==(ROOT/path).read_bytes(),'Owned bytes advanced while freezing: '+path
    target.write_bytes(zip_raw);(OUT/'CODE_MANIFEST.json').write_bytes(body)
    for name,raw in {NAME+'_APPLY.txt':script.encode(),NAME+'_WORKFLOW_PASTE_ALL.txt':workflow.encode(),
        NAME+'_PUSH_NEW_REMOTE.txt':push.encode(),NAME+'_SUMMARIZE.txt':payload['06_TOOLS/OFFLINE/genos_query_latency_summary.py'],
        'INNER_APPLY.txt':inner.encode()}.items():(OUT/name).write_bytes(raw)
    for suffix in ('_APPLY.txt','_PUSH_NEW_REMOTE.txt'):subprocess.run(['bash','-n',str(OUT/(NAME+suffix))],check=True)
    receipt={**record,'version':NAME,'parent':record['version'],'created_at':datetime.now(timezone.utc).isoformat(),
        'parent_code_zip_sha256':record['code_zip_sha256'],'code_zip_sha256':sha(zip_raw),'code_zip_bytes':len(zip_raw),
        'code_manifest_sha256':sha(body),'code_files':len(rows),'apply_txt_sha256':sha(script.encode()),
        'inner_apply_txt_sha256':sha(inner.encode()),'workflow_txt_sha256':sha(workflow.encode()),
        'scope':manifest['scope'],'resident_data':manifest['resident_data'],'email_sent':False,'email_status':'NOT_SENT',
        'genos_applied':False,'genos_pushed':False,'genos_deployed':False,'local_active_pointer_changed':False,
        'field_generation':None,'field_generation_manifest_sha256':None,'field_commit':None,'field_codeserving_revision':None,
        'source_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    (OUT/'HANDOFF.json').write_bytes(encode(receipt))
    print(json.dumps({'files':len(rows),'bytes':len(zip_raw),'zip_sha256':sha(zip_raw),'excluded':len(excluded)}))
if __name__=='__main__':main()
