import hashlib,importlib.util,json,os,sqlite3,subprocess,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit',P/'audit_internal_links.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def enc(x):return json.dumps(x,ensure_ascii=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fixture(p,compact=False):
 p.mkdir();n=p/'navigation';n.mkdir();s=sqlite3.connect(p/'store.sqlite');c=sqlite3.connect(n/'navigation.sqlite')
 s.executescript('create table document(document_id text,name text,source_artifact_sha256 text,json text);create table source_unit(document_id text,unit_id text,parent_id text,json text);create table source_block(document_id text,block_id text,unit_id text,text text,source_artifact_sha256 text,json text);')
 c.executescript('create table source(id text primary key,document_id text,article text,json text);create table reference(id text primary key,document_id text,json text);create table reference_end(source_id text,reference_id text);create table reference_target(reference_id text,ordinal int,source_id text,unit_id text,unit_path text,block_ids text,target_level text);create table source_unit_map(source_id text,unit_id text,parent_id text,ordinal text,surface text,block_ids text,family text);create table definition(id text,document_id text,json text);')
 docs=[('d','상품위원회운영지침 (합성)','internal','risk_team'),('ext','외규 (합성)','external',None),('secret','다른 팀 문서 (합성)','internal','another_team'),('zero','표현 없는 내규 (합성)','internal','risk_team')]
 for did,name,kind,team in docs:s.execute('insert into document values (?,?,?,?)',(did,name,'a'*64,enc({'document_metadata':{'source_category':kind,'team':team,'version':'test-v1'}})))
 texts={'1':'“신상품”이라 함은 관련 준칙에서 정한 바에 따라 신상품으로 인정되는 상품을 말한다.',
 '2':'제2조를 준용한다.','3':'제9조를 준용한다.','4':'제3조를 따른다.','5':'제2조를 준용한다. 관련 준칙에서 따로 정한다.',
 '6':'<img src=x onerror=alert(1)> 관련 규정에 따른다.','7':'제2조를 준용한다.', '8':'제2조를 따른다.',
 '9':'제2조를 따른다.', '10':'제2조를 따른다.'}
 def block(did,bid,text,sid):
  s.execute('insert into source_unit values (?,?,?,?)',(did,bid,None,enc({'title':'제'+bid+'조'})))
  s.execute('insert into source_block values (?,?,?,?,?,?)',(did,bid,bid,text,'a'*64,'{}'))
  obj={'id':sid,'document_id':did,'document_name':did,'unit_id':bid,'heading':'제'+bid+'조','blocks':[{'block_id':bid,'text':text}]}
  c.execute('insert into source values (?,?,?,?)',(sid,did,None,enc(obj)));c.execute('insert into source_unit_map values (?,?,?,?,?,?,?)',(sid,bid,None,'[]','',enc([bid]),'article'))
 for bid,text in texts.items():block('d',bid,text,'s'+bid)
 block('ext','20','제20조 대상 원문 <b>합성</b>','target');block('secret','30','노출되면 안되는 다른 팀 본문','restricted');block('zero','1','대상 업무 목록','zero')
 for bid,tid in [('2','target'),('3',None),('4','absent'),('5','target'),('7','restricted'),('8','target'),('9','target'),('10','target')]:
  text=texts[bid];mention=text[:3];t={'source_id':tid,'unit_id':'20' if tid=='target' else '30','block_ids':['20' if tid=='target' else '30'],'unit_path':[],'target_level':'provision'}
  if bid=='9':t['block_ids']=['missing']
  r={'id':'r'+bid,'source_id':'s'+bid,'document_id':'d','block_id':bid,'source_text':text,'source_text_sha256':a.sha_text(text),'mention_start':0,'mention_end':3,'mention_text':mention,'mention_text_sha256':a.sha_text(mention),'targets':[t] if tid else [],'target_source_ids':[tid] if tid else [],'reference_role':'APPLIES_MUTATIS_MUTANDIS','coverage_state':'COMPLETE' if tid else 'UNRESOLVED','resolution':'EXACT' if tid else 'UNRESOLVED'}
  if bid=='8':r['source_text_sha256']='0'*64
  c.execute('insert into reference values (?,?,?)',(r['id'],'d',enc(r)))
  c.execute('insert into reference_end values (?,?)',('s'+bid,r['id']))
  if tid:
   if bid!='10':c.execute('insert into reference_end values (?,?)',(tid,r['id']))
   c.execute('insert into reference_target values (?,?,?,?,?,?,?)',(r['id'],0,tid,t['unit_id'],'[]',enc(t['block_ids']),'provision'))
 c.execute('insert into definition values (?,?,?)',('definition','d',enc({'id':'definition','key':'신상품','block_id':'1','source_text_sha256':a.sha_text(texts['1'])})))
 if compact:
  s.executescript('alter table source_block rename to block_payload;create view source_block as select * from block_payload;')
  c.executescript("alter table reference rename to reference_payload;create table reference_body(sha256 text primary key,text text);insert or ignore into reference_body select json_extract(json,'$.source_text_sha256'),json_extract(json,'$.source_text') from reference_payload;update reference_payload set json=json_remove(json,'$.source_text');create view reference as select r.id,r.document_id,json_set(r.json,'$.source_text',b.text) as json from reference_payload r join reference_body b on b.sha256=json_extract(r.json,'$.source_text_sha256');")
 s.commit();c.commit();s.close();c.close()
 m={'schema_version':'term-source-generation-v2' if compact else 'term-source-generation-v1','generation_id':'synthetic','store_sha256':sha(p/'store.sqlite')}
 nm={'schema_version':'term-navigation-index-v7','generation_id':'synthetic','source_store_sha256':m['store_sha256'],'source_manifest_sha256':a.sha_text(json.dumps(m,ensure_ascii=False,sort_keys=True,separators=(',',':'))),'index_sha256':sha(n/'navigation.sqlite')}
 (n/'manifest.json').write_text(enc(nm));m['navigation']={'path':'navigation','manifest_sha256':sha(n/'manifest.json')};(p/'manifest.json').write_text(enc(m))
 return p

def main():
 result={};base=Path(tempfile.mkdtemp(prefix='internal-link-audit-tests-'))
 env={k:v for k,v in os.environ.items() if k not in ('DP','GENOS_GENERATION')}
 def run(g,out,*extra):
  return subprocess.run([sys.executable,str(P/'audit_internal_links.py'),'--generation',str(g),'--output',str(out),'--code-root',str(base/'empty'),*extra],capture_output=True,text=True,env=env)
 for compact in [False,True]:
  g=fixture(base/('compact' if compact else 'legacy'),compact);before={str(p):sha(p) for p in g.rglob('*') if p.is_file()};out=base/(g.name+'-report');r=run(g,out);assert r.returncode==1,r.stdout+r.stderr
  rows=[json.loads(x) for x in (out/'findings.jsonl').read_text().splitlines()];by={}
  for row in rows:by.setdefault(row['block_id'],[]).append(row)
  assert by['1'][0]['status']=='NO_REFERENCE' and by['1'][0]['definitions'][0]['key']=='신상품'
  assert by['2'][0]['status']=='NEARBY_REFERENCE'
  assert by['3'][0]['status']=='UNRESOLVED'
  assert by['4'][0]['status']=='BROKEN'
  assert len(by['5'])==2 and by['5'][1]['status']=='NO_REFERENCE',by['5']
  assert by['7'][0]['status']=='RESTRICTED'
  assert by['8'][0]['status']=='BROKEN' and by['9'][0]['status']=='BROKEN' and by['10'][0]['status']=='BROKEN'
  page=(out/'index.html').read_text();assert '<img src=x' not in page and '&lt;img' in page
  assert all('노출되면 안되는' not in p.read_text() for p in out.glob('*.html'))
  assert all((out/t['href']).exists() for row in rows for ref in row['references'] for t in ref['targets'] if t.get('href'))
  summary=json.loads((out/'summary.json').read_text());assert summary['status']=='CHECKS_COMPLETED' and any(d['id']=='zero' and d['rows']==0 for d in summary['documents'])
  assert before=={str(p):sha(p) for p in g.rglob('*') if p.is_file()}
  assert run(g,out).returncode==2
  assert run(g,g/'bad-output').returncode==2 and not (g/'bad-output').exists()
  result[g.name]={'passed_assertions':15,'rows':len(rows),'exit':r.returncode,'summary':summary['counts']}
  (g/'navigation/navigation.sqlite-wal').touch();assert run(g,base/(g.name+'-wal')).returncode==2;(g/'navigation/navigation.sqlite-wal').unlink()
  with (g/'store.sqlite').open('ab') as f:f.write(b'bad')
  assert run(g,base/(g.name+'-hash')).returncode==2
  result[g.name]['failure_injection']='WAL and changed input rejected'
 # Save only the synthetic report, no input DB duplicates.
 import shutil
 sample=P/'SAMPLE';sample.mkdir(exist_ok=True)
 for p in (base/'legacy-report').glob('*.html'):shutil.copyfile(p,sample/p.name)
 for name in ['summary.json','findings.jsonl','inputs.json']:shutil.copyfile(base/'legacy-report'/name,sample/name)
 result['fixture_scope']='합성 계약 검사. 실제 내규/GENOS/모델 검증 아님.'
 (P/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
 shutil.rmtree(base)
if __name__=='__main__':main()
