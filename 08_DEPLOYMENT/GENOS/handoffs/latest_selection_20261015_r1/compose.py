"""Compose only known complete field states with sealed latest-selection code."""
import base64,gzip,json,zipfile
from pathlib import Path
import installer as ins
import base_installer as base
H=Path(__file__).resolve().parent

def resources():
 m=json.loads((H/'PAYLOAD_MANIFEST.json').read_text());raw=(H/'PAYLOAD.zip').read_bytes()
 if ins.sha(raw)!=m['payload_sha256']:raise ValueError('pipeline payload changed')
 with zipfile.ZipFile(H/'PAYLOAD.zip') as z:
  if set(z.namelist())!=set(m['files']):raise ValueError('payload inventory mismatch')
  files={n:z.read(n) for n in z.namelist()}
 for n,b in files.items():
  if ins.sha(b)!=m['files'][n]['sha256']:raise ValueError('payload file changed: '+n)
 raw=(H/'BASE_SPEC.json.gz').read_bytes()
 if ins.sha(raw)!=m['base_spec_sha256']:raise ValueError('base patch spec changed')
 value=json.loads(gzip.decompress(raw))
 if 'patch_records' in value:
  records=value.pop('patch_records')
  for state in value['signatures'].values():state['patches']={records[i][0]:{'before_sha256':records[i][1],'after_sha256':records[i][2]} for i in state.pop('patch_refs')}
 return m,files,value

def repin(payload,updates,additions):
 final={**payload,**updates};config=json.loads(final['00_SYSTEM/PIPELINE.json'])
 for entry in config['engines'].values():
  n=entry['manifest'];engine=json.loads(payload[n])
  for name in set(engine['files'])&set(updates):engine['files'][name]=ins.sha(final[name])
  for name in additions.get(n,[]):engine['files'][name]=ins.sha(final[name])
  final[n]=ins.encoded(engine);entry['sha256']=ins.sha(final[n])
 for entry in config['contracts'].values():
  if entry['schema_path'] in updates:entry['schema_sha256']=ins.sha(final[entry['schema_path']])
 final['00_SYSTEM/PIPELINE.json']=ins.encoded(config)
 return final

def compose(root):
 m,source,spec=resources();manifest=json.loads((root/'CODE_MANIFEST.json').read_text());original=ins.inventory(root,manifest)
 ins.verify_bindings(original)
 if manifest.get('cumulative_mail',{}).get('revision')==base.VERSION:
  state=spec['signatures'].get(manifest['cumulative_mail'].get('input_signature'))
  if state is None or ins.signature(original,manifest,spec)!=state['output_signature']:raise ValueError('cumulative inventory differs')
  candidate=dict(original)
 else:
  _,_,changes,_,_=base.prepared(root,spec);candidate={**original,**{n:b for n,b in changes.items() if n!='CODE_MANIFEST.json'}}
 updates={}
 for n,b in source.items():
  old=candidate.get(n)
  if n in m['runtime_replacements'] or n in ('00_SYSTEM/FILENAME_EXCEPTIONS.json','00_SYSTEM/SCHEMAS/pipeline-v1.schema.json'):
   updates[n]=b
  elif old is None:updates[n]=b
  elif n in ('02_BACKEND/lawrag/pipeline/document_representations.py','02_BACKEND/lawrag/pipeline/genos_build.py','02_BACKEND/lawrag/pipeline/team_raw.py','02_BACKEND/lawrag/pipeline/genos_corpus.py','02_BACKEND/lawrag/pipeline/genos_stages.py','06_TOOLS/COMMANDS/composed_build.py','06_TOOLS/COMMANDS/genos_data_stages.py'):
   if ins.sha(old) not in m['allowed_existing_build_hashes'][n]:raise ValueError('unknown existing build code: '+n)
   updates[n]=b
  # Existing field dependencies stay on their verified field implementation.
 for n,needle in [('02_BACKEND/semantic_runtime/app.py','contracts=Contracts(contracts_root)'),('02_BACKEND/semantic_runtime/pipeline.py','self.store=store;self.contracts=Contracts(root);self.provider=provider')]:
  text=candidate[n].decode()
  if text.count(needle)!=1:raise ValueError('unknown latest gate insertion: '+n)
  text=text.replace(needle,needle+'\n        store.selection.require_latest()',1)
  updates[n]=text.encode()
 config=json.loads(candidate['00_SYSTEM/PIPELINE.json']);config['document_build']=m['document_build'];updates['00_SYSTEM/PIPELINE.json']=ins.encoded(config)
 adds={n:list(v) for n,v in spec['engine_additions'].items()}
 for entry in config['engines'].values():
  n=entry['manifest'];engine=json.loads(candidate[n])
  if '02_BACKEND/semantic_runtime/storage.py' in engine['files']:
   for path in ('02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/semantic_runtime/filename_versions.py','00_SYSTEM/FILENAME_EXCEPTIONS.json'):
    if path not in adds.setdefault(n,[]):adds[n].append(path)
 combined={n:b for n,b in {**candidate,**updates}.items() if b!=original.get(n)}
 final=repin(original,combined,adds);ins.verify_bindings(final)
 # Only verified normalized budget overlays are allowed to vary by site.
 effective={'revision':ins.VERSION,'budget_policy':spec['budget_policy'],'unrecorded_schema_preimages':spec['unrecorded_schema_preimages'],'engine_additions':adds,'signatures':{},'blobs':{}}
 key=ins.signature(original,manifest,effective);out=ins.signature(final,manifest,effective);patches={}
 for n,b in final.items():
  if b==original.get(n) or n.startswith('02_BACKEND/ENGINES/'):continue
  before=original.get(n)
  if n=='service.py' and manifest.get('investigation_budget_settings'):
   b=ins.budget_transform(b,effective,restore=False);before=ins.budget_transform(before,effective,restore=False)
  h=ins.sha(b);patches[n]={'before_sha256':ins.sha(before) if before is not None else None,'after_sha256':h};effective['blobs'][h]=base64.b64encode(b).decode()
 effective['signatures'][key]={'label':'verified cumulative predecessor plus exact latest policy','output_signature':out,'patches':patches}
 # Validate missing physical files before apply, including modules outside the old lean manifest.
 for n in patches:
  if n not in original and ins.path_at(root,n).exists():
   b=ins.path_at(root,n).read_bytes();h=ins.sha(b)
   if n not in source or h not in m['allowed_existing_build_hashes'][n]:raise ValueError('unrecorded existing file differs: '+n)
   effective['unrecorded_schema_preimages'].setdefault(n,{})[h]={'bytes':len(b),'evidence':'exact recorded source or final pipeline bytes'}
 ins.prepared(root,effective)
 return effective,final
