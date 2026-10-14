"""One explicit MAIN backfill; preserve and verify the entire existing authority.

No model calls. Actual CM text stays local and is not copied into this receipt.
"""
from pathlib import Path
import json,hashlib,sys,sqlite3,gzip,os,importlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
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
 result={}
 names=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'sw_recall_%' ORDER BY name")]
 for name in names:
  rows=[json.dumps(list(x),ensure_ascii=False,separators=(',',':'),default=lambda x:x.hex()) for x in db.execute('SELECT * FROM "'+name+'"')]
  result[name]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
 return result
db=sqlite3.connect(path);before=fingerprints(db)
backup=A/'artifacts/pre-recall-store.sqlite';archive=backup.with_suffix('.sqlite.gz')
assert not backup.exists() and not archive.exists()
with sqlite3.connect(backup) as target:db.backup(target)
backup_hash=sha(backup)
with backup.open('rb') as src,gzip.open(archive,'wb',compresslevel=6) as dst:
 import shutil
 shutil.copyfileobj(src,dst)
with gzip.open(archive,'rb') as src:assert hashlib.file_digest(src,'sha256').hexdigest()==backup_hash
backup.unlink();db.close()
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
 # Same source binding as real MAIN, established through selected API host.
 import service
 app=service.application()
 assert app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['bounded_recall'] is True
 package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
 cases=importlib.import_module(package+'.legal_agent.unified_runtime').open_cases(app.state.pipeline,runtime,{},principal)
 try:
  actual_binding=source_binding(cases.executor.binding)
 finally:cases.close()
 assert binding==actual_binding
 cards,receipt=lookup(repo,principal,sample['question'],actual_binding,external=False)
 assert cards and any(c['unit_id']==sample['id'] for c in cards)
 public_cards,public_receipt=lookup(repo,principal,sample['question'],actual_binding,external=True)
 assert not public_cards,'Internal CM discovery cannot enter external model context'
 status={'status':'passed','selected_release':p['release_id'],'pointer_generation':p['generation'],'store':str(path.relative_to(R)),'policy':'bounded-wiki-recall-v1','indexed_cards':index_count,'published_heads':len(values),'original_tables_unchanged':True,'original_fingerprints':before,'local_sample_hit':True,'lookup':receipt,'internal_sample_external_offered':len(public_cards),'external_lookup':public_receipt,'model_calls':0,'source_binding':actual_binding,'backup':{'path':str(archive.relative_to(R)),'sha256':sha(archive),'uncompressed_sha256':backup_hash,'restore':'Decompress into a new SQLite file and verify uncompressed_sha256; do not overwrite a running store.'}}
 put(A/'artifacts/main-recall-backfill.json',status)
 print(json.dumps({k:status[k] for k in ('status','indexed_cards','published_heads','original_tables_unchanged','local_sample_hit','internal_sample_external_offered','model_calls')},ensure_ascii=False))
finally:repo.close()
