from pathlib import Path
import hashlib,json,sys,zipfile
H=Path(__file__).resolve().parent;count=0
with zipfile.ZipFile(H/'code.zip') as z:
 for n in z.namelist():
  if n.endswith('.py'):
   compile(z.read(n),n,'exec');count+=1
for n in ('run.py','replace.py','code_smoke.py'):
 compile((H/n).read_bytes(),n,'exec');count+=1
raw=(H/'code.zip').read_bytes()
value={'status':'PASS','python':sys.version,'executable':sys.executable,'modules':count,'code_zip_sha256':hashlib.sha256(raw).hexdigest()}
(H/'PYTHON311.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
