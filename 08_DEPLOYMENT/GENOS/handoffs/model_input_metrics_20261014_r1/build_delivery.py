"""Exact reviewed telemetry edits over sealed GENOS field inventories."""
import ast, base64, gzip, hashlib, importlib.util, json, subprocess, zlib
from pathlib import Path

O = Path(__file__).resolve().parent
R = O.parents[3]
N = 'GENOS_MODEL_INPUT_METRICS_20261014_R1'
sha = lambda b: hashlib.sha256(b).hexdigest()
enc = lambda v: (json.dumps(v, ensure_ascii=False, indent=2)+'\n').encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def predecessor_tools():
    return {key: (load('metrics_'+key, O.with_name(folder)/'apply_patch.py'),
        json.loads(gzip.decompress((O.with_name(folder)/'PATCH_SPEC.json.gz').read_bytes())))
        for key, folder in [('ad', 'ad_request_logs_20261013_r2'),
            ('success', 'successful_shortcut_20261013_r1'),
            ('gap', 'assessment_gap_action_20261013_r2'),
            ('guidance', 'public_failure_guidance_20261014_r1')]}


def main():
    assert not (O/(N+'.zip')).exists(), 'Preserve sealed handoff'
    old = load('metrics_prior_builder', O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    parents = predecessor_tools()
    prior = O.with_name('assessment_gap_action_20261013_r2')
    code = (prior/'apply_patch.py').read_text().replace('GENOS_ASSESSMENT_GAP_ACTION_20261013_R2', N)
    code = code.replace('assessment-gap-action-r2', 'model-input-metrics-r1').replace("'assessment_gap_action'", "'model_input_metrics'")
    code = code.replace('Source gap action correction; exact original gaps and source verification preserved', 'Model input metrics and final failure log repair; inference policy unchanged')
    code = code.replace('Install source gap action correction while preserving the verified code and budget overlay.', 'Install model input and final outcome logging while preserving verified code and budgets.')
    code = code.replace("assert 'ModelEventStream'", '''from semantic_runtime.legal_agent.model_contract import request_metrics,response_length_metrics
from semantic_runtime.request_report import final_response_summary
assert request_metrics({'messages':[{'role':'user','content':'가'}]})['input_content_utf8_bytes']==3
m=response_length_metrics({'max_tokens':6400},{'choices':[{'finish_reason':'length'}],'usage':{'prompt_tokens':15186,'completion_tokens':6400}})
assert m['length_diagnosis']=='output_cap_reached' and m['prompt_plus_max_tokens']==21586 and not m['context_limit_known']
v=final_response_summary({'status':422,'body':{'answer_status':'failed','message':'synthetic failure','failure_reason':'review_incomplete'}})
assert v['message']=='synthetic failure' and v['final_text_kind']=='failure_guidance' and not v['answer_present']
assert 'ModelEventStream' '''.rstrip())
    (O/'apply_patch.py').write_text(code)
    installer = load('metrics_installer', O/'apply_patch.py')
    names = ['02_BACKEND/semantic_runtime/'+n for n in (
        'legal_agent/model_contract.py', 'legal_agent/gateway.py', 'observability.py', 'request_report.py')]
    sources = {n: sha((R/n).read_bytes()) for n in names}
    spec = {'revision': N, 'signatures': {}, 'blobs': {}, 'engine_additions': {},
        'budget_policy': parents['gap'][1]['budget_policy']}
    cache, variants, bindings = {}, {}, []
    def patched(before, manifest, key):
        inst, sp = parents[key]
        state = sp['signatures'][inst.signature(before, manifest, sp)]
        updates = {n: base64.b64decode(sp['blobs'][row['after_sha256']]) for n, row in state['patches'].items()}
        after = old.repin(before, updates, sp['engine_additions'])
        assert inst.signature(after, manifest, sp) == state['output_signature']
        return after
    for label, payload, budget in old.predecessors():
        base = dict(payload)
        manifest = json.loads(base.pop('CODE_MANIFEST.json'))
        ad = patched(base, manifest, 'ad')
        success = patched(ad, manifest, 'success')
        for tag, state in [('ad', ad), ('success', success)]:
            gap = patched(state, manifest, 'gap')
            for suffix, before in [('gap', gap), ('guidance', patched(gap, manifest, 'guidance'))]:
                updates = {}
                for n in names:
                    key = n, sha(before[n])
                    if key not in cache:
                        cache[key] = old.transform(before[n], (O/'preimage'/n).read_bytes(), (R/n).read_bytes(), n)
                        ast.parse(cache[key], feature_version=(3,10))
                    raw = updates[n] = cache[key]
                    spec['blobs'][sha(raw)] = base64.b64encode(raw).decode()
                    variants.setdefault(n, {})[key[1]] = sha(raw)
                after = old.repin(before, updates, {})
                installer.verify_bindings(after)
                key = installer.signature(before, manifest, spec)
                output = installer.signature(after, manifest, spec)
                spec['signatures'][key] = {'label': label+'/'+tag+'/'+suffix,
                    'patches': {n: {'before_sha256': sha(before[n]), 'after_sha256': sha(raw)} for n, raw in updates.items()},
                    'output_signature': output}
                bindings.append({'label': label+'/'+tag+'/'+suffix, 'input_signature': key, 'output_signature': output})
    for (n, _), raw in cache.items():
        path = O/'reviewed'/n/(sha(raw)+'.py')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (O/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec), mtime=0))
    (O/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(enc(bindings), mtime=0))
    (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files': sources, 'field_variants': variants,
        'known_predecessors': len(spec['signatures']), 'field_status': 'NOT_VERIFIED',
        'model_calls': 0, 'local_active_release_changed': False}))
    bundle = enc({'code': base64.b64encode(code.encode()).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    py = 'import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
    py += "bundle=json.loads(raw);module=types.ModuleType('metrics_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
    header = (prior/'GENOS_ASSESSMENT_GAP_ACTION_20261013_R2_RUN.txt').read_text().split('python3 - "$@"', 1)[0]
    header = header.replace('assessment-gap-action-r2', 'model-input-metrics-r1').replace('ASSESSMENT_GAP_ACTION', 'MODEL_INPUT_METRICS')
    (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'METRICS_PY\'\n'+py+'METRICS_PY\n')
    subprocess.run(['bash', '-n', str(O/(N+'_RUN.txt'))], check=True)
    print(json.dumps({'inventories': len(spec['signatures']), 'variants': {n: len(v) for n, v in variants.items()}}))


if __name__ == '__main__': main()
