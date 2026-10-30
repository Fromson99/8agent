"""Use configuration already present in this Pod; no Dataiku YAML parameter."""
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def existing_config(root):
    explicit=os.environ.get('GENOS_STRUCTURE_CONFIG','').strip()
    if explicit:
        p=Path(explicit)
        if not p.is_absolute() or not p.is_file():raise ValueError('POD_CONFIG_ENV_PATH_INVALID')
        return p,'ENV'
    candidates=[]
    bases=[Path('/app'),Path('/app/src'),Path('/opt/app'),*[Path(p) for p in sys.path if p]]
    seen=set()
    for base in bases:
        for component in (base,base/'genon/preprocessor'):
            for directory in ('resource_dev','resource'):
                p=component/directory/'parser_processor_config.yaml'
                if not p.is_file():continue
                p=p.resolve()
                if 'pod_vendor' not in p.parts and p not in seen:
                    seen.add(p);candidates.append(p)
                break  # resource_dev takes precedence only in this component.
    unique={sha(p):p for p in candidates}
    if not unique:raise ValueError('POD_EXISTING_PARSER_CONFIG_NOT_FOUND')
    if len(unique)>1:raise ValueError('POD_EXISTING_PARSER_CONFIG_AMBIGUOUS')
    return next(iter(unique.values())),'IMAGE'


def normalized(root):
    import yaml
    source,kind=existing_config(root)
    cfg=yaml.safe_load(source.read_text(encoding='utf-8'))
    if not isinstance(cfg,dict) or not isinstance(cfg.get('layout'),dict) or not isinstance(cfg.get('ocr'),dict):
        raise ValueError('POD_EXISTING_CONFIG_NOT_PARSER_CONFIG')
    def resolve(value,key=''):
        if isinstance(value,dict):return {k:resolve(v,str(k)) for k,v in value.items()}
        if isinstance(value,list):return [resolve(x,key) for x in value]
        if isinstance(value,str) and (key.endswith(('_file','_path','_dir')) or key in {'path','file'}):
            p=Path(value)
            if value and not p.is_absolute() and '://' not in value:
                value=str((source.parent/p).resolve())
        return value
    cfg=resolve(cfg);cfg['enrichment']=[];cfg['output']={**(cfg.get('output') or {}),'format':'docling'}
    return yaml.safe_dump(cfg,allow_unicode=True,sort_keys=True),{'source_kind':kind,'source_config_sha256':sha(source)}


@lru_cache(maxsize=8)
def checked_runtime(root,config_text):
    with tempfile.TemporaryDirectory(prefix='pod-probe-config-check-') as tmp:
        path=Path(tmp)/'parser.yaml';path.write_text(config_text);path.chmod(0o600)
        env={**os.environ,'PYTHONPATH':str(Path(root)/'02_BACKEND'),'GENOS_STRUCTURE_CONFIG':str(path),
             'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        code="from lawrag.core.genos_pod import Settings,preflight;import json;s=Settings.from_env();preflight(s);print('PROBE_JSON='+json.dumps(s.identity(),sort_keys=True))"
        try:r=subprocess.run([sys.executable,'-B','-c',code],cwd=root,env=env,text=True,capture_output=True,timeout=45)
        except subprocess.TimeoutExpired:raise ValueError('POD_RUNTIME_PREFLIGHT_TIMEOUT') from None
        lines=[s for s in r.stdout.splitlines() if s.startswith('PROBE_JSON=')]
        if r.returncode or len(lines)!=1:raise ValueError('POD_PARSER_OR_CONVERTER_NOT_READY')
        return json.loads(lines[0].split('=',1)[1])


def inspect(root):
    result={'ready':False,'transport':'same-pod','configuration':'existing-pod-config','errors':[],
            'model_connectivity':'NOT_CHECKED','application_review':False}
    try:
        text,origin=normalized(root);identity=checked_runtime(str(root),text)
        result.update(ready=True,**origin,config_sha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest())
    except Exception as exc:
        code=str(exc)
        if not code.startswith('POD_') or not code.replace('_','').isalnum():code='POD_RUNTIME_CONFIG_ERROR'
        result['errors'].append(code)
    return result


def require(root,expected=None):
    value=inspect(root)
    if not value['ready']:raise ValueError(value['errors'][0])
    if expected is not None and value['config_sha256']!=expected:raise ValueError('POD_PROBE_CONFIG_CHANGED')
    return value


@contextmanager
def use(root,folder,expected):
    text,origin=normalized(root)
    identity=checked_runtime(str(root),text)
    if hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()!=expected:
        raise ValueError('POD_PROBE_CONFIG_CHANGED')
    path=Path(folder)/'effective-parser.yaml'
    path.write_text(text);path.chmod(0o600)
    before=os.environ.get('GENOS_STRUCTURE_CONFIG')
    os.environ['GENOS_STRUCTURE_CONFIG']=str(path)
    try:yield origin
    finally:
        if before is None:os.environ.pop('GENOS_STRUCTURE_CONFIG',None)
        else:os.environ['GENOS_STRUCTURE_CONFIG']=before
        path.unlink(missing_ok=True)  # Config can contain credentials; never export it.
