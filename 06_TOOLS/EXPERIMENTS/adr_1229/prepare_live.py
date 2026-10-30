from common import *
T=ROOT/'06_TOOLS/EXPERIMENTS/adr_1230';T.mkdir(exist_ok=True)
old=ROOT/'06_TOOLS/EXPERIMENTS/adr_1228'
for n in ('common.py','resource_guard.py','freeze.py','live.py'):
 s=(old/n).read_text().replace('ADR-1228-source-first-authoring-live','ADR-1230-source-meaning-evidence-live')
 if n=='freeze.py':s=s.replace("'source-first'","'meaning-evidence'").replace('새 정규화부터','저장 정규화 재사용 후')
 if n=='live.py':
  s=s.replace('types,httpx','types,httpx,shutil')
  start=s.index('repo=Repository(');end=s.index("put(out/'binding.json'",start)
  earlier=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1222/live.py').read_text();a=earlier.index("continuation=read(DES/'continuation.json')");z=earlier.index("put(out/'binding.json'",a)
  s=s[:start]+earlier[a:z].replace("namespace='ADR1220-only'","namespace='ADR1228-only'")+s[end:]
  s=s.replace('max_calls=9','max_calls=4').replace("'maximum_physical_calls':9","'maximum_physical_calls':4").replace('client.calls>=9','client.calls>=4')
  a=s.index("  phase='normalize-'");z=s.index('  if i>0 and revision==0:',a)
  s=s[:a]+"  row.update(normalization='REUSED_VERIFIED',observation=continuation['observations'][i])\n"+s[z:]
  s=s.replace("'synthetic_refusals':2","'synthetic_refusals':3")
 (T/n).write_text(s)
print(T)
