"""First navigation choice and request-entry definition flag per question (model outputs as stored; no model call)."""
import json,gzip,sys,collections
from pathlib import Path
def scan(adr):
    out={}
    for d in sorted(Path(adr,'artifacts/public-live').glob('cm-*-candidate')):
        calls=json.load(open(d/'calls.json'));first=None;asks=None;defs_in_first=None
        for c in calls:
            n='%03d'%c['number'];p=d/'canonical'/(n+'-output.json.gz')
            if not p.exists():continue
            o=json.load(gzip.open(p))
            if c['stage']=='request-entry' and isinstance(o,dict):
                asks=((o.get('search') or {}).get('asks_definition'))
            elif first is None and 'navigation' in c['stage'] and isinstance(o,dict) and o.get('choice'):
                first=o['choice']
                i=json.dumps(json.load(gzip.open(d/'canonical'/(n+'.json.gz'))),ensure_ascii=False)
                defs_in_first=i.count('definition_role')
        out[d.name[:6]]={'asks_definition':asks,'first_choice':first,'definition_entries_in_first_menu':defs_in_first}
    return out
new=scan(sys.argv[1]);old=scan(sys.argv[2])
print('new first',collections.Counter(v['first_choice'] for v in new.values()))
print('old first',collections.Counter(v['first_choice'] for v in old.values()))
print('asks_definition',collections.Counter(v['asks_definition'] for v in new.values()))
print('asks true',[k for k,v in new.items() if v['asks_definition']])
print('new menus with definition entries',sum(1 for v in new.values() if v['definition_entries_in_first_menu']))
json.dump({'new':new,'old':old},open(Path(sys.argv[1],'artifacts/first-actions.json'),'w'),ensure_ascii=False,indent=1)
