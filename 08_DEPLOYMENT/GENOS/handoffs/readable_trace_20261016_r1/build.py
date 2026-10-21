"""Seal only the trace delta over the exact previously mailed MAIN76 inventory."""
import base64,gzip,hashlib,importlib.util,json,subprocess,zlib,zipfile
from pathlib import Path

H=Path(__file__).resolve().parent; R=H.parents[3]; B=H.parent
NAME='GENOS_READABLE_TRACE_20261016_R1'
A=R/'09_ARTIFACTS/AUDITS/20261016-readable-process-trace'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists(), 'Sealed delivery is immutable'
text=(B/'ad_request_logs_20261013_r2/apply_patch.py').read_text()
text=text.replace('Install AD request logging while preserving the verified budget overlay.',
                  'Install the human-readable request trace over the sealed MAIN76 delivery.')
text=text.replace("VERSION = 'GENOS_AD_REQUEST_LOGS_20261013_R2'",f"VERSION = '{NAME}'")
text=text.replace("MODULE = '02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py'\n",'')
start=text.index('    budget = manifest.get('); end=text.index('    if CONFIG in payload:',start)
text=text[:start]+"    if manifest.get('investigation_budget_settings') is not None:\n        raise ValueError('Apply the mailed MAIN_FULL_20261016_R1 baseline first; existing files preserved')\n"+text[end:]
start=text.index('def budget_transform('); end=text.index('def prepared(',start)
text=text[:start]+text[end:]
start=text.index("        has_budget = name == 'service.py'"); end=text.index('            raise ValueError(\'Unknown code bytes;',start)
text=text[:start]+"        if (sha(old) if old is not None else None) != item['before_sha256']:\n"+text[end:]
text=text.replace("        if has_budget:\n            new = budget_transform(new, spec, restore=True)\n",'')
text=text.replace('Known complete GENOS/CM code inventory required;', 'GENOS_MAIN_FULL_20261016_R1 complete code inventory required;')
text=text.replace('model_stream_fix','readable_trace').replace('Model stream fix','Readable trace')
start=text.index("    after['readable_trace'] = {");end=text.index("    changes['CODE_MANIFEST.json']",start)
text=text[:start]+'''    after['readable_trace'] = {
        'revision': VERSION, 'prior_inventory_sha256': sha(before_raw),
        'modified_paths': sorted(changes), 'source_candidate': spec['source_candidate'],
        'input_signature': state_key, 'output_signature': state['output_signature'],
        'prior_state': state['label'], 'registry_pins_verified': True,
        'requires_rebuilt_generation': False, 'field_deployment_status': 'NOT_VERIFIED',
        'prompt_search_budget_policy_changed': False,
    }
'''+text[end:]
start=text.index('    script = """',text.index('def local_verification'));end=text.index('    env = {',start)
text=text[:start]+'''    script = """
import sys,inspect
from pathlib import Path
from types import SimpleNamespace
from semantic_runtime.contracts import Contracts
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime import process_trace,request_report,observability,ad_request_report
root=Path(sys.argv[1]);c=Contracts(root)
for profile in c.pipeline['profiles']:
    StageRunner(SimpleNamespace(contracts=c,profile_id=profile)).verify_profile()
for module in (process_trace,request_report,observability,ad_request_report):
    assert Path(module.__file__).resolve().is_relative_to(root)
assert hasattr(process_trace,'ProcessTrace') and hasattr(process_trace,'ErrorSections')
assert 'detailed' in inspect.signature(request_report.capture_events).parameters
assert 'capture_events(request_id, detailed=True)' in (root/'service.py').read_text()
assert 'process_trace_path' in inspect.getsource(request_report)
print('READABLE_TRACE_ALL_PROFILES PASS; model calls=0')
print('READABLE_TRACE_CODE_ROOT='+str(root))
"""
'''+text[end:]
text=text.replace("    artifacts = path_at(root, 'TRANSFER/ad-request-logs-r2')", "    artifacts = Path.cwd() / 'readable-trace-r1-state'\n    if artifacts.is_symlink():\n        raise ValueError('State directory symlink is not supported')")
text=text.replace("        elif args.mode == 'apply':\n            apply(root, spec, artifacts)",'''        elif args.mode == 'apply':
            # Recover an interrupted transaction using its exact saved preimage.
            # Unknown later edits are rejected by undo before any restoration.
            for pending in sorted(artifacts.glob('backup-*/receipt.json')):
                receipt = json.loads(pending.read_bytes())
                if receipt.get('root') != str(root) or receipt.get('revision') != VERSION:
                    continue
                if receipt['state'] in ('PREPARED', 'APPLIED'):
                    print('RECOVER_INTERRUPTED=' + str(pending.parent), flush=True)
                    undo(root, pending.parent)
            apply(root, spec, artifacts)''')
text=text.replace('RAG_DISPLAY FAILED:', 'READABLE_TRACE FAILED:')
text=text.replace("    selected = generation or os.environ.get('GENOS_GENERATION')", """    if not (root/CONFIG).is_file():
        raise ValueError('Existing fixed GENOS_SERVING_PATHS.json required; apply MAIN_FULL first')
    binding = json.loads((root/CONFIG).read_bytes())
    selected = generation or os.environ.get('GENOS_GENERATION')""")
text=text.replace("    if (root/'.git').exists():", """    if (result['generation'] != str(Path(binding['generation']).resolve())
            or result['generation_manifest_sha256'] != binding['generation_manifest_sha256']):
        raise ValueError('Selected generation differs from the fixed binding; preserved')
    if (root/'.git').exists():""")
