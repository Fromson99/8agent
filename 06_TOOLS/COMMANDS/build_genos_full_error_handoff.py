"""Package exact error-log fragments using the existing checked DEV installer."""
import argparse
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10'
PREFIX='GENOS_FULL_ERROR_LOGGING_20261007_R10'
PARENT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/investigation_budget_20261007_r1/GENOS_INVESTIGATION_BUDGET_20261007_R1_RUN.txt'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def replace_function(code,name,new):
    node=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=code.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+new.rstrip()+'\n\n'+''.join(lines[node.end_lineno:])


def existing_installer():
    txt=PARENT.read_text();start=txt.index('import base64');end=txt.index('\nBUDGET_PY',start)
    tree=ast.parse(txt[start:end])
    call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
        and n.func.attr=='b64decode' and n.args and isinstance(n.args[0],ast.Constant))
    bundle=json.loads(zlib.decompress(base64.b64decode(call.args[0].value)))
    return base64.b64decode(bundle['code']).decode()


TRANSFORM='''def transform(raw, operations):
    text=raw.decode('utf-8')
    for op in operations:
        variants=[op]+op.get('alternatives',[])
        if any(text.count(v['after'])==1 for v in variants):continue
        selected=next((v for v in variants if text.count(v['before'])==1),None)
        if selected is None:
            if op.get('compatible_absent_marker') and text.count(op['compatible_absent_marker'])==1:continue
            raise ValueError('Unsupported error-log fragment; existing code preserved: '+op['name'])
        text=text.replace(selected['before'],selected['after'],1)
    ast.parse(text,feature_version=(3,11))
    return text.encode('utf-8')
'''
LOCAL='''def local_verification(payload, spec):
    for name,operations in spec['files'].items():
        raw=payload[name]
        if transform(raw,operations)!=raw:raise ValueError('Full-error patch is incomplete: '+name)
        ast.parse(raw,feature_version=(3,11))
    name='02_BACKEND/semantic_runtime/legal_agent/readable_log.py'
    module={};exec(compile(payload[name],name,'exec'),module)
    probe='error-begin\\n'+'x'*45000+'\\nFULL_ERROR_END'
    text=module['render_detail']('AGENT LAW DECISION REJECTED',{'error':probe,'decision':{'queries':[]}})
    if json.loads(text.split('\\n',1)[1])['error']!=probe:raise ValueError('Error rendering is incomplete')
    print('FULL_ERROR_RENDER PASS; 45000+ characters preserved; no model calls',flush=True)
'''
PREPARE='''def prepare(root, spec):
    before,manifest,payload=payload_at(root);verify_bindings(payload)
    effective=dict(payload)
    for name,operations in spec['files'].items():effective[name]=transform(payload[name],operations)
    local_verification(effective,spec)
    source_changes={n for n in spec['files'] if effective[n]!=payload[n]}
    if not source_changes:return before,payload,{},manifest
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for name,raw in list(payload.items()):
        if name.startswith('02_BACKEND/ENGINES/') and name.endswith('.json'):
            engine=json.loads(raw);files=engine.get('files',{})
            affected=set(files)&source_changes
            if affected:
                for path in affected:files[path]=sha(effective[path])
                effective[name]=encoded(engine)
    for binding in pipeline['engines'].values():binding['sha256']=sha(effective[binding['manifest']])
    effective['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
    verify_bindings(effective)
    after=json.loads(before)
    for row in after['files']:
        raw=effective[row['path']];row.update(sha256=sha(raw),bytes=len(raw))
    for row in after.get('required_files',[]):
        if not isinstance(row,dict):raise ValueError('Unsupported legacy inventory; preserved')
        if row['path'] in effective:row['sha256']=sha(effective[row['path']])
    changes={n:r for n,r in effective.items() if r!=payload[n]}
    after['full_error_logging']={'revision':VERSION,'prior_inventory_sha256':sha(before),
        'modified_paths':sorted(changes),'field_deployed':False}
    changes['CODE_MANIFEST.json']=encoded(after)
    return before,payload,changes,after
'''
VERIFY='''def verify(root, spec):
    _,manifest,payload=payload_at(root);verify_bindings(payload);local_verification(payload,spec)
    return manifest
'''


