"""Read-only admitted RAW -> selected structure provenance projection builder.

Caller explicitly selects RAW and structure package roots. Files are never moved.
Legacy document identity is the first 16 chars of RAW SHA-256, verified again here;
the full source structure artifact hash must also match the selected database.
"""
from pathlib import Path
from collections import defaultdict
import hashlib,json,sqlite3
from runtime import sha

def build(store,raw_root,structure_roots):
 raw_root=Path(raw_root).resolve(strict=True);origins=defaultdict(list);receipts={};selected={r['document_id']:dict(r) for r in store.db.execute('SELECT document_id,source_artifact_sha256 FROM document')}
 # Existing metadata manifests select candidate files; no title-based origin join.
 candidates=set()
 for directory in sorted(raw_root.iterdir()):
  if not directory.is_dir() or directory.is_symlink():continue
  if directory.name=='internal':
   candidates.update(p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in ('.pdf','.hwp','.hwpx','.docx','.html','.xml','.txt'))
   continue
  manifest=directory/'manifest.json'
  if not manifest.is_file():continue
  value=json.loads(manifest.read_text());receipts[str(manifest)]=sha(manifest)
  def walk(x):
   if isinstance(x,list):
    for v in x:walk(v)
   elif isinstance(x,dict):
    for k,v in x.items():
     if isinstance(v,str) and (k=='file' or k.endswith('_file') or k in ('path','raw_path')):
      # Accept only paths under this explicitly selected RAW provider.
      p=Path(v)
      if not p.is_absolute():
       if '..' in p.parts:continue
       p=directory/p
      try:p.resolve().relative_to(directory.resolve())
      except ValueError:continue
      if p.is_file() and not any(a.is_symlink() for a in [p,*p.parents]):candidates.add(p)
     else:walk(v)
  walk(value.get('items',value))
 for p in sorted(candidates):
  if any(a.is_symlink() for a in [p,*p.parents]):continue
  full=sha(p);did=full[:16]
  if did not in selected:continue
  origins[did].append({'raw_relative_path':p.relative_to(raw_root).as_posix(),'raw_sha256':full})
 docs={}
 for did,row in selected.items():
  checked=[]
  for root in structure_roots:
   root=Path(root).resolve(strict=True);result=root/did/'result.json';meta=root/did/'meta.json'
   if result.is_file() and meta.is_file() and sha(result)==row['source_artifact_sha256']:
    info=json.loads(meta.read_text())
    if str(info.get('doc_id'))==did:checked.append({'structure_result':str(result),'sha256':row['source_artifact_sha256'],'metadata_sha256':sha(meta)})
  paths=origins.get(did,[])
  if len(paths)==1 and checked:
   docs[did]={'status':'verified','document_id':did,**paths[0],'source_artifact_sha256':row['source_artifact_sha256'],'structure_receipt':checked[0],'identity_contract':'RAW sha256 prefix16 document ID + exact selected structure artifact hash'}
  elif len(paths)>1:docs[did]={'status':'ambiguous','document_id':did,'reason':'same raw identity has multiple folder locations','locations':paths}
 return {'schema_version':'folder-origin-projection-v1',**{k:store.manifest[k] for k in ('generation_id','store_sha256')},'raw_root':str(raw_root),'documents':docs,'input_manifest_hashes':receipts,'selected_document_count':len(selected),'verified_document_count':sum(x['status']=='verified' for x in docs.values()),'unknown_document_count':len(selected)-sum(x['status']=='verified' for x in docs.values()),'source_unchanged':True,'external_transmission':False}
