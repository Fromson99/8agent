"""Pod-local dependency/configuration preflight, no document/model calls."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ERRORS = {'PREPROCESSOR_CONFIG_CHANGED','PREPROCESSOR_REVIEW_CONFIG_REQUIRED','POD_RUNTIME_NOT_READY'}


@lru_cache(maxsize=8)
def probe(root, identity):
    env = {**os.environ,'PYTHONPATH':str(Path(root)/'02_BACKEND'),
           'PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
           'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    code = "from lawrag.core.genos_pod import Settings,preflight; preflight(Settings.from_env()); print('POD_RUNTIME_OK')"
    result = subprocess.run([sys.executable,'-B','-c',code],cwd=root,env=env,
                            text=True,capture_output=True,timeout=45)
    if result.returncode or not result.stdout.rstrip().endswith('POD_RUNTIME_OK'):
        # Private stderr is not returned by HEALTH (may contain config credentials).
        raise ValueError('POD_RUNTIME_NOT_READY')


def inspect(root):
    root=Path(root).resolve()
    result={'ready':False,'mode':'preprocessor','transport':'same-pod','response_mode':'docling',
            'review_backend':'genos','review_enabled':True,'errors':[],
            'model_connectivity':'NOT_CHECKED','conversion_execution':'NOT_CHECKED'}
    review={k:v for k,v in os.environ.items() if k.startswith('STRUCTURE_RECIPE_')}
    for key in ('GENOS_BASE_URL','GENOS_LLM_URL','GENOS_LLM_SERVING_ID','GENOS_LLM_MODEL',
                'GENOS_LLM_JSON_MODE','GENOS_LLM_TEMPERATURE','GENOS_GATEWAY_API_PREFIX','GENOS_LLM_API_PREFIX'):
        review[key]=os.environ.get(key,'').strip()
    endpoint=review['GENOS_LLM_URL']
    if not endpoint and review['GENOS_BASE_URL'] and review['GENOS_LLM_SERVING_ID'].isdigit():
        endpoint=review['GENOS_BASE_URL'].rstrip('/')+'/api/gateway/rep/serving/'+review['GENOS_LLM_SERVING_ID']
    try:
        url=urlsplit(endpoint)
        valid=url.scheme in {'http','https'} and url.hostname and not(url.username or url.password or url.query or url.fragment)
    except ValueError:valid=False
    if not valid or os.environ.get('LLM_BACKEND','genos').lower()!='genos' or os.environ.get('STRUCTURE_RECIPE_VLM','on').lower() not in {'on','auto'}:
        result['errors'].append('PREPROCESSOR_REVIEW_CONFIG_REQUIRED');return result
    if os.environ.get('GENOS_PREPROCESSOR_TRANSPORT','pod')!='pod' or os.environ.get('GENOS_PDF_PARSER','preprocessor')!='preprocessor':
        result['errors'].append('POD_TRANSPORT_REQUIRED');return result
    backend=str(root/'02_BACKEND')
    if backend not in sys.path:sys.path.insert(0,backend)
    try:
        from lawrag.core.genos_pod import Settings
        settings=Settings.from_env()
        identity={**settings.identity(),'review':review}
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        probe(str(root),digest)
    except (Exception,) as exc:
        safe=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('POD_') else 'POD_RUNTIME_NOT_READY'
        result['errors'].append(safe);return result
    result.update(ready=True,config_sha256=digest)
    return result


def require(root,expected=None):
    result=inspect(root)
    if not result['ready']:raise ValueError(result['errors'][0])
    if expected is not None and result['config_sha256']!=expected:raise ValueError('PREPROCESSOR_CONFIG_CHANGED')
    return result
