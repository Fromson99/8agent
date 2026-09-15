"""Read-only graph contract audit; it does not produce or approve legal claims."""
import importlib.util
from pathlib import Path

def run(inputs, parameters, context):
    root = Path(context['repository_root'])
    path = root / '06_TOOLS/AUDIT/legal_semantic_contract.py'
    spec = importlib.util.spec_from_file_location('legal_semantic_contract', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    errors = module.validate(inputs['observation'], root=root)
    if errors: raise ValueError('; '.join(errors))
    return {'report': {'valid': True, 'record_id': inputs['observation']['id'], 'approval_verified': False, 'source_verified': False}}
