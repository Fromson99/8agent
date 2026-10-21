"""Historical initial script generator; later reviewed files are authoritative. Do not rerun on a sealed delivery."""
from pathlib import Path
import re
H=Path(__file__).resolve().parent;R=H.parents[3];B=H.parent
assert not (H/'SEALED.json').exists()
p=H/'build.py';s=p.read_text();s=s.replace("assert sha((R/n).read_bytes())==pin,('Working drift after validation',n)","assert n=='02_BACKEND/semantic_runtime/deployment_paths.py' or sha((R/n).read_bytes())==pin,('Working drift after validation',n)")
p.write_text(s)
s=(B/'session_identity_20261019_r1/run.py').read_text().replace('MAIN87 plus team/session identity; preserve field data and selection.','MAIN88 plus Oracle selective query; preserve field data and selection.')
a=s.index('def identity(');b=s.index('\ndef archive(',a)
s=s[:a]+'''def identity(root,staged,explicit):
    path=rep.plain(root/CONFIG)
    raw=path.read_bytes() if path.exists() else None
    generation=str(explicit.resolve(strict=True)) if explicit else None
    if raw is not None:
        config=json.loads(raw)
        generation=generation or config.get('generation')
    return {'code_root':str(root),'generation':generation,
            'fixed_config_sha256':sha(raw) if raw is not None else None},raw
''' +s[b:]
s=s.replace("files={n:raw for n,(raw,_) in content.items() if n!='CODE_MANIFEST.json'};files[CONFIG]=config_raw", "files={n:raw for n,(raw,_) in content.items() if n!='CODE_MANIFEST.json'}\n    if config_raw is not None:files[CONFIG]=config_raw")
s=s.replace("manifest['field_binding']=ident;manifest['required_files'].append({'path':CONFIG,'sha256':sha(config_raw)})", "manifest['field_binding']=ident\n    if config_raw is not None:manifest['required_files'].append({'path':CONFIG,'sha256':sha(config_raw)})")
s=s.replace("'gate-code','gate','undo'","'gate-code','gate-sqlite','undo','deps'")
s=s.replace("    with rep.plain(root/'.genos-code-replacement.lock').open('a') as lock:",'''    if args.action=='deps':
        binding=json.loads((H/'PACKAGE_SPEC.json').read_bytes())
        wheels=[]
        for name,pin in binding['wheels'].items():
            path=rep.plain(H/'wheels'/name)
            if sha(path.read_bytes())!=pin:raise ValueError('Wheel changed: '+name)
            wheels.append(path)
        command([sys.executable,'-m','pip','install','--no-index','--no-deps',*wheels],root)
        return
    with rep.plain(root/'.genos-code-replacement.lock').open('a') as lock:''')
s=s.replace("('status','gate-code','gate')","('status','gate-code','gate-sqlite')").replace("('gate-code','gate')","('gate-code','gate-sqlite')")
s=s.replace(",'--generation',ident['generation']",'')
s=s.replace("if args.action=='gate-code':argv.append('--code-only')", "if args.action=='gate-code':argv.append('--code-only')\n                else:\n                    if not ident['generation']:raise ValueError('SQLite gate requires --generation')\n                    argv.extend(['--generation',ident['generation']])")
s=s.replace('CODE_GATE_PASSED_GENERATION_UNVERIFIED','CODE_GATE_PASSED_ORACLE_FIELD_UNVERIFIED').replace('SESSION_IDENTITY','MAIN88_ORACLE_QUERY')
(H/'run.py').write_text(s)
s=(B/'main87_patch_20261019_r1/code_smoke.py').read_text()
s=s.replace('assert Path(semantic_runtime.app.__file__)', '''import semantic_runtime.oracle_query_service,semantic_runtime.oracle_query_db
import lawrag.pipeline.oracle_query_publish
import sqlglot
assert sqlglot.__version__=='30.23.0'
assert Path(semantic_runtime.app.__file__)''')
(H/'code_smoke.py').write_text(s)
s=(B/'main87_patch_20261019_r1/installed_contract_runner.py').read_text()
s=s.replace("generation=Path(args[1] if len(args)>1 else kw['generation'])", "generation_value=args[1] if len(args)>1 else kw.get('generation')\n    generation=Path(generation_value) if generation_value is not None else None")
s=s.replace("if 'pytest-' in str(generation):", "if generation is not None and 'pytest-' in str(generation):")
a=s.index('    @pytest.fixture\n    def tmp_path');b=s.index('    def pytest_collection_modifyitems',a);s=s[:a]+s[b:]
(H/'installed_contract_runner.py').write_text(s)
