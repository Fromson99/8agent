"""Build exact delivery and prepare bounded local checks; no field actions."""
from pathlib import Path
import json,subprocess,sys,shutil
H=Path(__file__).resolve().parent;R=H.parents[3]
subprocess.run([sys.executable,str(H/'build.py')],check=True)
subprocess.run([sys.executable,str(H/'package.py')],check=True)
shutil.copyfile(H/'PACKAGE_BINDING.json',H/'TESTED_PACKAGE_BINDING.json')
shutil.copyfile(R/'04_EXPERIMENTS/ADR/ADR-0870-host-owned-enum-contract/artifacts/active-consumer.json',H/'active-consumer.json')
check="""from pathlib import Path
import json,sys,zipfile
H=Path(sys.argv[1]);count=0
with zipfile.ZipFile(H/'code.zip') as z:
 for n in z.namelist():
  if n.endswith('.py'):compile(z.read(n),n,'exec');count+=1
p=next(H.glob('*_WORKFLOW_PASTE_ALL.txt'));compile(p.read_bytes(),str(p),'exec')
(H/'PYTHON311_CHECK.json').write_text(json.dumps({'status':'PASS','compiled_modules':count,'workflow_editor':True,'python':sys.version,'executable':sys.executable},indent=2)+'\\n')
"""
subprocess.run([str(Path.home()/'.local/bin/python3.11'),'-c',check,str(H)],check=True)
print('Exact MAIN package ready; Python3.11 compile checked; delivery tests pending')
