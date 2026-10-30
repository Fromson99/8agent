from pathlib import Path
import json,sqlite3,time,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';D=A/'artifacts/design';data=R/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
assets={'glossary/dictionary.sqlite':['entry','definition_candidate','definition_record','corpus_definition','corpus_document'],'glossary/bundle/nodes.sqlite':['node'],'glossary/bundle/identity.sqlite':['entry','uri_alias','concept_mapping','official_relation','source_edge'],'glossary/bundle/translations.sqlite':['unit'],'glossary/cache/c9b659444abbf59fa56ea155820aab5f2cce774250cb7442591a639fcd032055.sqlite':['label']}
rows=[]
for rel,tables in assets.items():
 c=sqlite3.connect((data/rel).as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
 for table in tables:
  n=c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
  sample=[dict(r) for r in c.execute('SELECT * FROM '+table+' LIMIT 256')]
  avg=sum(len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()) for v in sample)/max(1,len(sample))
  row={'asset':rel,'table':table,'rows':n,'sample_rows':len(sample),'sample_average_json_bytes':avg,'rough_bytes_25pct_plus_1400_per_row':int(n*(avg*1.25+1400))};rows.append(row);print(table,n,round(row['rough_bytes_25pct_plus_1400_per_row']/1e9,3),flush=True)
 c.close()
result={'assets':assets,'rows':rows,'rough_total_bytes':sum(v['rough_bytes_25pct_plus_1400_per_row'] for v in rows),'includes_fts_postings':False,'sample_not_capacity_certification':True}
(D/'serving-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('ROUGH',result['rough_total_bytes'])
