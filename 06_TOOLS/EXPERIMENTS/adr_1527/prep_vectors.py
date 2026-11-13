"""ADR-1527 (no model call): bge-m3 vectors of every external article source of the liquidity generation, for the
experiment-only retriever of the vector arm (the local generation has no published vectors). Same model files and
passage form as ADR-1526 (document name with the rule an annex belongs to + heading + text, 250 characters).

usage: prep_vectors.py -> artifacts/vectors-external.npy, vectors-external.json"""
from common import *
import importlib.util,os,re,sqlite3,time
import numpy as np
G=ROOT/'01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation'
spec=importlib.util.spec_from_file_location('embed_server',ROOT/'06_TOOLS/EXPERIMENTS/adr_1504/embed_server.py')
es=importlib.util.module_from_spec(spec);spec.loader.exec_module(es)
expected=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1522-candidate-cm51-edge20-accuracy/artifacts/embed/profile-files.json')
model_dir=ART/'embed-model';files=es.build_model_dir(model_dir,expected)
import torch;torch.set_num_threads(12)
from sentence_transformers import SentenceTransformer
model=SentenceTransformer(str(model_dir),device='cpu',local_files_only=True)
def name(raw):
    parts=[x.strip() for x in str(raw or '').split('>') if x.strip()]
    if '별표서식' in parts and parts.index('별표서식')>0:return parts[parts.index('별표서식')-1]+' '+parts[-1]
    return parts[-1] if parts else ''
db=sqlite3.connect((G/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
store=sqlite3.connect((G/'store.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
category={d:json.loads(j).get('doc','') for d,j in store.execute('SELECT document_id,json FROM document')}
rows=[]
for sid,d,j in db.execute('SELECT id,document_id,json FROM source ORDER BY id'):
    if 'external' not in category[d]:continue
    v=json.loads(j)
    rows.append({'id':sid,'document_id':d,'passage':(name(v.get('document_name'))+' '+v.get('heading','')+'\n'+re.sub(r'\s+',' ',v.get('text','')))[:250]})
t=time.time()
vec=model.encode([r['passage'] for r in rows],normalize_embeddings=True,show_progress_bar=False,batch_size=32).astype(np.float32)
np.save(ART/'vectors-external.npy',vec)
put(ART/'vectors-external.json',{'model':'BAAI/bge-m3','files':files,'generation':str(G.relative_to(ROOT)),'count':len(rows),
    'ids':[r['id'] for r in rows],'documents':[r['document_id'] for r in rows],'seconds':round(time.time()-t,1),
    'passage':'document name (annex: with its rule) + heading + text, 250 characters'})
print('vectors',len(rows),round(time.time()-t,1),'s')
