"""Publish the selected generation's 21 Gold documents as a fresh query release the current code can serve.

The local Gold (A8_GR12_CM1208) holds an r12 packed engine publication that the product's native
Oracle path does not read. This script creates an isolated owner, copies the 13 Gold table
structures and the source rows (DOC_VER/UNIT/BLK/SRC_POST, same dataset version), publishes a
query release with the current publisher (lawrag.pipeline.oracle_query_publish, rows limited to
the 21 documents where a row names a document), re-binds the existing bge-m3 vectors to the new
release with source IDs (the item unit -> native.source mapping), and activates channel adr1459.
No model call. Gold itself is not modified.

usage: publish_local_release.py [--owner A8_ADR1459] [--channel adr1459]
"""
from common import *
import argparse,sqlite3,time,secrets,shutil,tempfile,traceback
sys.path.insert(0,str(Path(__file__).parent));import oracle_local as ol
sys.path[:0]=[str(ROOT/'02_BACKEND')]
import oracledb
from lawrag.pipeline import oracle_query_publish as pub, oracle_query_navigation_publish as navpub
from semantic_runtime import navigation_match, structure_navigation, inherited_navigation
from semantic_runtime.oracle_dp_assets import inventory
from semantic_runtime.oracle_dp_io import canonical, digest, file_sha
from semantic_runtime.oracle_development_mapping import LOGICAL
ap=argparse.ArgumentParser();ap.add_argument('--owner',default='A8_ADR1459');ap.add_argument('--channel',default='adr1459');ap.add_argument('--reset',action='store_true');a=ap.parse_args()
OWNER=a.owner;GOLD=ol.GOLD_OWNER;receipt_path=DES/'local-release.json'
if receipt_path.exists():raise SystemExit('receipt exists: '+str(receipt_path))
G=ROOT/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
log=(ART/'publish-local-release.log').open('a')
def say(*x):
 line=' '.join(str(v) for v in x);print(line,flush=True);log.write(time.strftime('%H:%M:%S ')+line+'\n');log.flush()
conn=ol.connect();cur=conn.cursor();started=time.time();receipt={'owner':OWNER,'channel':a.channel,'gold_owner':GOLD,'steps':[]}
TABLES=['DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST','SRCH_POST','SRCH_ROW','SRCH_CHNL','ONTL_POST','ONTL_HEAD','ONTL_ANC','VCTR_POST','VCTR_ITEM','VCTR_HEAD']
T=lambda owner,key:f'{owner}.IDD_B03_LGL_{key}'
cur.execute("select count(*) from all_users where username=:u",{'u':OWNER})
if cur.fetchone()[0]:
 if not (a.reset and OWNER.startswith('A8_ADR1459')):raise SystemExit('owner exists: '+OWNER)
 cur.execute(f'DROP USER {OWNER} CASCADE');say('dropped incomplete owner',OWNER)
cur.execute(f'CREATE USER {OWNER} IDENTIFIED BY "x{secrets.token_hex(12)}" DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS');cur.execute(f'GRANT CREATE SESSION,CREATE TABLE TO {OWNER}')
for key in TABLES:cur.execute(f'CREATE TABLE {T(OWNER,key)} AS SELECT * FROM {T(GOLD,key)} WHERE 1=0')
say('owner and 13 tables created',OWNER)
for key in ('DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST'):
 cur.execute(f'INSERT INTO {T(OWNER,key)} SELECT * FROM {T(GOLD,key)}');receipt['steps'].append({'copy':key,'rows':cur.rowcount});say('copied',key,cur.rowcount)
conn.commit()
cur.execute(f"select BODY_POST_HASH_VALU,BODY_POST_IFMN_CTNT from {T(GOLD,'SRC_POST')}");src_id,body=cur.fetchone();src=json.loads(body)
scope=set(src['projection_scope']['document_ids']);assert len(scope)==21
# Scoped copy of store.sqlite so per-document structure derivation runs for the 21 documents only.
tmp=Path(tempfile.mkdtemp(prefix='adr1459-store-'));scoped=tmp/'store.sqlite'
full=sqlite3.connect((G/'store.sqlite').as_uri()+'?mode=ro',uri=True);copy=sqlite3.connect(scoped)
for name,kind,sql in full.execute("select name,type,sql from sqlite_master where sql is not null and name not like 'sqlite_%'"):
 if kind in ('table','index','view'):copy.execute(sql)
marks=','.join('?'*len(scope))
base_tables={n for n, in full.execute("select name from sqlite_master where type='table'")}
for table in [t for t in ('document','source_unit','source_block','block_payload') if t in base_tables]:
 cols=[r[1] for r in full.execute(f'pragma table_info("{table}")')]
 rows=full.execute(f'select {",".join(cols)} from "{table}" where document_id in ({marks})',sorted(scope)).fetchall()
 copy.executemany(f'insert into "{table}" ({",".join(cols)}) values ({",".join("?"*len(cols))})',rows);say('scoped store',table,len(rows))
