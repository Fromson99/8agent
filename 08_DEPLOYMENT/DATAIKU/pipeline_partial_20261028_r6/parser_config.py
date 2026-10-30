"""Full Flow keeps its original HTTP parser; same-Pod remains explicitly selectable."""
import hashlib,json,os,subprocess,sys
from pathlib import Path


def environment():
    mode=os.environ.get('LEGAL_PIPELINE_PARSER_MODE','existing-http').strip()
    if mode=='existing-http':
        return mode,{'GENOS_PREPROCESSOR_TRANSPORT':'http','GENOS_PDF_PARSER':'preprocessor',
                     'GENOS_PREPROCESSOR_RESPONSE_MODE':'auto'}
    if mode=='same-pod':
        return mode,{'GENOS_PREPROCESSOR_TRANSPORT':'pod','GENOS_PDF_PARSER':'preprocessor',
                     'GENOS_PREPROCESSOR_RESPONSE_MODE':'docling'}
    raise ValueError('PIPELINE_PARSER_MODE_INVALID')


def inspect(root):
    try:
        mode,overrides=environment()
        module='http_parser_config' if mode=='existing-http' else 'pod_parser_config'
        env={**os.environ,**overrides,'PYTHONPATH':str(root)+os.pathsep+str(Path(root)/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1'}
        code="import json;from pathlib import Path;import "+module+" as p;print('CONFIG_JSON='+json.dumps(p.inspect(Path.cwd()),sort_keys=True))"
        r=subprocess.run([sys.executable,'-B','-c',code],cwd=root,env=env,text=True,capture_output=True,timeout=55)
        lines=[x for x in r.stdout.splitlines() if x.startswith('CONFIG_JSON=')]
        if r.returncode or len(lines)!=1:raise ValueError('PIPELINE_PARSER_PREFLIGHT_FAILED')
        value=json.loads(lines[0].split('=',1)[1]);value['pipeline_parser_mode']=mode
        value['document_failure_policy']='verified-successes-only'
        if value.get('ready'):
            value['config_sha256']=hashlib.sha256(json.dumps({'mode':mode,'configuration':value['config_sha256']},sort_keys=True).encode()).hexdigest()
        return value
    except Exception as exc:
        error=str(exc)
        if not error.startswith('PIPELINE_') or not error.replace('_','').isalnum():error='PIPELINE_PARSER_PREFLIGHT_FAILED'
        return {'ready':False,'errors':[error],'document_failure_policy':'verified-successes-only'}


def require(root,expected=None):
    value=inspect(root)
    if not value['ready']:raise ValueError(value['errors'][0])
    if expected is not None and value['config_sha256']!=expected:raise ValueError('PREPROCESSOR_CONFIG_CHANGED')
    return value
