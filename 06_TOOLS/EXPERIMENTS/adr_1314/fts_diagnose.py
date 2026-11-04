from common import *
import sqlite3
b=read(DES/'baseline.json');data=ROOT/b['release']['data_path'];manifest=read(data/'manifest.json');p=data/manifest['fulltext']['path']/'units.sqlite'
with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
 count=db.execute('SELECT COUNT(*) FROM unit_fts').fetchone()[0]
 # FTS5 id=1 averages record holds document count then token counts per column.
 blob=db.execute('SELECT block FROM unit_fts_data WHERE id=1').fetchone()[0]
 values=[];value=0
 for byte in blob:
  value=(value<<7)|(byte&127)
  if byte<128:values.append(value);value=0
 assert values[0]==count
stats=read(ART/'actual/oracle/binding.json')['oracle_fts_statistics'];docs=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation/artifacts/design/documents.json')['documents']
put(ART/'fts-statistics-diagnosis.json',{'sqlite_actual_fts_documents':count,'sqlite_fts_averages_varints':values,'oracle_published_statistics':stats,'oracle_published_authorized_corpus_documents':len(docs),'source_original_hash_same':True,'scope':'Local readonly SQLite count+FTS5aggregateblob; Oracle stats from previouslycapturedactualrequest, extraOraclequeries0.','reason':'Oracle local Gold publication contains21document corpus while SQLite index covers whole generation. BM25 global corpus N/average differ; first10rankedbodies/totals equalitydoesnotimplyscores equality. No score normalization or artificial equality was applied.','ddl':0,'writes':0})
print('FTS statistics:',count,values,stats)