copy.commit();copy.close();full.close()
original_projected=pub.projected_rows
def scoped_rows(path,relative,source_release):
 if relative=='store.sqlite':
  # The Gold source release chains were computed over the 21 documents: the scoped copy reproduces them exactly.
  yield from pub.source_records(str(scoped),source_release)
  yield from navpub.records(str(scoped),'store.sqlite',source_release)
  return
 for r in original_projected(path,relative,source_release):
  if r['document_id'] is not None and r['document_id'] not in scope:continue
  yield r
pub.projected_rows=scoped_rows
t=time.time();manifest,assets,tables=pub.describe(G,src);say('describe done',round(time.time()-t),'s kinds',len(tables),'rows',sum(v['rows'] for v in tables.values()))
_,inventory_assets=inventory(G)
value={'schema_version':pub.SCHEMA,'status':'COMPLETE','source_release_id':src_id,'dataset_version':src['dataset_version'],'source_manifest':manifest,
 'search_selection':src.get('search_selection'),'assets':assets,'tables':tables,'projection':'sqlite-logical-rows-and-fts5-positions-v1',
 'metadata':pub.asset_metadata(G,inventory_assets),'selection_proof':pub.selection_proof(G,manifest),'publisher_sha256':file_sha(pub.__file__),
 'navigation_compilers':{m.__name__:file_sha(m.__file__) for m in (navpub,navigation_match,structure_navigation,inherited_navigation)},
 'experiment_scope_note':'rows naming a document are limited to the 21 Gold documents (ADR-1459 local publication)'}
qid=digest(value);say('query release id',qid)
cols=LOGICAL['SRCH_ROW'].split();phys={'RFRN_POST_HASH_VALU':'RFRN_POST_HASH_VALU','RFRN_DTA_TYPE_VALU':'RFRN_DTA_TYPE_VALU','RFRN_DTA_ID':'RFRN_DTA_ID','DOC_ID':'RGLT_DOC_ID','RFRN_DTA_IDNF_CTNT':'RFRN_DTA_IDNF_CTNT','BLNG_DTA_IDNF_CTNT':'BLNG_DTA_IDNF_CTNT','TAGT_DTA_IDNF_CTNT':'TAGT_DTA_IDNF_CTNT','SRCH_DATA_HASH_VALU':'RFRN_DATA_HASH_VALU','SRCH_DATA_CTNT':'RFRN_DATA_CTNT'}
insert_sql=f'INSERT INTO {T(OWNER,"SRCH_ROW")} ({",".join(phys[c] for c in cols)}) VALUES ({",".join(":"+str(i+1) for i in range(len(cols)))})'
cur.setinputsizes(None,None,None,None,None,None,None,None,oracledb.DB_TYPE_CLOB)
batch=[];total=0;kinds={};unit_source={};t=time.time()
def flush():
 global batch
 if batch:cur.executemany(insert_sql,batch);conn.commit();batch=[]
for relative in assets:
 for r in pub.projected_rows(G/relative,relative,src):
  batch.append((qid,r['kind'],r['row_id'],r['document_id'],r['lookup_id'],r['owner_id'],r['target_id'],r['sha256'],canonical(r['value'])));total+=1;kinds[r['kind']]=kinds.get(r['kind'],0)+1
  if r['kind']=='native.source':
   v=r['value'];unit_source.setdefault((r['document_id'],str(v.get('unit_id'))),[]).append(r['lookup_id'])
  if len(batch)>=5000:
   flush()
   if total%200000<5000:say('rows',total,'kinds',len(kinds),round(time.time()-t),'s')
flush();say('rows inserted',total,'in',round(time.time()-t),'s')
assert total==sum(v['rows'] for v in tables.values()),(total,sum(v['rows'] for v in tables.values()))
cur.execute(f'INSERT INTO {T(OWNER,"SRCH_POST")} (RFRN_POST_HASH_VALU,RFRN_POST_IFMN_CTNT) VALUES (:1,:2)',(qid,canonical(value)))
t=time.time()
for name,uniq,columns in [('X0','UNIQUE','RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,RFRN_DTA_ID'),('X1','','RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,RFRN_DTA_IDNF_CTNT'),('X2','','RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,BLNG_DTA_IDNF_CTNT'),('X3','','RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,TAGT_DTA_IDNF_CTNT'),('X4','','RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,RGLT_DOC_ID')]:
 cur.execute(f'CREATE {uniq} INDEX {OWNER}.{name}_SRCH_ROW ON {T(OWNER,"SRCH_ROW")} ({columns})')
for key,columns in [('DOC_VER','DTLS_HASH_VALU,RGLT_DOC_ID'),('DOC_UNIT','DTLS_HASH_VALU,RGLT_DOC_ID,STRC_UNIT_ID'),('DOC_BLK','DTLS_HASH_VALU,RGLT_DOC_ID,BODY_SLC_ID'),('SRCH_POST','RFRN_POST_HASH_VALU'),('SRCH_CHNL','RFRN_CHNL_NAME'),('VCTR_POST','VCTR_POST_ID'),('VCTR_ITEM','VCTR_POST_ID,VCTR_SCTN_ID'),('VCTR_HEAD','RFRN_POST_HASH_VALU'),('SRC_POST','BODY_POST_HASH_VALU')]:
 cur.execute(f'CREATE UNIQUE INDEX {OWNER}.X0_{key} ON {T(OWNER,key)} ({columns})')
