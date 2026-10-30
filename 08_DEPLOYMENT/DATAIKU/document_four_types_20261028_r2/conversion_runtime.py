"""PDF conversion prerequisites only. Never construct a parser or load YAML."""
import hashlib,json,os,subprocess,sys
from pathlib import Path

CODE = r'''
import importlib.metadata as md,json,os,sys
from pathlib import Path
from lawrag.core.genos_pod import activate
activate()
from genon.preprocessor.converters.hwp_to_pdf import availability as a
import shutil
paths={'libreoffice':shutil.which('soffice'),'rhwp':str(a.rhwp_binary()),'pdf_sdk':str(a.pdf_sdk_binary())}
backends={}
for name,value in paths.items():
    p=Path(value) if value else None
    present=bool(p and p.is_file() and os.access(p,os.X_OK))
    backends[name]={'available':present}
    if present:
        s=p.stat();backends[name].update(path=str(p.resolve()),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
errors=[]
if not any(x['available'] for x in backends.values()):errors.append('POD_PDF_CONVERTER_MISSING')
try:
    import fitz
    version=md.version('PyMuPDF')
except (ImportError,md.PackageNotFoundError):
    version='MISSING';errors.append('POD_PDF_VALIDATOR_MISSING')
print('CONVERSION_JSON='+json.dumps({'backends':backends,'pdf_validator':version,'python':sys.version,'errors':errors},sort_keys=True))
'''


def inspect(root):
    result={'ready':False,'transport':'same-pod','configuration':'NOT_REQUIRED','parser_enabled':False,
            'mode':'convert_only','errors':[],'application_review':False,'parser_model_calls':0}
    env={**os.environ,'PYTHONPATH':str(Path(root)/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1'}
    try:
        r=subprocess.run([sys.executable,'-B','-c',CODE],cwd=root,env=env,text=True,capture_output=True,timeout=15)
        lines=[x for x in r.stdout.splitlines() if x.startswith('CONVERSION_JSON=')]
        if r.returncode or len(lines)!=1:raise ValueError('POD_CONVERTER_IMPORT_FAILED')
        runtime=json.loads(lines[0].split('=',1)[1]);result['errors']=runtime['errors']
        identity={'mode':'convert_only','runtime':runtime}
        result.update(runtime=runtime,ready=not runtime['errors'],config_sha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest())
    except subprocess.TimeoutExpired:result['errors'].append('POD_CONVERTER_CHECK_TIMEOUT')
    except Exception:result['errors'].append('POD_CONVERTER_IMPORT_FAILED')
    return result


def require(root,expected=None):
    value=inspect(root)
    if not value['ready']:raise ValueError(value['errors'][0])
    if expected is not None and value['config_sha256']!=expected:raise ValueError('POD_CONVERTER_RUNTIME_CHANGED')
    return value
