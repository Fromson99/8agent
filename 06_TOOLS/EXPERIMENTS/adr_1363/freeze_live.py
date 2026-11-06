from common import *
import ast
for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file() and '__pycache__' not in p.parts],*DES.glob('*.json')]
paths=[p for p in paths if p.name!='freeze-public.json']
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True,'live_calls_started':False})
print('Frozen',len(paths),'runner/config/transport files')