def fragments(before):
    original=json.loads((before/'before.json').read_text());files={}
    for name,expected in original.items():
        old=(before/name).read_bytes();new=(SOURCE/name).read_bytes()
        assert sha(old)==expected
        if old==new:continue
        a=old.decode().splitlines(keepends=True);b=new.decode().splitlines(keepends=True)
        for context in (1,2,3,6,12,24):
            operations=[]
            for index,group in enumerate(difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_grouped_opcodes(context)):
                old_part=''.join(a[group[0][1]:group[-1][2]]);new_part=''.join(b[group[0][3]:group[-1][4]])
                operations.append({'name':name+':'+str(index),'before':old_part,'after':new_part})
            if all(old.decode().count(o['before'])==1 and new.decode().count(o['after'])==1 for o in operations):break
        else:raise ValueError('Ambiguous fragment: '+name)
        files[name]=operations
    compatible_fragments(files,before)
    return {'revision':PREFIX,'files':files,'source_before_sha256':original,
        'source_after_sha256':{n:sha((SOURCE/n).read_bytes()) for n in files},
        'generation_modified':False,'model_or_prompt_policy_modified':False}


def compatible_fragments(files,before):
    name='02_BACKEND/semantic_runtime/progress.py'
    anchor='        if name == "request.finished":\n            self.poll_journal()\n            self._flush_reads(force=True)\n'
    op=next(o for o in files[name] if "if fields.get('ok') is False" in o['after'])
    op['before']=anchor;op['after']=anchor+"            if fields.get('ok') is False:label='요청 처리 실패 · 오류 로그를 확인해 주세요'\n"
    name='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py';old=(before/name).read_text();new=(SOURCE/name).read_text()
    replacements=[]
    for op in files[name]:
        if 'if len(self.flow_events) < 256 or full_error:' in op['after']:
            op['before']='        if len(self.flow_events) < 256:\n';op['after']='        if len(self.flow_events) < 256 or full_error:\n'
            op['compatible_absent_marker']='''        if kind == "heartbeat":
            if elapsed - self.last_heartbeat < 30000:
                return
            self.last_heartbeat = elapsed
'''
        elif "body += render_error({'stage':label" in op['after']:
            anchor='''            if details:
                body += "\\n\\n".join("- " + self._plain(row) for row in details) + "\\n\\n"
'''
            op['before']=anchor;op['after']="            if full_error:\n                body += render_error({'stage':label,'logs':details})+'\\n\\n'\n            el"+anchor.removeprefix('            ')
            op['alternatives']=[{'before':'\n'.join('    '+line if line else line for line in op['before'].split('\n')),
                'after':'\n'.join('    '+line if line else line for line in op['after'].split('\n'))}]
            legacy=op['alternatives'][0]
            op['alternatives'].append({k:v.replace('"\\n\\n".join','"\\n".join') for k,v in legacy.items()})
        elif 'def render_error(' in op['after']:
            helper=next(n for n in ast.parse(new).body if isinstance(n,ast.FunctionDef) and n.name=='render_error')
            source=''.join(new.splitlines(keepends=True)[helper.lineno-1:helper.end_lineno])
            replacements.append({'name':name+':render_error_helper','before':'\ndef render(',
                'after':'\n'+source+'\n\ndef render('})
            start=old.index('    if isinstance(status, int) and status >= 400:',old.index('\ndef render('))
            end=old.index('    answer = _public_answer_text(body)',start)
            replacements.append({'name':name+':render_error_body','before':old[start:end],
                'after':'    if isinstance(status, int) and status >= 400:\n        return render_error(body)\n'})
            continue
        elif 'detail = raw_error.decode' in op['before']:
            pairs=[
                ('        raw_error = _raw_http_error(exc, request_id)\n','        raw_error = _raw_http_error(exc, request_id)\n'),
                ('        detail = raw_error.decode("utf-8", "replace")[:2000]\n','        detail = raw_error.decode("utf-8", "replace")\n'),
                ('        error_diagnostics = _http_error_diagnostics(exc, raw_error[:16384], question)\n','        error_diagnostics = _http_error_diagnostics(exc, raw_error, question)\n'),
                ('''        except ValueError:
            failure = {}
        service_error = (isinstance(failure.get("code"), str)
                         and isinstance(failure.get("detail"), str))
''',"        except ValueError:\n            failure = {'error_type':type(exc).__name__,'detail':detail}\n"),
                ('''            "text": ("실행 오류 (" + failure["code"] + "): " + _redact_http_error(failure["detail"], question)[:1000]) if service_error else
                    f"지금 답변을 가져오지 못했습니다. (코드서빙 응답 {exc.code}, 추적 번호: {request_id})",
''',"            \"text\": render_error({**failure,'_gateway_status':exc.code,'request_id':request_id},question=question),\n"),
                ('''        if failure.get("code") in ("SOURCE_INVESTIGATION_INCOMPLETE","MODEL_UPSTREAM_UNAVAILABLE"):
            failed["text"]=render({**failure,"_gateway_status":exc.code})
        await display.finish(failed["text"])
''','        # The complete received HTTP error has already been rendered above.\n        await display.finish(failed["text"])\n')]
            entries=[{'name':name+':http-error-'+str(i),'before':a,'after':b} for i,(a,b) in enumerate(pairs)]
            entries[0]['alternatives']=[{'before':'        raw_error = exc.read(16384)\n','after':'        raw_error = exc.read()\n'}]
            replacements.extend(entries)
            continue
        elif 'failure["http_error_diagnostics"]' in op['before']:
            line='            failure["http_error_diagnostics"] = _http_error_diagnostics(exc, _raw_http_error(exc, data["request_id"])[:16384])\n'
            op['before']=line;op['after']=line.replace('[:16384]','')
            op['alternatives']=[{'before':'            failure["http_error_diagnostics"] = _http_error_diagnostics(exc, exc.read(16384))\n',
                'after':'            failure["http_error_diagnostics"] = _http_error_diagnostics(exc, exc.read())\n'}]
        elif 'traceback=traceback.format_exc()[-4000:]' in op['before']:
            replacements.append({'name':name+':client-exception-log',
                'before':'            error_message=str(exc)[:500],\n            traceback=traceback.format_exc()[-4000:],\n',
                'after':'            error_message=str(exc),\n            traceback=traceback.format_exc(),\n'})
            replacements.append({'name':name+':client-exception-text',
                'before':'''            "text": f"지금 답변을 가져오지 못했습니다. (추적 번호: {request_id})",
            "answer_status": "failed",
            "failure_kind": "client_exception",
''',
                'after':'''            "text": render_error({'request_id':request_id,'error_type':type(exc).__name__,
                'detail':str(exc),'traceback':traceback.format_exc()},question=question),
            "answer_status": "failed",
            "failure_kind": "client_exception",
'''})
            continue
        replacements.append(op)
    files[name]=replacements


