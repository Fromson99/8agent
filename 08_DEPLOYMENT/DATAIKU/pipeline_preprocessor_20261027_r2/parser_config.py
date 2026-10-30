"""Local preflight for the existing GENOS parser; never load local PDF models."""
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ERRORS = {
    'PREPROCESSOR_MODE_REQUIRED', 'PREPROCESSOR_ENDPOINT_REQUIRED',
    'PREPROCESSOR_SHARED_ROOT_REQUIRED', 'PREPROCESSOR_CONFIG_INVALID',
    'PREPROCESSOR_SHARED_ROOT_UNAVAILABLE', 'PREPROCESSOR_DOCLING_RESPONSE_REQUIRED',
    'PREPROCESSOR_CONFIG_CHANGED',
}


@lru_cache(maxsize=4)
def settings_module(root):
    # Load the exact pinned Settings implementation, not an ambient lawrag install.
    path = Path(root) / '02_BACKEND/lawrag/core/genos_preprocessor.py'
    name = '_pipeline_parser_settings_' + hashlib.sha256(str(path).encode()).hexdigest()
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inspect(root):
    errors = []
    if os.environ.get('GENOS_PDF_PARSER', 'preprocessor').strip() != 'preprocessor':
        errors.append('PREPROCESSOR_MODE_REQUIRED')
    if not (os.environ.get('GENOS_PREPROCESSOR_ID', '').strip()
            or os.environ.get('GENOS_PREPROCESSOR_URL', '').strip()):
        errors.append('PREPROCESSOR_ENDPOINT_REQUIRED')
    if not os.environ.get('GENOS_PREPROCESSOR_SHARED_ROOT', '').strip():
        errors.append('PREPROCESSOR_SHARED_ROOT_REQUIRED')
    mode = os.environ.get('GENOS_PREPROCESSOR_RESPONSE_MODE', 'docling').strip()
    # This delivery keeps structural VLM off. Chunk-only responses need that
    # separate review path and cannot be promoted to equivalent source structure.
    if mode != 'docling':
        errors.append('PREPROCESSOR_DOCLING_RESPONSE_REQUIRED')
    result = {'ready': False, 'mode': 'preprocessor', 'response_mode': 'docling',
              'errors': errors, 'remote_connectivity': 'NOT_CHECKED',
              'remote_shared_mount': 'NOT_CHECKED'}
    if errors:
        return result
    try:
        settings = replace(settings_module(str(Path(root).resolve())).Settings.from_env(),
                           response_mode=mode)
    except (ValueError, OSError):
        errors.append('PREPROCESSOR_CONFIG_INVALID')
        return result
    if (not settings.shared_root.is_dir()
            or not os.access(settings.shared_root, os.R_OK | os.W_OK | os.X_OK)):
        errors.append('PREPROCESSOR_SHARED_ROOT_UNAVAILABLE')
        return result
    identity = asdict(settings)
    identity['shared_root'] = str(settings.shared_root)
    result.update(ready=True, config_sha256=hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    # No URL, filesystem values, API key or authorization header is published.
    return result


def require(root, expected=None):
    result = inspect(root)
    if not result['ready']:
        raise ValueError(result['errors'][0])
    if expected is not None and result['config_sha256'] != expected:
        raise ValueError('PREPROCESSOR_CONFIG_CHANGED')
    return result
