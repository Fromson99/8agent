"""Contract-first local pipeline host. No engine discovery or implicit migrations.

Engine code is trusted executable Python, not sandboxed by this host. Registry
membership/hash authorizes identity, not legal approval or release promotion.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
class ContractError(ValueError): pass

def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
def contained(root, relative):
    path = (root / relative).resolve()
    try: path.relative_to(root.resolve())
    except ValueError: raise ContractError('path escapes repository: ' + str(relative))
    return path

def load(root=ROOT):
    config = read(root / '00_SYSTEM/PIPELINE.json')
    schema = read(root / '00_SYSTEM/SCHEMAS/pipeline-v1.schema.json')
    Draft202012Validator(schema).validate(config)
    return config

def contract_schema(config, name, root=ROOT):
    if name not in config['contracts']: raise ContractError('unknown contract: ' + name)
    contract = config['contracts'][name]
    path = contained(root, contract['schema_path'])
    if sha(path) != contract['schema_sha256']: raise ContractError('contract schema hash drift: ' + name)
    schema = read(path)
    definition = contract.get('schema_definition')
    if definition is not None:
        if definition not in schema.get('$defs', {}):
            raise ContractError('unknown schema definition: ' + name + '/' + definition)
        return {key: value for key, value in schema.items() if key in ('$schema', '$id', '$defs')} | {'$ref': '#/$defs/' + definition}
    return schema

def schema_registry(config, root=ROOT):
    """Resolve only explicitly hash-bound local schemas; never fetch a URL.

    Stage schemas share the legal definitions by reference. Their source files
    remain the authorities; this registry is an in-memory resolver only.
    """
    resources = {}
    def add(schema):
        identifier = schema.get('$id')
        if identifier:
            if identifier in resources and resources[identifier] != schema:
                raise ContractError('conflicting schema identity: ' + identifier)
            resources[identifier] = schema
    for name, item in config['contracts'].items():
        if 'schema_path' in item:
            path = contained(root, item['schema_path'])
            if sha(path) != item['schema_sha256']:
                raise ContractError('contract schema hash drift: ' + name)
            add(read(path))
    return Registry().with_resources((key, Resource.from_contents(value)) for key, value in resources.items())

def validate_value(config, contract, value, root=ROOT):
    schema = contract_schema(config, contract, root)
    Draft202012Validator(schema, registry=schema_registry(config, root), format_checker=FormatChecker()).validate(value)

def engine(config, engine_id, mode, root=ROOT):
    spec = config['engines'].get(engine_id)
    if spec is None: raise ContractError('unregistered engine: ' + engine_id)
    path = contained(root, spec['manifest'])
    if sha(path) != spec['sha256']: raise ContractError('engine manifest hash drift: ' + engine_id)
    manifest = read(path)
    Draft202012Validator(read(root / '00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json')).validate(manifest)
    if manifest['id'] != engine_id: raise ContractError('engine identity mismatch')
    maturity = manifest['maturity']
    relative = path.relative_to(root.resolve()).as_posix()
    research = relative.startswith('02_BACKEND/lawrag/research/candidates/')
    if research != (maturity == 'RESEARCH'): raise ContractError('engine namespace/maturity mismatch')
    if mode != 'research' and maturity == 'RESEARCH': raise ContractError('research engine cannot run in ' + mode)
    if maturity == 'RESEARCH':
        binding = manifest['experiment_binding']
        if binding is None: raise ContractError('research engine needs exact experiment binding')
        for key in ('candidate', 'revision', 'experiment'):
            item = binding[key]; target = contained(root, item['path'])
            if sha(target) != item['sha256']: raise ContractError('experiment binding drift: ' + key)
        if not binding['arm_id'] or not binding['run_id']: raise ContractError('missing experiment arm/run')
    elif not relative.startswith('02_BACKEND/ENGINES/'):
        raise ContractError('released/tool engine outside engine namespace')
    if mode == 'serving' and maturity != 'RELEASED': raise ContractError('serving requires released engine')
    if mode == 'serving':
        pointer=read(root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
        if pointer.get('schema_version')!='semantic-runtime-active-v2':
            raise ContractError('latest semantic runtime is not activated')
        release_path=contained(root,pointer['manifest_path'])
        if sha(release_path)!=pointer['release_manifest_sha256']:raise ContractError('active release hash drift')
        release=read(release_path)
        for file,expected in manifest['files'].items():
            if release['files'].get(file)!=expected:raise ContractError('engine differs from active release')
    for port in list(manifest['inputs'].values()) + list(manifest['outputs'].values()):
        contract_schema(config, port, root)
    for relative_file, expected in manifest['files'].items():
        file = contained(root, relative_file)
        if sha(file) != expected: raise ContractError('engine code hash drift: ' + relative_file)
        if maturity != 'RESEARCH' and '/research/' in file.as_posix():
            raise ContractError('released/tool engine depends on research code')
    entry = manifest['entrypoint']['path']
    if entry not in manifest['files']: raise ContractError('entrypoint not hash-bound')
    if manifest['kind'] == 'MIGRATOR':
        migration = manifest['migration']
        if migration is None or len(manifest['inputs']) != 1 or len(manifest['outputs']) != 1:
            raise ContractError('migrator needs one explicit input/output contract')
        if list(manifest['inputs'].values()) != [migration['from_contract']] or list(manifest['outputs'].values()) != [migration['to_contract']]:
            raise ContractError('migrator declaration does not match ports')
    elif manifest['migration'] is not None: raise ContractError('only MIGRATOR may declare schema migration')
    return manifest

def plan(config, profile_name, overrides=None, root=ROOT):
    if profile_name not in config['profiles']: raise ContractError('unknown profile: ' + profile_name)
    profile = config['profiles'][profile_name]; overrides = overrides or {}
    ids = [n['id'] for n in profile['nodes']]
    if len(ids) != len(set(ids)): raise ContractError('duplicate pipeline node')
    if set(overrides) - set(ids): raise ContractError('override names an unknown node')
    outputs = {'$input': profile['inputs']}; available = set(); pending = list(profile['nodes']); steps = []; missing = []
    for name in profile['inputs'].values(): contract_schema(config, name, root)
    while pending:
        ready = [n for n in pending if all(source.split('.', 1)[0] == '$input' or source.split('.', 1)[0] in available for source in n['bindings'].values())]
        if not ready: raise ContractError('cycle or unknown dependency in pipeline')
        for node in ready:
            selected = overrides.get(node['id'], node['engine'])
            slot = config['slots'].get(node['slot'])
            if slot is None: raise ContractError('unknown pipeline slot: ' + node['slot'])
            if selected is None:
                missing.append(node['id'])
                manifest = {**slot, 'parameters_schema': {'type': 'object'}}
            else:
                manifest = engine(config, selected, profile['mode'], root)
            if manifest['kind'] != slot['kind']: raise ContractError('engine kind does not fit slot: ' + node['id'])
            if manifest['inputs'] != slot['inputs'] or manifest['outputs'] != slot['outputs']:
                raise ContractError('engine does not satisfy slot contract: ' + node['id'])
            if set(node['bindings']) != set(manifest['inputs']): raise ContractError('missing/extra input ports: ' + node['id'])
            for port, source in node['bindings'].items():
                producer, name = source.split('.', 1)
                incoming = outputs.get(producer, {}).get(name)
                if incoming != manifest['inputs'][port]:
                    raise ContractError(f'{node["id"]}.{port}: {incoming} != {manifest["inputs"][port]}; insert an explicit MIGRATOR stage')
            Draft202012Validator(manifest['parameters_schema']).validate(node['parameters'])
            steps.append({'node': node['id'], 'engine': selected, 'manifest_sha256': config['engines'][selected]['sha256'] if selected else None, 'bindings': node['bindings'], 'parameters': node['parameters'], 'outputs': manifest['outputs']})
            outputs[node['id']] = manifest['outputs']; available.add(node['id']); pending.remove(node)
    for port, source in profile['outputs'].items():
        producer, name = source.split('.', 1)
        if name not in outputs.get(producer, {}): raise ContractError('unknown pipeline output: ' + port)
    if missing: raise ContractError('engines not migrated/selected: ' + ', '.join(missing))
    return {'schema_version': 'pipeline-plan-v1', 'profile': profile_name, 'mode': profile['mode'], 'steps': steps, 'inputs': profile['inputs'], 'outputs': profile['outputs']}

def execute(config, profile_name, input_artifacts, output_dir, overrides=None, root=ROOT):
    frozen_plan = plan(config, profile_name, overrides, root)
    if set(input_artifacts) != set(frozen_plan['inputs']): raise ContractError('input artifact ports differ from profile')
    values = {}; input_receipts = {}
    for name, contract in frozen_plan['inputs'].items():
        artifact = input_artifacts[name]; path = Path(artifact['path']).resolve()
        raw = path.read_bytes(); actual = hashlib.sha256(raw).hexdigest()
        if actual != artifact['sha256']: raise ContractError('input artifact hash drift: ' + name)
        value = json.loads(raw); validate_value(config, contract, value, root)
        values['$input.' + name] = value
        input_receipts[name] = {'path': str(path), 'sha256': actual, 'contract': contract}
    output_dir = Path(output_dir).resolve()
    if output_dir.exists(): raise ContractError('output run already exists; never overwrite a run')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Atomic mkdir reserves this run even when multiple runners start together.
    output_dir.mkdir()
    receipt = {'schema_version': 'pipeline-run-v1', 'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat(), 'plan': frozen_plan, 'inputs': input_receipts, 'steps': [], 'outputs': {}, 'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), 'approval_verified': False, 'main_changed': False}
    runtime=None
    try:
        import sys
        sys.path.insert(0,str(root/'02_BACKEND'))
        if frozen_plan['mode']=='serving':
            from semantic_runtime.storage import Store
            from semantic_runtime.pipeline import Pipeline
            from semantic_runtime.provider import Haiku
            pointer=read(root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
            release=read(contained(root,pointer['manifest_path']))
            store=Store(contained(root,release['data_path']))
            runtime=Pipeline(root,store,Haiku(root,root/'90_RUNTIME/semantic/provider',store.manifest['export_allowed']))
        # Legal-agent stages require one request-local session and may re-enter.
        # Use the same coordinator/outbox as the HTTP API, not four linear calls.
        if runtime is not None and runtime.profile_id.startswith('legal-agent-rag-'):
            requested = config['profiles'][profile_name]
            selected = config['profiles'][runtime.profile_id]
            if requested['nodes'] != selected['nodes'] or overrides:
                raise ContractError('legal-agent execution requires its complete bound profile; stage overrides are not a coherent session')
            request = values['$input.request']
            result = runtime.run(request['question'], request.get('document_ids'), request['use_llm'], request.get('scope'),
                execution_context={'runtime':root/'90_RUNTIME/semantic','release':pointer,'publish':True})
            value = {k:v for k,v in result.items() if k not in ('run_id','release')}
            validate_value(config, 'runtime.result', value, root)
            target = output_dir/'answer--result.json'; dump(target,value)
            receipt['execution'] = {'kind':'REQUEST_LOCAL_LEGAL_COORDINATOR','run_id':result['run_id'],
                                    'journal':result.get('journal'), 'profile':runtime.profile_id}
            receipt['outputs']['result'] = {'path':target.name,'sha256':sha(target),'contract':'runtime.result'}
            receipt['status'] = 'COMPLETE'
            return receipt
        for step in frozen_plan['steps']:
            manifest = engine(config, step['engine'], frozen_plan['mode'], root)
            module_path = contained(root, manifest['entrypoint']['path'])
            spec = importlib.util.spec_from_file_location('pipeline_engine_' + step['node'], module_path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            kwargs = {port: values[source] for port, source in step['bindings'].items()}
            result = getattr(module, manifest['entrypoint']['function'])(kwargs, step['parameters'], {'repository_root': str(root), 'mode': frozen_plan['mode'], 'runtime':runtime})
            if not isinstance(result, dict) or set(result) != set(manifest['outputs']): raise ContractError('engine output ports differ: ' + step['node'])
            artifacts = {}
            for port, contract in manifest['outputs'].items():
                validate_value(config, contract, result[port], root)
                path = output_dir / (step['node'] + '--' + port + '.json')
                dump(path, result[port]); values[step['node'] + '.' + port] = result[port]
                artifacts[port] = {'path': path.name, 'sha256': sha(path), 'contract': contract}
            receipt['steps'].append({'node': step['node'], 'engine': step['engine'], 'manifest_sha256': step['manifest_sha256'], 'artifacts': artifacts})
        for name, source in frozen_plan['outputs'].items():
            producer, port = source.split('.', 1)
            if producer == '$input': receipt['outputs'][name] = input_receipts[port]
            else: receipt['outputs'][name] = next(s for s in receipt['steps'] if s['node'] == producer)['artifacts'][port]
        receipt['status'] = 'COMPLETE'
    except Exception as exc:
        receipt['status'] = 'FAILED'; receipt['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if runtime is not None:runtime.store.close()
        receipt['completed_at'] = datetime.now(timezone.utc).isoformat(); dump(output_dir / 'receipt.json', receipt)
    return receipt

def inventory(config, root=ROOT):
    for name in config['contracts']: contract_schema(config, name, root)
    schema_registry(config, root)
    if 'stage_schemas' in config:
        ids=[stage['id'] for stage in config['stage_schemas']]
        if len(ids)!=len(set(ids)):raise ContractError('duplicate stage schema catalog ID')
        for stage in config['stage_schemas']:
            if set(stage['contracts']) - set(config['contracts']):
                raise ContractError('unknown contract in stage schema catalog')
            if set(stage['profiles']) - set(config['profiles']):
                raise ContractError('unknown profile in stage schema catalog')
    for name in config['engines']: engine(config, name, 'research', root)
    profiles = {}
    for name, spec in config['profiles'].items():
        try: profiles[name] = {'ready': True, 'steps': len(plan(config, name, root=root)['steps'])}
        except ContractError as exc:
            if spec['status'] != 'MIGRATION_REQUIRED' or not str(exc).startswith('engines not migrated/selected:'): raise
            profiles[name] = {'ready': False, 'reason': str(exc)}
    return {'ok': True, 'profiles': profiles, 'runtime': 'term-runtime-v1'}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'plan', 'run'])
    parser.add_argument('--profile', default='legal-rag')
    parser.add_argument('--engine', action='append', default=[], help='explicit NODE=ENGINE override')
    parser.add_argument('--inputs', type=Path, help='JSON mapping port to path and sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv); config = load(); overrides = dict(x.split('=', 1) for x in args.engine)
    if args.action == 'check': result = inventory(config)
    elif args.action == 'plan': result = plan(config, args.profile, overrides)
    else:
        if args.inputs is None or args.output is None: parser.error('run requires --inputs and --output')
        result = execute(config, args.profile, read(args.inputs), args.output, overrides)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