def main():
    global SOURCE
    parser=argparse.ArgumentParser();parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=ROOT,help='Frozen verified source root; avoids unrelated concurrent edits')
    args=parser.parse_args();SOURCE=args.source.resolve(strict=True)
    if (OUT/'DELIVERY.json').exists():raise ValueError('Preserve built handoff; use a new revision')
    OUT.mkdir(parents=True,exist_ok=True);spec=fragments(args.before)
    code=existing_installer()
    code=code.replace("VERSION = 'GENOS_INVESTIGATION_BUDGET_20261007_R1'",f"VERSION = '{PREFIX}'")
    code=code.replace("MANAGED = ('service.py', 'CODE_MANIFEST.json')","MANAGED = ()")
    for name,new in [('transform',TRANSFORM),('local_verification',LOCAL),('prepare',PREPARE),('verify',VERIFY)]:
        code=replace_function(code,name,new)
    code=code.replace("if tuple(row['path'] for row in receipt['files']) != MANAGED:",
        "if len({r['path'] for r in receipt['files']})!=len(receipt['files']) or not set(r['path'] for r in receipt['files']) <= set(MANAGED):")
    code=code.replace('for name in MANAGED:',"for name in (r['path'] for r in receipt['files']):")
    code=code.replace("    artifacts = path_at(root, 'TRANSFER/investigation-budget-r1')",'''    global MANAGED
    _,_,installed=payload_at(root)
    MANAGED=tuple(spec['files'])+tuple(n for n in installed if n.startswith('02_BACKEND/ENGINES/') and n.endswith('.json'))+('00_SYSTEM/PIPELINE.json','CODE_MANIFEST.json')
    artifacts = path_at(root, 'TRANSFER/full-error-logging-r1')''')
    code=code.replace("print('BUDGET_INSTALL FAILED: ' + str(exc), file=sys.stderr, flush=True)","import traceback;traceback.print_exc()")
    code=code.replace('BUDGET_INSTALL','FULL_ERROR_INSTALL')
    code=code.replace('full-error-logging-r1','full-error-logging-r10')
    code=code.replace("    verify(root, spec)\n    archive =", "    verify(root, spec)\n    atomic(backup/'CHANGED_FILES.txt', ('\\n'.join(changes)+'\\n').encode())\n    archive =")
    ast.parse(code,feature_version=(3,11));(OUT/'INSTALL.py').write_text(code);(OUT/'PATCH_SPEC.json').write_bytes(encoded(spec))
    bundle=encoded({'code':base64.b64encode(code.encode()).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    run=f'''#!/usr/bin/env bash
set -Eeuo pipefail
dev="${{GENOS_DEV_ROOT:-${{GENOS_DEV:-$HOME/DEV}}}}"
run_dir="$dev/TRANSFER/full-error-logging-r10/run-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$run_dir"
exec > >(tee -a "$run_dir/RUN.log") 2>&1
trap 'rc=$?; echo "EXIT=$rc"; printf "{{\\"exit_code\\":%s}}\\n" "$rc" > "$run_dir/EXIT_STATUS.json"' EXIT
echo "RUN_DIR=$run_dir"
python3 - "$@" <<'FULL_ERROR_PY'
import base64,hashlib,json,types,zlib
raw=zlib.decompress(base64.b64decode('{packed}'))
assert hashlib.sha256(raw).hexdigest()=='{sha(bundle)}','Embedded installer mismatch'
bundle=json.loads(raw);module=types.ModuleType('full_error_install');module.__file__='embedded-full-error-install.py'
exec(compile(base64.b64decode(bundle['code']),module.__file__,'exec'),module.__dict__)
raise SystemExit(module.main(bundle['spec']))
FULL_ERROR_PY
'''
    (OUT/(PREFIX+'_RUN.txt')).write_text(run)
    diagnostics=(ROOT/'genos_diagnostics.py').read_bytes()
    bootstrap=("import base64,hashlib,os,sys,types,zlib\nfrom pathlib import Path\n"
        + "_raw=zlib.decompress(base64.b64decode("+repr(base64.b64encode(zlib.compress(diagnostics,9)).decode())+"))\n"
        + "assert hashlib.sha256(_raw).hexdigest()=="+repr(sha(diagnostics))+"\n"
        + "_mod=types.ModuleType('genos_diagnostics')\n_mod.__file__=str(Path.cwd()/'genos_diagnostics.py')\n"
        + "sys.modules['genos_diagnostics']=_mod\nexec(compile(_raw,_mod.__file__,'exec'),_mod.__dict__)\n").encode()
    (OUT/'WORKFLOW_PASTE_ALL.txt').write_bytes(bootstrap+(SOURCE/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes())
    docs=ROOT/'08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r8'
    (OUT/'GUIDE_UTF8.txt').write_text((docs/'GUIDE_UTF8.txt').read_text().replace('R8','R10').replace('r8','r10'))
    (OUT/'READ_ERROR_LOGS.txt').write_bytes((docs/'READ_ERROR_LOGS.txt').read_bytes())
    rows=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in
        (OUT/'INSTALL.py',OUT/'PATCH_SPEC.json',OUT/(PREFIX+'_RUN.txt'),OUT/'WORKFLOW_PASTE_ALL.txt',
         OUT/'GUIDE_UTF8.txt',OUT/'READ_ERROR_LOGS.txt')]
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded({'format':'8agent-code/1','patch':PREFIX,'files':rows}))
    archive=OUT/(PREFIX+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for row in rows:z.write(OUT/row['path'],row['path'])
        z.write(OUT/'CODE_MANIFEST.json','CODE_MANIFEST.json')
    (OUT/'DELIVERY.json').write_bytes(encoded({'revision':PREFIX,'zip':archive.name,'zip_sha256':sha(archive.read_bytes()),
        'run_txt_sha256':sha((OUT/(PREFIX+'_RUN.txt')).read_bytes()),'verified_working_root':str(ROOT),
        'verified_source_root':str(SOURCE),
        'code_root_expected':'~/DEV (resolved existing Git checkout)','generation':None,'generation_manifest_sha256':None,
        'git_push':False,'code_serving_revision':None,'field_workflow_test':False,'email_sent':False,
        'source_sha256':spec['source_after_sha256'],'installer_parent_sha256':sha(PARENT.read_bytes()),
        'workflow_embedded_diagnostics_sha256':sha(diagnostics),
        'workflow_txt_sha256':sha((OUT/'WORKFLOW_PASTE_ALL.txt').read_bytes())}))
    subprocess.run(['bash','-n',str(OUT/(PREFIX+'_RUN.txt'))],check=True)
    print(json.dumps({'output':str(OUT),'source_files':len(spec['files']),'zip_bytes':archive.stat().st_size}))


if __name__=='__main__':main()