cur.execute(f'CREATE INDEX {OWNER}.X1_DOC_UNIT ON {T(OWNER,"DOC_UNIT")} (DTLS_HASH_VALU,RGLT_DOC_ID,UPPR_STRC_UNIT_ID,STRC_UNIT_ID)')
cur.execute(f'CREATE INDEX {OWNER}.X1_DOC_BLK ON {T(OWNER,"DOC_BLK")} (DTLS_HASH_VALU,RGLT_DOC_ID,STRC_UNIT_ID,BODY_SLC_ID)')
cur.execute(f'CREATE INDEX {OWNER}.X1_VCTR_ITEM ON {T(OWNER,"VCTR_ITEM")} (VCTR_POST_ID,RGLT_DOC_ID,BODY_UNIT_ID,VCTR_SCTN_ID)')
conn.commit();say('indexes created',round(time.time()-t),'s')
# Vectors: same bge-m3 items, re-bound to the new release with source IDs.
cur.execute(f"select VCTR_POST_ID,VCTR_POST_IFMN_CTNT from {T(GOLD,'VCTR_POST')}");old_vid,old_body=cur.fetchone();old=json.loads(old_body);profile=old['manifest']['profile']
vmanifest={'schema_version':'gold-vector-manifest-preview-v1','query_id':qid,'source_release_id':src_id,'dataset_version':src['dataset_version'],'documents':sorted(scope),'profile':profile,
 'segment_profile':old['manifest'].get('segment_profile'),'rebound_from':old_vid,'rebinding':'BODY_UNIT_ID (unit) -> native.source lookup_id (source id) of the new release'}
vid=digest(vmanifest)
cur.execute(f"select VCTR_SCTN_ID,RGLT_DOC_ID,BODY_UNIT_ID from {T(GOLD,'VCTR_ITEM')} where VCTR_POST_ID=:p",{'p':old_vid});items=cur.fetchall()
mapped=[];skipped={'no_source':0,'ambiguous':0}
for sctn,did,uid in items:
 sids=unit_source.get((did,str(uid)),[])
 if len(sids)==1:mapped.append((vid,sids[0],old_vid,sctn))
 else:skipped['ambiguous' if sids else 'no_source']+=1
t=time.time()
for i in range(0,len(mapped),2000):
 cur.executemany(f'INSERT INTO {T(OWNER,"VCTR_ITEM")} (VCTR_POST_ID,VCTR_SCTN_ID,RGLT_DOC_ID,BODY_UNIT_ID,VCTR_DTLS_IFMN_CTNT,EMBD_VCTR) SELECT :1,VCTR_SCTN_ID,RGLT_DOC_ID,:2,VCTR_DTLS_IFMN_CTNT,EMBD_VCTR FROM {T(GOLD,"VCTR_ITEM")} WHERE VCTR_POST_ID=:3 AND VCTR_SCTN_ID=:4',mapped[i:i+2000])
conn.commit()
cur.execute(f"select count(*) from {T(OWNER,'VCTR_ITEM')} where VCTR_POST_ID=:p",{'p':vid});count=cur.fetchone()[0];assert count==len(mapped)
completion={'status':'READY','count':count,'profile_sha256':digest(profile),'rebound_items':len(mapped),'skipped':skipped,'source_items':len(items)}
cur.execute(f'INSERT INTO {T(OWNER,"VCTR_POST")} (VCTR_POST_ID,VCTR_POST_IFMN_CTNT) VALUES (:1,:2)',(vid,canonical({'manifest':vmanifest,'completion':completion})))
cur.execute(f'INSERT INTO {T(OWNER,"VCTR_HEAD")} (RFRN_POST_HASH_VALU,VCTR_POST_ID,CHAN_NO) VALUES (:1,:2,1)',(qid,vid))
cur.execute(f'INSERT INTO {T(OWNER,"SRCH_CHNL")} (RFRN_CHNL_NAME,RFRN_POST_HASH_VALU,CHAN_NO) VALUES (:1,:2,1)',(a.channel,qid))
conn.commit();say('vectors rebound',count,'skipped',skipped,round(time.time()-t),'s')
cur.execute("select sum(bytes)/1024/1024/1024 from dba_segments where owner=:o",{'o':OWNER});gib=float(cur.fetchone()[0] or 0)
receipt.update(query_release_id=qid,vector_post_id=vid,rows=total,kinds=kinds,vector={'count':count,'skipped':skipped,'old_post':old_vid},
 dataset_version=src['dataset_version'],source_release_id=src_id,documents=sorted(scope),segments_gib=round(gib,2),seconds=round(time.time()-started),
 publisher_sha256=value['publisher_sha256'],navigation_compilers=value['navigation_compilers'],generation=str(G.relative_to(ROOT)),scoped_store_rows='21 documents',model_calls=0)
put(receipt_path,receipt);shutil.rmtree(tmp,ignore_errors=True);say('DONE',json.dumps({k:receipt[k] for k in ('rows','segments_gib','seconds')}))
