from common import *
import shutil,subprocess
f=read(sorted(DES.glob('freeze-*.json'))[-1]);rev=f['candidate_revision']['revision_id'];C=ROOT/f['code_root'];b=read(DES/'baseline.json')
baseline=read(ART/f'regression-main113-{rev}.json');candidate=read(ART/f'regression-candidate-{rev}.json')
maps=[{r['test']:r['status'] for r in result['rows']} for result in (baseline,candidate)]
assert all(len(m)==len(r['rows']) for m,r in zip(maps,(baseline,candidate))), 'nonunique regression identity'
assert maps[0].keys()==maps[1].keys()
new=[k for k,v in maps[0].items() if v=='passed' and maps[1][k]!='passed']
comparison={'same_tests':True,'baseline':{k:baseline[k] for k in ('passed','failed')},'candidate':{k:candidate[k] for k in ('passed','failed')},'new_regressions':new,'status_differences':[k for k in maps[0] if maps[0][k]!=maps[1][k]],'import_leaks':[baseline['import_leaks'],candidate['import_leaks']],'new_model_calls':0}
put(ART/'regression-comparison.json',comparison);assert not new and not any(comparison['import_leaks']),comparison
assert read(ART/('check-'+rev+'.json'))['failed']==0
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h]
engines={r['manifest'] for r in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()}
pins=engines|{'00_SYSTEM/PIPELINE.json'};products=[n for n in changed if n not in pins]
protected={s[3:]:sha(ROOT/s[3:]) for s in subprocess.check_output(['git','status','--porcelain','-z'],cwd=ROOT).decode().split('\0') if s and s[:2]!='??' and (ROOT/s[3:]).is_file() and s[3:] not in changed}
merges={}
for n in changed:
 current=sha(ROOT/n) if (ROOT/n).is_file() else None
 assert current==b['working_files'].get(n),'concurrent working change: '+n
 if current:
  dest=ART/'working-backup'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
 if n in products and current and current not in (b['manifest']['files'].get(n),f['files'][n]):
  merged=subprocess.run(['git','merge-file','-p',str(ROOT/n),str(ROOT/b['manifest']['code_root']/n),str(C/n)],capture_output=True)
  assert merged.returncode==0,(n,merged.stderr.decode())
  dest=ART/'working-merged'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(merged.stdout);merges[n]=dest
# Publish the exact tested serving inventory; never promote unrelated working changes.
S=ART/'staged-code'
for n,h in f['files'].items():
 assert sha(C/n)==h
 dest=S/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,dest)
put(DES/'staging-final.json',{'code_root':str(S.relative_to(ROOT)),'files':f['files'],'changed':changed})
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',b['manifest']['data_path'],'--release-id','requirement-coverage-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files']
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Request requirement coverage in existing ASSESS, original/gap-bound closure and publication; local resource items1-3 excluded.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
for n in products:
 dest=ROOT/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(merges.get(n,C/n),dest)
for n in engines:
 p=ROOT/n;value=read(p);base=read(ROOT/b['manifest']['code_root']/n);target=read(C/n)
 for path,h in target['files'].items():
  if base['files'].get(path)!=h:value['files'][path]=sha(ROOT/path)
 for path in value['files']:value['files'][path]=sha(ROOT/path)
 p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'00_SYSTEM/PIPELINE.json';value=read(p)
for row in value['engines'].values():row['sha256']=sha(ROOT/row['manifest'])
p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
assert all(sha(ROOT/n)==h for n,h in protected.items())
put(ART/'working-integration.json',{'product_files':{n:sha(ROOT/n) for n in products},'pins':{n:sha(ROOT/n) for n in pins},'three_way_merges':list(merges),'protected_files':len(protected),'protected_unchanged':True,'changed_files':changed,'new_model_calls':0})
print('Integrated',len(products),'product/config files;',len(actual),'serving files; preserved',list(merges))
