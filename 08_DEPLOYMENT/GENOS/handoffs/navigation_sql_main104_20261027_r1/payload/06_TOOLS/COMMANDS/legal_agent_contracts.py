"""Generate schemas and opt-in candidate manifests; never change active pointers.

This is code/contract packaging, not a quality experiment or MAIN promotion.
Run after editing candidate code so every executed file is hash-bound.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from semantic_runtime.contracts import sha
from semantic_runtime.legal_agent.protocol import SCHEMA
from semantic_runtime.legal_agent.domain import DOMAIN, DEFAULT_PROFILE


def build(root):
    root = Path(root)

    def emit(relative, value):
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        return sha(path)

    pipeline_path = root/'00_SYSTEM/PIPELINE.json'
    config = json.loads(pipeline_path.read_text())
    domain_path = '00_SYSTEM/LEGAL_AGENT/domain-v1.json'
    profile_path = '00_SYSTEM/LEGAL_AGENT/profile-source-only.json'
    domain_hash = emit(domain_path, DOMAIN)
    profile_hash = emit(profile_path, DEFAULT_PROFILE)
    schema_path = '00_SYSTEM/SCHEMAS/legal-agent-v1.schema.json'
    config['contracts']['legal.control'] = {'schema_path': schema_path, 'schema_sha256': emit(schema_path, SCHEMA), 'schema_definition': 'Control'}
    config['authorities']['legal_agent'] = '07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_DOUBLE_HARNESS.md'
    new_files = [p for p in (root/'02_BACKEND/semantic_runtime/legal_agent').iterdir() if p.suffix in ('.py', '.sql')]
    new_files += [root/'02_BACKEND/semantic_runtime/stage_runner.py', root/'02_BACKEND/semantic_runtime/legal_agent_adapter.py']
    new_pins = {str(p.relative_to(root)): sha(p) for p in sorted(new_files)}
    # Existing engines import app/Pipeline. Re-pin their working-code dependencies
    # without changing their profile parameters or selected data/index bindings.
    for entry in config['engines'].values():
        if not entry['manifest'].startswith('02_BACKEND/ENGINES/term_runtime/'):
            continue
        manifest = json.loads((root/entry['manifest']).read_text())
        manifest['files'] = {file: sha(root/file) for file in manifest['files']}
        manifest['files'].update(new_pins)
        entry['sha256'] = emit(entry['manifest'], manifest)
    common = deepcopy(json.loads((root/config['engines']['term-retrieve@1.0.0']['manifest']).read_text())['files'])
    common[domain_path] = domain_hash
    common[profile_path] = profile_hash
    common['00_SYSTEM/WORKSPACE.json'] = sha(root/'00_SYSTEM/WORKSPACE.json')
    common['02_BACKEND/lawrag/platform/workspace.py'] = sha(root/'02_BACKEND/lawrag/platform/workspace.py')
    nodes = []
    term_config = deepcopy(config['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent'])
    term_config.update(implementation='legal-agent-v1', legal_agent={
        'domain': {'path': domain_path, 'sha256': domain_hash},
        'profile': {'path': profile_path, 'sha256': profile_hash}})
    for stage, kind, inp, out in [('retrieve', 'RETRIEVER', 'request', 'retrieved'),
                                  ('select', 'RETRIEVER', 'retrieved', 'selected'),
                                  ('assemble', 'ASSEMBLER', 'selected', 'assembled'),
                                  ('answer', 'ANSWERER', 'assembled', 'result')]:
        slot = 'legal-'+stage
        engine = slot+'@candidate-v1'
        inputs, outputs = {inp: 'runtime.'+inp}, {out: 'runtime.'+out}
        if stage == 'answer':
            outputs['control'] = 'legal.control'
        config['slots'][slot] = {'kind': kind, 'inputs': inputs, 'outputs': outputs}
        path = '02_BACKEND/ENGINES/legal_agent/1.0.0/'+stage+'.json'
        manifest = {'schema_version': 'pipeline-engine-v1', 'id': engine, 'version': '1.0.0',
                    'kind': kind, 'maturity': 'TOOL', 'inputs': inputs, 'outputs': outputs,
                    'entrypoint': {'path': '02_BACKEND/semantic_runtime/legal_agent/stages.py', 'function': stage},
                    'files': common, 'parameters_schema': {'type': 'object', 'properties': {
                        'term_agent': {'type': 'object'}} if stage == 'retrieve' else {}, 'additionalProperties': False},
                    'migration': None, 'experiment_binding': None}
        config['engines'][engine] = {'manifest': path, 'sha256': emit(path, manifest)}
        upstream = {'retrieve': '$input.request', 'select': 'retrieve.retrieved', 'assemble': 'select.selected', 'answer': 'assemble.assembled'}[stage]
        nodes.append({'id': stage, 'slot': slot, 'engine': engine, 'bindings': {inp: upstream},
                      'parameters': {'term_agent': term_config} if stage == 'retrieve' else {}})
    config['profiles']['legal-agent-rag-v1'] = {'mode': 'tool', 'status': 'READY', 'inputs': {'request': 'runtime.request'},
                                              'nodes': nodes, 'outputs': {'result': 'answer.result'}}
    emit('00_SYSTEM/PIPELINE.json', config)
    return {'profile': 'legal-agent-rag-v1', 'default_profile_changed': False, 'active_release_changed': False,
            'model_quality_validated': False, 'engine_count': 4}


def build_v2(root, *, default=False):
    """Package v2 working-code contracts; default selection is explicitly requested."""
    from semantic_runtime.legal_agent.tools_protocol import SCHEMA as V2_SCHEMA
    from semantic_runtime.legal_agent.tools_policy import DOMAIN as V2_DOMAIN, DEFAULT_PROFILE as V2_PROFILE
    root = Path(root)
    def emit(relative, value):
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        return sha(path)
    config = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    domain_path = '00_SYSTEM/LEGAL_AGENT/domain-v2.json'
    profile_path = '00_SYSTEM/LEGAL_AGENT/profile-tools-v2.json'
    domain_hash = emit(domain_path, V2_DOMAIN)
    if not (root/profile_path).exists(): emit(profile_path, V2_PROFILE)
    from semantic_runtime.legal_agent.tools_policy import profile
    profile(json.loads((root/profile_path).read_text()))
    profile_hash = sha(root/profile_path)
    schema_path = '00_SYSTEM/SCHEMAS/tool-exploration-v2.schema.json'
    config['contracts']['legal.control-v2'] = {'schema_path': schema_path, 'schema_sha256': emit(schema_path, V2_SCHEMA), 'schema_definition': 'Control'}
    common = deepcopy(json.loads((root/config['engines']['term-retrieve@1.0.0']['manifest']).read_text())['files'])
    for p in (root/'02_BACKEND/semantic_runtime/legal_agent').iterdir():
        if p.suffix in ('.py', '.sql'): common[str(p.relative_to(root))] = sha(p)
    for p in [domain_path, profile_path, '00_SYSTEM/WORKSPACE.json', '02_BACKEND/lawrag/platform/workspace.py']:
        common[p] = sha(root/p)
    common = {p: sha(root/p) for p in sorted(common)}
    base = config['profiles'].get('document-navigation-rag-v1', config['profiles']['legal-rag'])
    term = deepcopy(base['nodes'][0]['parameters']['term_agent'])
    term.update(implementation='legal-agent-tools-v2', legal_agent={
        'domain': {'path': domain_path, 'sha256': domain_hash}, 'profile': {'path': profile_path, 'sha256': profile_hash}})
    nodes = []
    for stage, kind, inp, out in [('retrieve','RETRIEVER','request','retrieved'), ('select','RETRIEVER','retrieved','selected'),
                                 ('assemble','ASSEMBLER','selected','assembled'), ('answer','ANSWERER','assembled','result')]:
        slot = 'legal-v2-'+stage; engine = slot+'@2.0.0'
        inputs, outputs = {inp: 'runtime.'+inp}, {out: 'runtime.'+out}
        if stage == 'answer': outputs['control'] = 'legal.control-v2'
        config['slots'][slot] = {'kind': kind, 'inputs': inputs, 'outputs': outputs}
        path = '02_BACKEND/ENGINES/legal_agent/2.0.0/'+stage+'.json'
        manifest = {'schema_version': 'pipeline-engine-v1', 'id': engine, 'version': '2.0.0',
            'kind': kind, 'maturity': 'TOOL', 'inputs': inputs, 'outputs': outputs,
            'entrypoint': {'path': '02_BACKEND/semantic_runtime/legal_agent/stages.py', 'function': stage},
            'files': common, 'parameters_schema': {'type': 'object', 'properties': {'term_agent': {'type': 'object'}} if stage=='retrieve' else {}, 'additionalProperties': False},
            'migration': None, 'experiment_binding': None}
        config['engines'][engine] = {'manifest': path, 'sha256': emit(path, manifest)}
        upstream = {'retrieve':'$input.request','select':'retrieve.retrieved','assemble':'select.selected','answer':'assemble.assembled'}[stage]
        nodes.append({'id':stage,'slot':slot,'engine':engine,'bindings':{inp:upstream},'parameters':{'term_agent':term} if stage=='retrieve' else {}})
    v2 = {'mode':'serving' if default else 'tool','status':'READY','inputs':{'request':'runtime.request'},'nodes':nodes,'outputs':{'result':'answer.result'}}
    config['profiles']['legal-agent-rag-v2'] = v2
    if default:
        if 'document-navigation-rag-v1' not in config['profiles']:
            config['profiles']['document-navigation-rag-v1'] = deepcopy(config['profiles']['legal-rag'])
        config['profiles']['legal-rag'] = deepcopy(v2)
    config['authorities']['tool_exploration'] = '07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V2.md'
    emit('00_SYSTEM/PIPELINE.json', config)
    from semantic_runtime.control import rehash_engines
    rehash_engines(root, apply=True, add_new=True)
    return {'profile':'legal-agent-rag-v2','default_profile_changed':default,'active_release_changed':False,'quality_certified':False}


def build_tools(root, *, version=3, default=False):
    """Package v3 working-code contracts; default selection is explicitly requested."""
    if version == 5:
        from semantic_runtime.legal_agent.obligation_protocol import SCHEMA as V3_SCHEMA
        from semantic_runtime.legal_agent.workflow_tiers_policy import DOMAIN as V3_DOMAIN, DEFAULT_PROFILE as V3_PROFILE, profile
    elif version == 3:
        from semantic_runtime.legal_agent.relations_protocol import SCHEMA as V3_SCHEMA
        from semantic_runtime.legal_agent.relations_policy import DOMAIN as V3_DOMAIN, DEFAULT_PROFILE as V3_PROFILE, profile
    else:
        raise ValueError('unsupported tools version')
    root = Path(root)
    def emit(relative, value):
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        return sha(path)
    config = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    domain_path = f'00_SYSTEM/LEGAL_AGENT/domain-v{version}.json'
    profile_path = f'00_SYSTEM/LEGAL_AGENT/profile-tools-v{version}.json'
    domain_hash = emit(domain_path, V3_DOMAIN)
    if not (root/profile_path).exists(): emit(profile_path, V3_PROFILE)
    profile(json.loads((root/profile_path).read_text()))
    profile_hash = sha(root/profile_path)
    schema_path = f'00_SYSTEM/SCHEMAS/tool-exploration-v{version}.schema.json'
    config['contracts'][f'legal.control-v{version}'] = {'schema_path': schema_path, 'schema_sha256': emit(schema_path, V3_SCHEMA), 'schema_definition': 'Control'}
    common = deepcopy(json.loads((root/config['engines']['term-retrieve@1.0.0']['manifest']).read_text())['files'])
    for p in (root/'02_BACKEND/semantic_runtime/legal_agent').iterdir():
        if p.suffix in ('.py', '.sql'): common[str(p.relative_to(root))] = sha(p)
    for p in [domain_path, profile_path, '00_SYSTEM/WORKSPACE.json', '02_BACKEND/lawrag/platform/workspace.py',
              '06_TOOLS/run_tool.py', '06_TOOLS/ACTIVE_TOOLS.json', '06_TOOLS/COMMANDS/legal_agent_trace.py',
              '06_TOOLS/COMMANDS/legal_agent_contracts.py', '02_BACKEND/PIPELINE/engine_host.py']:
        common[p] = sha(root/p)
    # platform.__init__ eagerly imports this closure; pin it for isolated releases.
    for relative in ['lawrag/__init__.py','lawrag/platform/__init__.py','lawrag/platform/release.py',
        'lawrag/platform/paths.py','lawrag/platform/active_data.py','lawrag/platform/experiment_store.py',
        'lawrag/platform/stored_paths.py','lawrag/datasets/__init__.py','lawrag/datasets/catalog.py']:
        common['02_BACKEND/'+relative] = sha(root/'02_BACKEND'/relative)
    common = {p: sha(root/p) for p in sorted(common)}
    base = config['profiles'].get('document-navigation-rag-v1', config['profiles']['legal-rag'])
    term = deepcopy(base['nodes'][0]['parameters']['term_agent'])
    term.update(implementation=f'legal-agent-tools-v{version}', legal_agent={
        'domain': {'path': domain_path, 'sha256': domain_hash}, 'profile': {'path': profile_path, 'sha256': profile_hash}})
    nodes = []
    for stage, kind, inp, out in [('retrieve','RETRIEVER','request','retrieved'), ('select','RETRIEVER','retrieved','selected'),
                                 ('assemble','ASSEMBLER','selected','assembled'), ('answer','ANSWERER','assembled','result')]:
        slot = f'legal-v{version}-'+stage; engine = slot+f'@{version}.0.0'
        inputs, outputs = {inp: 'runtime.'+inp}, {out: 'runtime.'+out}
        if stage == 'answer': outputs['control'] = f'legal.control-v{version}'
        config['slots'][slot] = {'kind': kind, 'inputs': inputs, 'outputs': outputs}
        path = f'02_BACKEND/ENGINES/legal_agent/{version}.0.0/'+stage+'.json'
        manifest = {'schema_version': 'pipeline-engine-v1', 'id': engine, 'version': f'{version}.0.0',
            'kind': kind, 'maturity': 'RELEASED' if version == 5 and default else 'TOOL', 'inputs': inputs, 'outputs': outputs,
            'entrypoint': {'path': '02_BACKEND/semantic_runtime/legal_agent/stages.py', 'function': stage},
            'files': common, 'parameters_schema': {'type': 'object', 'properties': {'term_agent': {'type': 'object'}} if stage=='retrieve' else {}, 'additionalProperties': False},
            'migration': None, 'experiment_binding': None}
        config['engines'][engine] = {'manifest': path, 'sha256': emit(path, manifest)}
        upstream = {'retrieve':'$input.request','select':'retrieve.retrieved','assemble':'select.selected','answer':'assemble.assembled'}[stage]
        nodes.append({'id':stage,'slot':slot,'engine':engine,'bindings':{inp:upstream},'parameters':{'term_agent':term} if stage=='retrieve' else {}})
    v3 = {'mode':'serving' if default else 'tool','status':'READY','inputs':{'request':'runtime.request'},'nodes':nodes,'outputs':{'result':'answer.result'}}
    config['profiles'][f'legal-agent-rag-v{version}'] = v3
    if default:
        if 'document-navigation-rag-v1' not in config['profiles']:
            config['profiles']['document-navigation-rag-v1'] = deepcopy(config['profiles']['legal-rag'])
        config['profiles']['legal-rag'] = deepcopy(v3)
        if version == 5:
            for name, candidate in config['profiles'].items():
                if name not in ('legal-rag','legal-agent-rag-v5') and candidate['mode']=='serving':
                    candidate['mode']='tool'
    config['authorities']['tool_exploration'] = ('07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_V5.md' if version == 5 else '07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V3.md')
    emit('00_SYSTEM/PIPELINE.json', config)
    from semantic_runtime.control import rehash_engines
    rehash_engines(root, apply=True, add_new=True)
    return {'profile':f'legal-agent-rag-v{version}','default_profile_changed':default,'active_release_changed':False,'quality_certified':False}


def build_v3(root, *, default=False):
    return build_tools(root, version=3, default=default)


def build_v5(root, *, default=False):
    return build_tools(root, version=5, default=default)


def build_v6(root):
    """Package the common coordinator without changing defaults or active data."""
    root=Path(root)
    pipeline=root/'00_SYSTEM/PIPELINE.json';config=json.loads(pipeline.read_text())
    candidate=deepcopy(config['profiles']['legal-agent-rag-v6'])
    candidate['mode']='tool'
    candidate['status']='READY'
    if 'orchestration' in candidate:
        candidate['nodes'][0]['parameters']['term_agent']['unified_orchestration']=candidate.pop('orchestration')
    for step in candidate['nodes']:
        old=config['engines'][config['profiles']['legal-agent-rag-v5']['nodes'][
            ['retrieve','select','assemble','answer'].index(step['id'])]['engine']]
        manifest=deepcopy(json.loads((root/old['manifest']).read_text()))
        slot='legal-v6-'+step['id'];engine=slot+'@6.0.0'
        manifest.update(id=engine,version='6.0.0',maturity='TOOL')
        for f in (root/'02_BACKEND/semantic_runtime/legal_agent').iterdir():
            if f.suffix in ('.py','.sql'):manifest['files'][f.relative_to(root).as_posix()]=sha(f)
        for f in ['00_SYSTEM/LEGAL_AGENT/domain-catalogue-v1.json','00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json',
                  '02_BACKEND/lawrag/pipeline/legal_llm_wiki.py','02_BACKEND/lawrag/core/action_memory.py',
                  '02_BACKEND/lawrag/pipeline/unified_memory.py']:
            manifest['files'][f]=sha(root/f)
        manifest['files']={name:sha(root/name) for name in sorted(manifest['files'])}
        path=f'02_BACKEND/ENGINES/legal_agent/6.0.0/{step["id"]}.json'
        (root/path).parent.mkdir(parents=True,exist_ok=True)
        (root/path).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        config['engines'][engine]={'manifest':path,'sha256':sha(root/path)}
        config['slots'][slot]=deepcopy(config['slots'][step['slot']])
        step.update(slot=slot,engine=engine)
    config['profiles']['legal-agent-rag-v6']=candidate
    config['authorities']['unified_legal_agent']='07_DOCS/REFERENCE/OPERATIONS/UNIFIED_LEGAL_AGENT_20261002.md'
    pipeline.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    from semantic_runtime.control import rehash_engines
    rehash_engines(root,apply=True,add_new=True)
    return {'profile':'legal-agent-rag-v6','default_profile_changed':False,'active_release_changed':False,
            'native_journal_version':6,'case_store_version':3,'quality_certified':False}


def bind_genos_v5(root, max_input_bytes, *, output=None):
    """Pin the configured model, or discover one model using the common GENOS path."""
    import hashlib
    from semantic_runtime.genos import advertised_model, from_env
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE, profile
    target, model = from_env('llm')
    root = Path(root).resolve()
    source = root/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json'
    path = source
    if output is not None:
        path = root/Path(output)
        relative = path.relative_to(root)
        if '..' in relative.parts or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('standalone model profile must be a non-symlink path inside the code root')
        if relative.parent != Path('00_SYSTEM/LEGAL_AGENT') or path.suffix != '.json':
            raise ValueError('standalone model profile must be a JSON file in 00_SYSTEM/LEGAL_AGENT')
        config = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
        pinned = {file for entry in config['engines'].values()
                  for file in json.loads((root/entry['manifest']).read_text())['files']}
        if relative.as_posix() in pinned or path == source:
            raise ValueError('standalone model profile must not replace an engine-pinned file')
    value = json.loads(source.read_text()) if source.exists() else dict(DEFAULT_PROFILE)
    discovered = not model
    if discovered:
        model = advertised_model(target)
    value['model_binding'] = {'provider':'genos', 'model':model, 'adapter_version':'genos-single-send-v1',
        'endpoint_identity':hashlib.sha256(target.root.encode()).hexdigest(),
        'trust_zone':'internal', 'max_input_bytes':max_input_bytes}
    profile(value, require_model=True)
    payload = json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    if output is not None:
        if path.exists():
            if path.read_text() != payload:
                raise ValueError('model profile already exists with different settings; use a new output name')
        else:
            with path.open('x') as stream: stream.write(payload)
    else:
        path.write_text(payload)
    return {'model':model, 'profile':str(path), 'profile_sha256':sha(path),
            'network_contacted':discovered, 'quality_certified':False,
            'standalone':output is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--version', choices=['v1', 'v2', 'v3', 'v5','v6'], default='v1')
    parser.add_argument('--default', action='store_true', help='Explicitly select v2 or v5 in the working MAIN configuration')
    parser.add_argument('--bind-genos-from-env', action='store_true', help='Bind the internal endpoint/model; discover via /models when MODEL is omitted')
    parser.add_argument('--max-input-bytes', type=int, help='Deployment-validated conservative model input limit')
    parser.add_argument('--profile-output', type=Path,
                        help='Create a standalone GENOS v5 profile without rewriting engine/data bindings')
    args = parser.parse_args()
    if args.profile_output is not None and (not args.bind_genos_from_env or args.default):
        parser.error('--profile-output requires --bind-genos-from-env and cannot be combined with --default')
    if args.bind_genos_from_env:
        if args.version != 'v5' or args.max_input_bytes is None: parser.error('model binding requires --version v5 and --max-input-bytes')
        binding = bind_genos_v5(args.root,args.max_input_bytes,output=args.profile_output)
        if args.profile_output is not None:
            print(json.dumps(binding,ensure_ascii=False,indent=2))
            raise SystemExit(0)
    if args.default and args.version not in ('v2', 'v5'): parser.error('--default requires --version v2 or v5; v3 is explicit opt-in')
    print(json.dumps(build_v6(args.root) if args.version=='v6' else build_v5(args.root, default=args.default) if args.version=='v5' else build_v3(args.root) if args.version=='v3' else build_v2(args.root, default=args.default) if args.version=='v2' else build(args.root), ensure_ascii=False, indent=2))
