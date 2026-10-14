"""Bind MAIN53 scoped fulltext support to the preserved R2 cache variants."""
import ast, base64, difflib, gzip, hashlib, importlib.util, json, subprocess, zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRIOR = OUT.with_name('rag_focused_rules_20261013_r2')
R1 = OUT.with_name('rag_focused_rules_20261013_r1')
NAME = 'GENOS_RAG_FOCUSED_RULES_20261013_R3'
TARGET = '02_BACKEND/semantic_runtime/unit_fulltext.py'
RELEASE = ROOT/'08_DEPLOYMENT/RELEASES/focused-rules-20261013-r1'
sha = lambda b: hashlib.sha256(b).hexdigest()
encoded = lambda o: (json.dumps(o, ensure_ascii=False, indent=2)+'\n').encode()

def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m

def scoped(raw, new):
    text = raw.decode()
    pairs = [
        ('kind, identity=None):', 'kind, identity=None, unit_keys=None):'),
        ("'scope': sorted(scope), 'kind': kind, 'identity': identity})",
         "'scope': sorted(scope), 'kind': kind, 'identity': identity,\n                          **({'unit_keys':sorted(set(unit_keys))} if unit_keys is not None else {})})"),
        ('        return where, params, binding, offset, bool(terms and scope)',
         "        if unit_keys is not None:\n            where += ' AND u.key IN (SELECT value FROM json_each(?))'; params.append(json.dumps(sorted(set(unit_keys))))\n        return where, params, binding, offset, bool(terms and scope and (unit_keys is None or unit_keys))"),
        ('cursor=None, limit=12):', 'cursor=None, limit=12, unit_keys=None):'),
        ('cursor=None, limit=8):', 'cursor=None, limit=8, unit_keys=None):'),
        ('cursor=None, limit=16):', 'cursor=None, limit=16, unit_keys=None):'),
        ("limit, 'laws')", "limit, 'laws', unit_keys=unit_keys)"),
        ("limit, 'articles', document_id)", "limit, 'articles', document_id, unit_keys=unit_keys)"),
        ("limit, 'hits', source_id)", "limit, 'hits', source_id, unit_keys=unit_keys)"),
    ]
    for old, replacement in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, replacement, 1)
    old = 'projection = self._projection(db, terms, allowed)'
    assert text.count(old) == 3
    text = text.replace(old, old+' if unit_keys is None else None')
    # The query/aggregation methods are byte-identical to validated MAIN53.
    def methods(source):
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name=='UnitFulltextIndex')
        lines = source.splitlines(keepends=True)
        return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in cls.body if isinstance(n, ast.FunctionDef)}
    before, after, main = methods(raw.decode()), methods(text), methods(new.decode())
    changed = {'_page_query','law_groups_page','article_groups_page','hit_page'}
    assert all(before[n] == after[n] for n in before if n not in changed)
    assert all(after[n] == main[n] for n in changed-{'hit_page'})
    ast.parse(text, feature_version=(3,10))
    return text.encode()

