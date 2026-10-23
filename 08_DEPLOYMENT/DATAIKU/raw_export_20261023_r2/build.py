"""Seal the exporter fix; previous ZIPs and deployed service/client stay unchanged."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
NAME = 'GENOS_RAW_EXPORT_20261023_R2'
FILES = ('export_inputs.py', 'transport.py', 'filename_versions.py',
         'GENOS_RAW_EXPORT_RUN_20261023_R2.txt', 'GUIDE.txt')


def build():
    pins = {'format': 'pipeline-code-pins-v1', 'files': {
        name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in FILES}}
    (HERE/'CODE_PINS.json').write_text(json.dumps(pins,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    service = HERE.parent/'pipeline_service_20261022_r3/GENOS_PIPELINE_SERVICE_20261022_R2.zip'
    with zipfile.ZipFile(service) as z:
        for local, member in [('transport.py','transport.py'),
                              ('filename_versions.py','02_BACKEND/semantic_runtime/filename_versions.py')]:
            assert (HERE/local).read_bytes()==z.read('GENOS_PIPELINE_SERVICE_20261022_R2/'+member)
    for name in FILES:
        if name.endswith('.py'):compile((HERE/name).read_text(),name,'exec')
    target=HERE/(NAME+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name in (*FILES,'CODE_PINS.json'):z.write(HERE/name,NAME+'/'+name)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist())==6
        assert not any(Path(p).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
    manifest={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in [target,HERE/'GENOS_RAW_EXPORT_RUN_20261023_R2.txt',HERE/'GUIDE.txt']}
    (HERE/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':build()
