"""New-run recorder: immutable compressed versions plus a small current pointer."""
from pathlib import Path
import hashlib,json,types,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'maintenance'))
from experiment_json import write_raw_json,write_summary

def install(client):
    def compressed(self,path,value):
        body=json.dumps(value,ensure_ascii=False,sort_keys=True)
        if self._key and self._key in body:
            raise RuntimeError('Credential in artifact')
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        fingerprint=hashlib.sha256(body.encode()).hexdigest()
        target=path.parent/'.raw-versions'/(path.stem+'-'+fingerprint+'.json.gz')
        if not target.exists():
            reference=write_raw_json(target,value)
            write_summary(target.with_suffix('.ref.json'),reference)
        else:
            reference=json.loads(target.with_suffix('.ref.json').read_text())
        pointer=path.with_suffix('.raw-ref.json')
        temporary=pointer.with_name('.'+pointer.name+'.pending')
        # Only this small observer pointer changes. All prior raw values remain.
        temporary.write_text(json.dumps({'raw_json':reference},ensure_ascii=False)+'\n')
        temporary.replace(pointer)
    client._write=types.MethodType(compressed,client)
    return client
