"""Read-only build inventory check. Never reads settings, source data or secrets."""
import argparse,hashlib,json,sys
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path.home()/'DEV')
parser.add_argument('--out',type=Path,default=Path.cwd()/'SCHEMA_BUILD_INVENTORY.json')
args=parser.parse_args();root=args.root.resolve(strict=True)
spec=json.loads(Path(__file__).with_name('BUILD_SOURCE_BINDING.json').read_bytes())
changes={r['path']:r for r in spec['files']};rows=[]
for name,expected in spec['dependencies'].items():
    p=root/name
    if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('Unsafe path: '+name)
    actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    row=changes.get(name,{})
    rows.append({'path':name,'actual':actual,'expected':expected,
        'status':'CURRENT' if actual==expected else 'SUPPORTED_PREIMAGE' if row.get('before')==actual and actual else 'DIFFERS'})
result={'version':spec['version'],'code_root':str(root),'sys_executable':sys.executable,
        'python':sys.version.split()[0],'files':rows,'writes_to_checkout':0,
        'status':'MATCHED' if all(r['status']!='DIFFERS' for r in rows) else 'REQUIRES_REBASE',
        'genos_field_deployed':False}
with args.out.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':result['status'],'checked':len(rows),'different':sum(r['status']=='DIFFERS' for r in rows),'receipt':str(args.out)},ensure_ascii=False))
