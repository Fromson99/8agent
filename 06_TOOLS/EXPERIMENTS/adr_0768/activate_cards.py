"""One explicit MAIN backfill; preserve and verify the entire existing authority.

No model calls. Actual CM text stays local and is not copied into this receipt.
"""
from pathlib import Path
import json,hashlib,sys,sqlite3,gzip,os,resource,fcntl
resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0768-bounded-wiki-public-qualification'
lock=(A/'artifacts/recall-maintenance.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert p['release_id']=='bounded-wiki-recall-20261013-r1'
m=read(R/p['manifest_path']);code=R/m['code_root']
sys.dont_write_bytecode=True;sys.path[:0]=[str(code/'02_BACKEND'),str(R)]
from lawrag.platform.workspace import load_layout
from semantic_runtime.legal_agent.shortcut_store import selected_store
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.wiki_recall import lookup,source_binding
from lawrag.pipeline.unified_memory import main
runtime=load_layout(R).path('runtime')/'semantic';path=selected_store(runtime)
def fingerprints(db):
 db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA temp_store=FILE')
 result={}
 names=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'sw_recall_%' ORDER BY name")]
 for name in names:
  quoted='"'+name.replace('"','""')+'"'
  definition=db.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?',(name,)).fetchone()[0]
  primary=[r[1] for r in sorted(db.execute('PRAGMA table_info('+quoted+')').fetchall(),key=lambda r:r[5]) if r[5]]
  order=','.join('"'+x.replace('"','""')+'"' for x in primary) if 'WITHOUT ROWID' in definition.upper() else 'rowid'
  h=hashlib.sha256();count=0
  for row in db.execute('SELECT * FROM '+quoted+' ORDER BY '+order):
   value=json.dumps(list(row),ensure_ascii=False,separators=(',',':'),default=lambda x:x.hex()).encode()
   h.update(len(value).to_bytes(8,'big'));h.update(value);count+=1
  result[name]={'rows':count,'sha256':h.hexdigest()}
 return result
db=sqlite3.connect(path);before=fingerprints(db)
print('Original fingerprints streamed',len(before),'tables; peak KiB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True)
backup=A/'artifacts/pre-recall-store.sqlite';archive=backup.with_suffix('.sqlite.gz')
assert not backup.exists() and not archive.exists()
with sqlite3.connect(backup) as target:db.backup(target,pages=128,sleep=0.01)
backup_hash=sha(backup)
with backup.open('rb') as src,gzip.open(archive,'wb',compresslevel=6) as dst:
 import shutil
 shutil.copyfileobj(src,dst)
with gzip.open(archive,'rb') as src:assert hashlib.file_digest(src,'sha256').hexdigest()==backup_hash
backup.unlink();db.close()
print('Streaming backup verified; peak KiB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True)
# Existing pipeline maintenance entry, using the selected release's exact code.
main(['recall-rebuild','--root',str(R),'--store-version','4'])
repo=ShortcutRepository(path)
try:
 after=fingerprints(repo.db);assert before==after,'Original state changed by derived backfill'
 index_count=repo.db.execute('SELECT COUNT(*) FROM sw_recall_card').fetchone()[0]
 rows=repo.db.execute("SELECT k.payload FROM sw_knowledge k JOIN sw_unit u ON u.id=k.unit AND u.head=k.revision JOIN sw_lifecycle l ON l.unit=k.unit AND l.revision=k.revision WHERE l.status='PUBLISHED'").fetchall()
 values=[json.loads(x[0]) for x in rows]
 assert index_count>=len(values)>0
 docs=sorted({d for v in values for d in v['documents']})
 principal={'user_id':'local-recall-read-check','team_id':'risk_team','authenticated':True,'document_ids':docs}
 eligible=[v for v in values if v.get('core_evidence_route',{}).get('contract')=='curated-core-evidence-route-v1']
 assert eligible
 sample=eligible[0];binding=sample['core_evidence_route']['source_binding']
 # Reuse completed real service verification; never load the multi-GB server again.
 smoke=read(A/'artifacts/main-smoke.json')
 assert smoke['status']=='passed' and smoke['pointer']==p
 assert sha(R/p['manifest_path'])==p['release_manifest_sha256']
 config=read(code/'00_SYSTEM/PIPELINE.json')
 assert config['shortcut_v4']['features']['bounded_recall'] is True
 generation=R/m['data_path'];manifest=read(generation/'manifest.json')
 assert sha(generation/'manifest.json')==m['data_manifest_sha256']==smoke['execution_binding']['data_manifest_sha256']
 fulltext_path=generation/manifest['fulltext']['path']/'manifest.json'
 assert sha(fulltext_path)==smoke['execution_binding']['fulltext_manifest_sha256']
 fulltext=read(fulltext_path)
 actual_binding={'generation':manifest['generation_id'],'store_sha256':manifest['store_sha256'],'unit_index_sha256':fulltext['index_sha256']}
 assert binding==actual_binding
 cards,receipt=lookup(repo,principal,sample['question'],actual_binding,external=False)
 assert cards and any(c['unit_id']==sample['id'] for c in cards)
 public_cards,public_receipt=lookup(repo,principal,sample['question'],actual_binding,external=True)
 assert not public_cards,'Internal CM discovery cannot enter external model context'
 status={'status':'passed','selected_release':p['release_id'],'pointer_generation':p['generation'],'store':str(path.relative_to(R)),'policy':'bounded-wiki-recall-v1','indexed_cards':index_count,'published_heads':len(values),'original_tables_unchanged':True,'original_fingerprints':before,'local_sample_hit':True,'lookup':receipt,'internal_sample_external_offered':len(public_cards),'external_lookup':public_receipt,'model_calls':0,'source_binding':actual_binding,'backup':{'path':str(archive.relative_to(R)),'sha256':sha(archive),'uncompressed_sha256':backup_hash,'restore':'Decompress into a new SQLite file and verify uncompressed_sha256; do not overwrite a running store.'}}
 status.update(server_reloaded=False,binding_basis='Selected immutable manifests plus completed actual service receipt',peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,virtual_memory_limit_mib=768,authority_hash_method='Length-prefixed canonical row serialization, streamed in rowid or primary-key order',recovery_receipt='artifacts/interruption-recovery.json')
 put(A/'artifacts/main-recall-backfill.json',status)
 print(json.dumps({k:status[k] for k in ('status','indexed_cards','published_heads','original_tables_unchanged','local_sample_hit','internal_sample_external_offered','model_calls')},ensure_ascii=False))
finally:repo.close()
