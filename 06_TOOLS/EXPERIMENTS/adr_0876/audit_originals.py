from pathlib import Path
import json,sqlite3,hashlib,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0876-original-coverage-scope-probe'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path']);G=R/release['data_path'];db=sqlite3.connect('file:'+str(G/'store.sqlite')+'?mode=ro',uri=True)
targets=['이사회규정','위험관리위원회규정','금융소비자 보호에 관한 법률','금융소비자 보호에 관한 법률 시행령']
raw=[p for p in (R/'01_DATA/RAW').rglob('*') if p.is_file() and any(t.replace(' ','') in p.name.replace(' ','') for t in targets)]
rows=[]
for title in targets:
 matches=db.execute("SELECT document_id,name FROM document WHERE replace(name,' ','') LIKE ?",('%'+title.replace(' ','')+'%',)).fetchall()
 files=[p for p in raw if title.replace(' ','') in p.name.replace(' ','') and p.suffix=='.xml' and '본문' in p.name]
 rows.append({'target':title,'selected_documents':matches,'raw_originals':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in files], 'classification':'RAW_PRESENT_NOT_SELECTED' if files and not matches else 'NOT_FOUND_IN_SELECTED_CATALOGUE_OR_RAW_FILENAMES' if not matches else 'SELECTED'})
coverage=[]
for did,ids in [('51a1477afdec9faa',range(102,108)),('683c4222e1cd54cc',range(962,972))]:
 blocks=[]
 for bid in ids:
  r=db.execute('SELECT unit_id,text FROM source_block WHERE document_id=? AND block_id=?',(did,str(bid))).fetchone()
  blocks.append({'block_id':str(bid),'unit_id':r[0],'chars':len(r[1]),'text_sha256':hashlib.sha256(r[1].encode()).hexdigest()})
 coverage.append({'document_id':did,'blocks':blocks})
old=R/'04_EXPERIMENTS/ADR/ADR-0875-bounded-followup-live/artifacts/run-001/committee-comparison/raw'
trace=[]
for p in sorted(old.glob('*/request.json')):
 s=p.read_text();trace.append({'path':str(p.relative_to(R)),'sha256':sha(p),'contains_article8_item1':'위험관리조직 구조 및 업무 분장' in s,'contains_article8_proviso':'제4호 및 제5호' in s})
withdrawal=R/'04_EXPERIMENTS/ADR/ADR-0873-main83-workflow-live-diagnosis/artifacts/withdrawal-diagnosis.json'
out={'pointer':pointer,'selected_manifest_sha256':sha(G/'manifest.json'),'targets':rows,'available_original_blocks':coverage,'actual_parent_delivery_trace':trace,
 'withdrawal_prior_diagnosis':{'path':str(withdrawal.relative_to(R)),'sha256':sha(withdrawal),'facts':read(withdrawal)},
 'conclusions':['Article8 subitems exist and were delivered in later ITEMS, then omitted from final COMPARE because only model-selected citations were retained.','Initial article3-43 read omitted descendant items; database has them. Read scope, not original-data loss.','Board regulations not found by selected-catalogue/RAW-filename audit; this does not prove no embedded copy elsewhere.','Consumer protection law exists in legacy RAW but not active data; no access-scope expansion is performed.','PENDING was a valid model decision with25read handles and0presented pages; it was not transport timeout or schema failure.'],
 'repair_scope':'Original context closure and issue focus; precise proviso attachment guidance and explicit navigation counts. Missing originals remain missing; no fabricated evidence or forced semantic retry.'}
p=A/'artifacts/original-coverage.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');db.close();print('Original-coverage audit saved; no data/model mutations')
