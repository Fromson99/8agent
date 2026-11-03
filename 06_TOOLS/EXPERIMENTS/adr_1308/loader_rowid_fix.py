from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
rel='08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_seek_20261103_r7/package'
paths=[str(p.relative_to(ROOT)) for p in (ROOT/rel).rglob('*') if p.is_file()]
m=read(ADR/'실험/manifest.json');c=ac.snapshot(ADR,'loader-rowid-fixed',paths,experiment_id=m['experiment_id'],arm_id='optimized',run_ids=['run-001'])
p=c/'snapshot'/rel/'reduced_export.py';s=p.read_text();old="db.execute('SELECT rowid AS fts_row_id,source,node_id FROM label WHERE rowid>? ORDER BY rowid',(after or 0,))";new="db.execute('SELECT rowid AS fts_row_id,source,node_id FROM label'+(' WHERE rowid>?' if after is not None else '')+' ORDER BY rowid',(after,) if after is not None else ())";assert old in s;s=s.replace(old,new);p.write_text(s)
p=c/'snapshot'/rel/'CODE_MANIFEST.json';d=read(p);d['files']['reduced_export.py']=sha(c/'snapshot'/rel/'reduced_export.py');p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
ac.freeze(c);assert not ac.validate(c),ac.validate(c)
v=read(c/'candidate.json')['revisions'][-1]
put(ART/'loader-final-candidate.json',{'candidate':{'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']},'package':str((c/'revisions'/v['revision_id']/'snapshot'/rel).relative_to(ROOT)),
 'reason':'Unconditional first words-content export must preserve rowid 0 and negative rowids; after=0 is a valid explicit checkpoint, not absence of one.', 'working_before':{n:sha(ROOT/n) for n in paths}})
print('Loader-only candidate prepared; MAIN files unchanged')
