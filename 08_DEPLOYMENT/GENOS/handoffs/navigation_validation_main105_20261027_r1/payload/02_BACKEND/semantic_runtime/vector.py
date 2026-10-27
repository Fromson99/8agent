"""Generation-local dense index with exact source and local encoder binding."""
import hashlib
import json
from pathlib import Path
import sqlite3
import numpy as np
from .contracts import sha,write


def migrate_cache(source_store,old_vectors,old_meta,model_path,output):
    db=sqlite3.connect(Path(source_store).resolve().as_uri()+'?mode=ro',uri=True)
    units={(d,u):(p,json.loads(raw)) for d,u,p,raw in db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit')}
    texts={(d,b):t for d,b,t in db.execute('SELECT document_id,block_id,text FROM source_block')};db.close()
    meta=[json.loads(x) for x in Path(old_meta).read_text().splitlines()]
    with np.load(old_vectors,allow_pickle=False) as old:vectors=old['v']
    if len(meta)!=len(vectors):raise ValueError('vector metadata length mismatch')
    keep=[];docs=[];blocks=[];hashes=[];samples=[]
    for i,m in enumerate(meta):
        key=(m['doc_id'],str(m['node']));row=units.get(key)
        if row is None:continue
        unit=row[1];start,end=unit['span'];parts=[];size=0;cut=False
        for n in range(start,max(end,start+1)):
            text=texts.get((key[0],str(n)),'').strip()
            if text:parts.append(text);size+=len(text)
            if size>=800:cut=n+1<end;break
        body='\n'.join(parts)
        if len(body)>800:body=body[:800];cut=True
        if cut:body+='\n…(구역이 길어 여기서 잘림 — 이후 내용 있음)'
        labels=[];current=key;seen=set()
        while current in units:
            if current in seen:raise ValueError('cyclic source ancestors')
            seen.add(current);parent,u=units[current];sf=u.get('surface','').strip();title=u.get('title','').strip()
            label=f'{sf} {title}' if sf and title and sf not in title else title or sf
            if label:labels.append(label)
            current=(key[0],str(parent)) if parent is not None else None
        encoded=(' ▸ '.join(reversed(labels))+'\n'+body).strip();bid=str(unit.get('block'))
        if hashlib.sha1(encoded.encode()).hexdigest()[:16]!=m['sha1'] or (key[0],bid) not in texts:continue
        keep.append(i);docs.append(key[0]);blocks.append(bid);hashes.append(hashlib.sha256(texts[(key[0],bid)].encode()).hexdigest())
        if len(samples)<3:samples.append((len(keep)-1,encoded))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('immutable vector output exists')
    selected=vectors[keep].astype(np.float32);selected/=np.maximum(np.linalg.norm(selected,axis=1,keepdims=True),1e-12)
    model_path=Path(model_path).resolve()
    weights=sorted(list(model_path.glob('*.safetensors'))+list(model_path.glob('pytorch_model.bin')))
    if not weights:raise ValueError('local encoder weights unavailable')
    model_files={str(p.relative_to(model_path)):sha(p) for p in sorted(model_path.rglob('*')) if p.is_file() and p.suffix in {'.json','.safetensors','.bin','.model'}}
    np.savez_compressed(output,vectors=selected.astype(np.float16),document_ids=np.array(docs),block_ids=np.array(blocks),text_sha256=np.array(hashes))
    descriptor={'path':output.name,'sha256':sha(output),'model_path':str(model_path),'model_files':model_files,
                'rows':len(keep),'unmatched_rows':len(meta)-len(keep),'source_store_sha256':sha(source_store),
                'source_cache_sha256':sha(old_vectors),'source_metadata_sha256':sha(old_meta),
                'build_method':'exact legacy input hash match; migrated cache, not newly embedded full corpus',
                'encoder_samples':samples}
    write(output.with_suffix('.json'),descriptor)
    return descriptor


class Dense:
    def __init__(self,store,descriptor):
        self.store=store;self.descriptor=descriptor;self.model=None
        path=store.path/descriptor['path']
        if sha(path)!=descriptor['sha256']:raise ValueError('vector generation hash mismatch')
        with np.load(path,allow_pickle=False) as x:
            self.v=x['vectors'].astype(np.float32);self.docs=x['document_ids'];self.blocks=x['block_ids'];hashes=x['text_sha256']
        if not(len(self.v)==len(self.docs)==len(self.blocks)==len(hashes)):raise ValueError('vector index shape mismatch')
        text_hash={(d,b):hashlib.sha256(t.encode()).hexdigest() for d,b,t in store.db.execute('SELECT document_id,block_id,text FROM source_block')}
        if any(text_hash.get((str(d),str(b)))!=h for d,b,h in zip(self.docs,self.blocks,hashes)):raise ValueError('vector/source generation mismatch')
        self.v/=np.maximum(np.linalg.norm(self.v,axis=1,keepdims=True),1e-12)

    def encoder(self):
        if self.model is None:
            path=Path(self.descriptor['model_path'])
            for relative,expected in self.descriptor['model_files'].items():
                if sha(path/relative)!=expected:raise ValueError('embedding model fingerprint changed')
            import torch
            torch.set_num_threads(4)
            from sentence_transformers import SentenceTransformer
            self.model=SentenceTransformer(str(path),device='cpu',local_files_only=True)
            samples=self.descriptor.get('encoder_samples',[])
            if samples:
                fresh=self.model.encode([x[1] for x in samples],normalize_embeddings=True,show_progress_bar=False)
                cosine=np.sum(fresh*self.v[[x[0] for x in samples]],axis=1)
                if float(cosine.min())<.995:raise ValueError('migrated vector encoder mismatch')
        return self.model

    def search(self,question,allowed,limit):
        vector=self.encoder().encode([question],normalize_embeddings=True,show_progress_bar=False)[0]
        if vector.shape[0]!=self.v.shape[1]:raise ValueError('embedding dimension mismatch')
        scores=self.v@vector;indices=np.flatnonzero(np.isin(self.docs,list(allowed)))
        indices=indices[np.argsort(-scores[indices],kind='stable')[:limit]]
        return [self.store.source(str(self.docs[i]),str(self.blocks[i])) for i in indices]