text=text.replace("            if not args.backup or not args.generation:\n                raise ValueError('gate requires exact BACKUP path and --generation')\n            backup = Path(args.backup).resolve(strict=True)", """            if not args.backup:
                candidates = []
                for path in artifacts.glob('backup-*/receipt.json'):
                    value = json.loads(path.read_bytes())
                    if (value.get('root') == str(root) and value.get('revision') == VERSION
                            and value.get('state') == 'VERIFIED'
                            and value.get('code_manifest_sha256') == sha((root/'CODE_MANIFEST.json').read_bytes())):
                        candidates.append(path.parent)
                if len(candidates) != 1:
                    raise ValueError('Supply exact BACKUP path; no unique applied receipt for this checkout')
                args.backup = str(candidates[0])
            backup = Path(args.backup).resolve(strict=True)""")
(H/'apply_patch.py').write_text(text)
s=importlib.util.spec_from_file_location('installer',H/'apply_patch.py'); installer=importlib.util.module_from_spec(s);s.loader.exec_module(installer)
base=B/'main_full_20261016_r1/code.zip'
sealed=json.loads((base.parent/'SEALED.json').read_bytes())
assert sha(base.read_bytes())==sealed['files']['code.zip']['sha256']
with zipfile.ZipFile(base) as z:payload={n:z.read(n) for n in z.namelist()}
manifest=json.loads(payload.pop('CODE_MANIFEST.json'))
binding=json.loads((A/'CODE_BINDING.json').read_bytes()); source={}
for name,pin in binding['changed_code'].items():
    raw=(R/name).read_bytes();assert sha(raw)==pin,name
    if name in payload:
        before=A/(Path(name).stem+'.before.py.gz')
        assert gzip.decompress(before.read_bytes())==payload[name],name
    source[name]=raw
candidate={**payload,**source}; changes=dict(source); additions={}
pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
active={e['manifest'] for e in pipeline['engines'].values()}
for name in binding['repinned_manifests']:
    engine=json.loads(payload[name]);oldpins=dict(engine['files'])
    for p in set(engine['files'])&set(source):engine['files'][p]=sha(source[p])
    if '02_BACKEND/semantic_runtime/request_report.py' in engine['files']:
        p='02_BACKEND/semantic_runtime/process_trace.py';engine['files'][p]=sha(source[p]);additions[name]=[p]
    assert all(v==engine['files'][p] for p,v in oldpins.items() if p not in source),name
    candidate[name]=enc(engine)
    if name not in active:changes[name]=candidate[name]
for entry in pipeline['engines'].values():entry['sha256']=sha(candidate[entry['manifest']])
candidate['00_SYSTEM/PIPELINE.json']=enc(pipeline)
installer.verify_bindings(candidate)
statekey=installer.signature(payload,manifest,{})
output=installer.signature(candidate,manifest,{})
spec={'revision':NAME,'source_candidate':'Working trace implementation, exact delta over mailed MAIN76 full code',
      'signatures':{statekey:{'label':'GENOS_MAIN_FULL_20261016_R1; fixed field generation binding preserved',
                             'output_signature':output,'patches':{n:{'before_sha256':sha(payload[n]) if n in payload else None,
                                   'after_sha256':sha(raw)} for n,raw in changes.items()}}},
      'blobs':{sha(raw):base64.b64encode(raw).decode() for raw in changes.values()},'engine_additions':additions}
(H/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec),mtime=0))
(H/'SOURCE_BINDING.json').write_bytes(enc({'revision':NAME,'prerequisite':base.parent.name,
 'base_code_zip_sha256':sha(base.read_bytes()),'base_inventory':statekey,'output_inventory':output,
 'source_files':{n:sha(raw) for n,raw in source.items()},'repinned_manifests':binding['repinned_manifests'],
 'base_serving_overlays_preserved':True,'selected_local_release_changed':False,
 'field_git_commit':None,'field_generation':None,'field_code_serving_revision':None,'field_verified':False}))
bundle=enc({'code':base64.b64encode((H/'apply_patch.py').read_bytes()).decode(),'spec':spec})
header='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export GENOS_PATCH_DEV="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"
task_logs="$PWD/readable-trace-r1-logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "READABLE_TRACE_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'READABLE_TRACE_LOG=%s\\n' "$task_log"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
if [[ $# -eq 0 ]]; then set -- check; fi
python3 - "$@" <<'READABLE_TRACE_PY'
import base64,hashlib,json,os,sys,types,zlib
'''
run=header+f"raw=zlib.decompress(base64.b64decode('{base64.b64encode(zlib.compress(bundle,9)).decode()}'))\n"
run+=f"assert hashlib.sha256(raw).hexdigest()=='{sha(bundle)}'\n"
run+="bundle=json.loads(raw);module=types.ModuleType('readable_trace_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\n"
run+="try:\n    raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\nexcept Exception as exc:\n    print('READABLE_TRACE FAILED: '+str(exc),file=sys.stderr,flush=True)\n    raise SystemExit(1)\nREADABLE_TRACE_PY\n"
(H/(NAME+'_RUN.txt')).write_text(run)
subprocess.run(['bash','-n',str(H/(NAME+'_RUN.txt'))],check=True)
(H/'SAMPLE.trace.txt').write_bytes((A/'SAMPLE.trace.txt').read_bytes())
(H/'WORKING_VALIDATION.json').write_bytes((A/'VALIDATION.json').read_bytes())
(H/'READABLE_TRACE_GUIDE.txt').write_bytes((R/'07_DOCS/REFERENCE/OPERATIONS/READABLE_REQUEST_TRACE.md').read_bytes())
print(json.dumps({'version':NAME,'source_files':len(source),'engine_manifests':len(binding['repinned_manifests']),
                  'run_bytes':len(run.encode()),'base_signature':statekey,'output_signature':output},indent=2))
