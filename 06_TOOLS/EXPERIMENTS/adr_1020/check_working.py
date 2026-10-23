from common import *
s=read(ART/'stage.json');i=read(ART/'working-integration.json');C=ROOT/s['roots']['candidate']
checks={n:sha(ROOT/n)==v['after']==sha(C/n) for n,v in i['changed_files'].items()}
mismatches=[];count=0
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 for n,h in read(p).get('files',{}).items():
  count+=1
  if sha(ROOT/n)!=h:mismatches.append({'manifest':str(p.relative_to(ROOT)),'file':n})
pipeline=all(sha(ROOT/e['manifest'])==e['sha256'] for e in read(ROOT/'00_SYSTEM/PIPELINE.json')['engines'].values())
r={'changed_files_match_frozen':checks,'engine_file_pins_checked':count,'engine_mismatches':mismatches,'pipeline_manifest_pins_match':pipeline,
 'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']}
save(ART/'working-final-check.json',r)
print(json.dumps({'changed_files_exact':all(checks.values()),'all_pins_exact':not mismatches and pipeline,'unrelated_pin_mismatches':sorted({x['file'] for x in mismatches}),'main_unchanged':r['main_unchanged']},ensure_ascii=False))
