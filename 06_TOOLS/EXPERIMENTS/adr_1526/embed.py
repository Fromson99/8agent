"""ADR-1526 step 2 (no model call): BAAI/bge-m3 vectors (1024, l2-normalised; the Gold publication's model and file
hashes) for the internal articles and every external passage, in this process (not another experiment's server).

usage: embed.py [--probe N]   -> artifacts/vectors-external.npy, vectors-internal.npy, embed.json"""
from common import *
import importlib.util,time,os
import numpy as np
spec=importlib.util.spec_from_file_location('embed_server',ROOT/'06_TOOLS/EXPERIMENTS/adr_1504/embed_server.py')
es=importlib.util.module_from_spec(spec);spec.loader.exec_module(es)
expected=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1522-candidate-cm51-edge20-accuracy/artifacts/embed/profile-files.json')
model_dir=ART/'embed-model';files=es.build_model_dir(model_dir,expected)
import torch
torch.set_num_threads(int(os.environ.get('EMBED_THREADS','12')))
from sentence_transformers import SentenceTransformer
model=SentenceTransformer(str(model_dir),device='cpu',local_files_only=True)
p=read(ART/'passages.json.gz')
def encode(texts,batch=32):
    return model.encode(texts,normalize_embeddings=True,show_progress_bar=False,batch_size=batch).astype(np.float32)
if '--probe' in sys.argv:
    n=int(sys.argv[sys.argv.index('--probe')+1]);t=time.time()
    encode([e['passage'] for e in p['external'][:n]]);print('probe',n,'passages',round(time.time()-t,1),'s');sys.exit(0)
t=time.time()
internal=encode([r['heading']+'\n'+r['text'] for r in p['internal']],batch=4)
np.save(ART/'vectors-internal.npy',internal)
texts=[e['passage'] for e in p['external']];out=np.zeros((len(texts),1024),dtype=np.float32);step=512
for i in range(0,len(texts),step):
    out[i:i+step]=encode(texts[i:i+step])
    print('external',min(i+step,len(texts)),'/',len(texts),round(time.time()-t),'s',flush=True)
np.save(ART/'vectors-external.npy',out)
put(ART/'embed.json',{'model':'BAAI/bge-m3','files':files,'internal':len(internal),'external':len(texts),'seconds':round(time.time()-t,1),
    'internal_text':'heading + whole article text','external_text':'document name + heading + text, first %d chars'%p['passage_chars']})
print('done',round(time.time()-t),'s')
