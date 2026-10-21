from common import *
import importlib.util,sqlite3,tempfile,unittest
candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0971/dense-rerank/snapshot'/TARGET
spec=importlib.util.spec_from_file_location('probe',candidate);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Tokenizer:
 def __call__(self,text,**kwargs):return {'input_ids':list(range(len(text)+2))}
class Contracts(unittest.TestCase):
 def test_long_unicode_tail_coverage_and_token_budget(self):
  text='가나다 abc\n'*500+'마지막 예외';seen=set()
  for a,b in p.split_text(text,'문서\n',lambda s:len(s)+2,max_tokens=127):
   self.assertLessEqual(len('문서\n'+text[a:b])+2,127);seen.update(range(a,b))
  self.assertEqual(seen,set(range(len(text))))
 def test_oversized_prefix_fails(self):
  with self.assertRaises(ValueError):list(p.split_text('body','x'*600,len))
 def test_compound_coordinate_uses_true_article(self):
  root={'id':1,'family':'kr_article','legal_coordinate':{'unit':'조','chain':[]},'parent':None}
  child={'id':2,'family':'kr_item','legal_coordinate':{'unit':'조','chain':[{'unit':'항'}]},'parent':1}
  self.assertEqual(p.article_root(child,{'1':root,'2':child}),1)
 def test_shard_resume_and_stale_hash(self):
  import numpy as np
  with tempfile.TemporaryDirectory() as d:
   v=np.zeros((2,1024),dtype='float32');v[:,0]=1
   self.assertFalse(p.check_shard(d,0,2,'a'));p.save_shard(d,0,v,'a');self.assertTrue(p.check_shard(d,0,2,'a'))
   with self.assertRaises(ValueError):p.check_shard(d,0,2,'b')
   with self.assertRaises(ValueError):p.save_shard(d,0,v,'a')
 def test_uncommitted_shard_is_not_success(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'00000000.npy').write_bytes(b'partial')
   with self.assertRaises(ValueError):p.check_shard(d,0,2,'a')
 def test_invalid_vector_rejected(self):
  import numpy as np
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):p.save_shard(d,0,np.zeros((1,1024)),'a')
 def fixture(self,path):
  db=sqlite3.connect(path);db.executescript('CREATE TABLE document(document_id,name,source_artifact_sha256); CREATE TABLE source_unit(document_id,unit_id,parent_id,json); CREATE TABLE source_block(document_id,block_id,unit_id,text,source_artifact_sha256);')
  db.execute('INSERT INTO document VALUES (?,?,?)',('doc','문서','h'))
  db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',('doc','1',None,json.dumps({'id':1,'family':'kr_article','parent':None,'span':[0,2],'coordinate_key':'body:제1조','surface':'제1조'})))
  db.executemany('INSERT INTO source_block VALUES (?,?,?,?,?)',[('doc','0','1','본문'*800+'끝예외','h'),('doc','1','1','', 'h'),('doc','2',None,'표제 미배정 원문','h')]);db.commit();db.close()
 def test_full_source_coverage_orphan_empty_tail_and_reader(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'src.sqlite';out=Path(d)/'corpus.sqlite';self.fixture(src)
   stats=p.build(src,{'doc'},out,Tokenizer(),{'prefix_characters':100,'max_characters':800,'max_embedding_tokens':512,'overlap_characters':100})
   proof=p.verify_corpus(src,{'doc'},out);self.assertEqual(proof['source_blocks'],3);self.assertEqual(proof['coverage'],1)
   db=p.connect(out);groups=[json.loads(r[0]) for r in db.execute('SELECT json FROM groups')];db.close()
   ctx=p.context(src,groups,{'doc'});self.assertIn('끝예외',ctx['sources'][0]['text']);self.assertEqual(len(ctx['sources']),2)
   with self.assertRaises(ValueError):p.context(src,groups,set())
   db=sqlite3.connect(out);db.execute('DELETE FROM chunks WHERE id=(SELECT max(id) FROM chunks WHERE node=1)');db.commit();db.close()
   with self.assertRaises(ValueError):p.verify_corpus(src,{'doc'},out)
 def test_original_change_detected(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'src.sqlite';out=Path(d)/'corpus.sqlite';self.fixture(src)
   p.build(src,{'doc'},out,Tokenizer(),{'prefix_characters':100,'max_characters':800,'max_embedding_tokens':512,'overlap_characters':100})
   db=sqlite3.connect(src);db.execute("UPDATE source_block SET text='변경' WHERE block_id='0'");db.commit();db.close()
   with self.assertRaises(ValueError):p.verify_corpus(src,{'doc'},out)
if __name__=='__main__':unittest.main()
