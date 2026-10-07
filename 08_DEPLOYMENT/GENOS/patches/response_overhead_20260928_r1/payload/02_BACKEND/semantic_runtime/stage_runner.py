"""Shared manifest/port checked stage execution for linear and re-entrant profiles."""
import importlib.util
import json
from .contracts import cached_code_sha as sha
from . import observability as obs


class StageRunner:
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def execute(self, step, values, *, legal_session=None):
        p = self.pipeline
        config = p.contracts.pipeline
        with obs.step(obs.get_logger('rag'), step['id'], engine=step['engine']):
            entry = config['engines'][step['engine']]
            path = (p.contracts.root/entry['manifest']).resolve()
            path.relative_to(p.contracts.root)
            if sha(path) != entry['sha256']:
                raise ValueError('engine manifest hash mismatch')
            key = (str(path), entry['sha256'])
            manifest = p.contracts._engine_manifests.get(key)
            if manifest is None:
                raw = path.read_bytes()
                import hashlib
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('engine manifest hash mismatch')
                manifest = json.loads(raw)
                p.contracts._engine_manifests[key] = manifest
            slot = config['slots'][step['slot']]
            if any(slot[k] != manifest[k] for k in ('kind', 'inputs', 'outputs')):
                raise ValueError('engine slot/port mismatch')
            for file, expected in manifest['files'].items():
                bound = (p.contracts.root/file).resolve()
                bound.relative_to(p.contracts.root)
                if sha(bound) != expected:
                    raise ValueError('engine code hash mismatch: '+file)
            module_path = (p.contracts.root/manifest['entrypoint']['path']).resolve()
            module_path.relative_to(p.contracts.root)
            if manifest['entrypoint']['path'] not in manifest['files']:
                raise ValueError('engine entrypoint is not hash-bound')
            suffix = '.legal_agent' if legal_session is not None else ''
            spec = importlib.util.spec_from_file_location(__package__+suffix+'._stage_'+step['id'], module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if set(step['bindings']) != set(manifest['inputs']):
                raise ValueError('engine input ports mismatch')
            inputs = {k: values[v] for k, v in step['bindings'].items()}
            for key, value in inputs.items():
                p.contracts.validate_port(manifest['inputs'][key], value)
            from jsonschema import Draft202012Validator
            Draft202012Validator(manifest['parameters_schema']).validate(step['parameters'])
            context = {'runtime': p, **({'legal_session': legal_session} if legal_session is not None else {})}
            result = getattr(module, manifest['entrypoint']['function'])(inputs, step['parameters'], context)
            if set(result) != set(manifest['outputs']):
                raise ValueError('engine output ports mismatch')
            for key, value in result.items():
                p.contracts.validate_port(manifest['outputs'][key], value)
                values[step['id']+'.'+key] = value
            primary = {'retrieve': 'retrieved', 'select': 'selected', 'assemble': 'assembled', 'answer': 'result'}.get(step['id'])
            current = result.get(primary, {})
            log = obs.get_logger('rag')
            if step['id'] == 'retrieve':
                data = current.get('retrieval', {})
                obs.event(log, 'rag.retrieved', candidate_count=len(data.get('candidates', [])), routes=data.get('routes', {}), vector_status=data.get('vector_status'))
            elif step['id'] == 'select':
                data = current.get('selection', {})
                obs.event(log, 'rag.selected', selected_count=len(data.get('selected', [])), method=data.get('method'))
            elif step['id'] == 'assemble':
                data = current.get('assembly', {})
                obs.event(log, 'rag.assembled', context_count=len(data.get('context', [])), unresolved_count=len(data.get('unresolved', [])))
            elif step['id'] == 'answer':
                data = current.get('answer', {})
                obs.event(log, 'rag.answered', answer_chars=len(data.get('text', '')), claim_count=len(data.get('claims', [])), unresolved_count=len(data.get('unresolved', [])))
            if legal_session is not None:
                legal_session.work.save_artifact(step['id'], current)
            obs.event(obs.get_logger('rag'), 'rag.stage_completed', stage=step['id'], ports=list(result))
            return result