def main():
    assert not (OUT/(NAME+'.zip')).exists(), 'Preserve sealed delivery'
    b = load('r3_frozen_r1_build', R1/'build_delivery.py')
    a = load('r3_frozen_r2_apply', PRIOR/'apply_patch.py')
    app = load('r3_apply', OUT/'apply_patch.py')
    catalogue, states, budget = b.source_material()
    r1 = json.loads(gzip.decompress((R1/'PATCH_SPEC.json.gz').read_bytes()))
    r2 = json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
    new = (RELEASE/'code'/TARGET).read_bytes()
    release = json.loads((RELEASE/'release.json').read_bytes())
    assert sha(new) == release['files'][TARGET]
    assert (ROOT/TARGET).read_bytes() == new
    variants = {}
    for h in sorted({s['pins'][TARGET] for s in states}):
        old = catalogue[h];fixed = scoped(old, new)
        variants[h] = {'before_sha256':h,'after_sha256':sha(fixed),
                       'before':base64.b64encode(old).decode(),'after':base64.b64encode(fixed).decode()}
        p = OUT/'payload'/sha(fixed)/'unit_fulltext.py';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(fixed)
        p = OUT/'reviewed'/(h+'.diff');p.parent.mkdir(exist_ok=True)
        p.write_text(''.join(difflib.unified_diff(old.decode().splitlines(True),fixed.decode().splitlines(True),fromfile='R2',tofile='R3')))
    spec = {'revision':NAME,'prior_revision':'GENOS_RAG_FOCUSED_RULES_20261013_R2',
            'budget_policy':budget,'target':TARGET,'variants':variants,'predecessors':{},
            'source_release':'focused-rules-20261013-r1',
            'source_release_manifest_sha256':sha((RELEASE/'release.json').read_bytes()),
            'source_unit_fulltext_sha256':sha(new),
            'prior_code_zip_sha256':json.loads((PRIOR/'HANDOFF.json').read_bytes())['code_zip_sha256']}
    bindings = []
    for state in states:
        payload = {n:catalogue[h] for n,h in state['pins'].items()}
        manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
        pin = a.signature(payload,manifest,r1);patch = r1['signatures'][pin]
        final = {**payload,**{n:base64.b64decode(r1['blobs'][p['after_sha256']]) for n,p in patch['patches'].items()}}
        pipeline = json.loads(payload['00_SYSTEM/PIPELINE.json'])
        for entry in pipeline['engines'].values():
            name=entry['manifest'];engine=json.loads(payload[name])
            for target in set(engine['files'])&set(patch['patches']):engine['files'][target]=sha(final[target])
            for target in r1['engine_additions'].get(name,[]):engine['files'][target]=sha(final[target])
            final[name]=encoded(engine);entry['sha256']=sha(final[name])
        final['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
        r1_pin = a.signature(final,manifest,r1)
        assert r1_pin == patch['output_signature']
        final.update(a.repinned(final,r2))
        r2_pin = a.signature(final,manifest,r2)
        spec['predecessors'].setdefault(r2_pin,[]).append(r1_pin)
        original = dict(final);final.update(app.repinned(final,spec));app.verify_bindings(final)
        reverse = {**final,**app.repinned(final,spec,reverse=True)}
        assert reverse == original
        bindings.append({'label':state['label'],'r1_signature':r1_pin,'r2_signature':r2_pin,
                         'r3_signature':app.signature(final,manifest,spec),'unit_fulltext_sha256':sha(final[TARGET]),
                         'cache_methods_preserved':True})
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
    (OUT/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(encoded(bindings),mtime=0))
    code = (OUT/'apply_patch.py').read_bytes();ast.parse(code,feature_version=(3,10))
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    py=('import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+
        "bundle=json.loads(raw);module=types.ModuleType('focused_r3_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    prior=(PRIOR/'GENOS_RAG_FOCUSED_RULES_20261013_R2_RUN.txt').read_text()
    run=prior[:prior.index('python3 - "$@"')].replace('rag-focused-rules-r2','rag-focused-rules-r3')+'python3 - "$@" <<\'FOCUSED_RAG_PY\'\n'+py+'FOCUSED_RAG_PY\n'
    (OUT/(NAME+'_RUN.txt')).write_text(run)
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    hand={k:spec[k] for k in ('source_release','source_release_manifest_sha256','prior_code_zip_sha256','source_unit_fulltext_sha256')}
    hand.update(version=NAME,source_code_root=str(RELEASE/'code'),required_predecessor=spec['prior_revision'],
                changed_implementation=[TARGET],unit_variants={h:v['after_sha256'] for h,v in variants.items()},
                known_r2_output_signatures=len(spec['predecessors']),run_txt_sha256=sha(run.encode()),
                local_active_pointer_sha256=sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
                field_code_root='~/DEV',field_git_commit=None,field_generation=None,field_generation_manifest_sha256=None,
                field_code_serving_revision=None,genos_applied=False,genos_deployed=False,workflow_test='NOT_RUN',email_status='NOT_SENT')
    (OUT/'HANDOFF.json').write_bytes(encoded(hand))
    print(json.dumps({'version':NAME,'variants':len(variants),'r2_inventories':len(spec['predecessors']),'run_bytes':len(run.encode())}))

if __name__=='__main__':main()
