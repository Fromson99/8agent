from pathlib import Path
import json,hashlib,zipfile,io,base64,gzip,shutil
H=Path(__file__).resolve().parent;R=H.parents[3];B=H.parent/'cumulative_mail_20261015_r1';A=R/'04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search';f=json.loads((A/'artifacts/design/freeze.json').read_text());C=R/f['code_root']
sha=lambda b:hashlib.sha256(b).hexdigest()
def pack(files):
 buf=io.BytesIO()
 with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n,b in sorted(files.items()):
   assert Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
   info=zipfile.ZipInfo(n,(2026,10,15,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,b)
 return buf.getvalue()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
files={}
for folder in ('02_BACKEND/lawrag/pipeline','02_BACKEND/lawrag/core','02_BACKEND/lawrag/sources','02_BACKEND/lawrag/platform'):
 for p in (C/folder).rglob('*'):
  if p.suffix in ('.py','.yaml','.json'):files[str(p.relative_to(C))]=p.read_bytes()
for n in ['06_TOOLS/pipeline.py','06_TOOLS/COMMANDS/composed_build.py','06_TOOLS/COMMANDS/genos_data_stages.py','02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/semantic_runtime/filename_versions.py','00_SYSTEM/FILENAME_EXCEPTIONS.json','00_SYSTEM/SCHEMAS/pipeline-v1.schema.json','02_BACKEND/semantic_runtime/factorized_audit.py']:
 files[n]=((C/n) if (C/n).is_file() else (R/n)).read_bytes()
for n in ['06_TOOLS/COMMANDS/genos_data_stages.sh','06_TOOLS/COMMANDS/prepare_data.py']:
 files[n]=(R/n).read_bytes()
# Build-time registries/format engines absent from the historical lean serving checkout.
for folder in ('02_BACKEND/lawrag/agents/agent1','02_BACKEND/lawrag/agents/agent6'):
 for p in (R/folder).rglob('*'):
  if p.suffix in ('.py','.json','.yaml'):files.setdefault(str(p.relative_to(R)),p.read_bytes())
for n in ('00_SYSTEM/GLOSSARY_SCHEMA.json','00_SYSTEM/GLOSSARY_PIPELINE.json','00_SYSTEM/INTERNAL_LAYOUT.json','02_BACKEND/lawrag/agents/__init__.py'):
 if (R/n).is_file():files.setdefault(n,(R/n).read_bytes())
for p in (R/'00_SYSTEM/SCHEMAS').glob('glossary*.json'):files.setdefault(str(p.relative_to(R)),p.read_bytes())
for n in ('02_BACKEND/lawrag/core/ingest.py','02_BACKEND/lawrag/pipeline/genos_build.py'):
 files[n]=(R/n).read_bytes()
# Match the new pipeline compiler with its factorized-audit implementation; serving APIs retain field settings.
compiler_paths=['02_BACKEND/semantic_runtime/'+n+'.py' for n in ('term_index','term_links','navigation_build','navigation_storage','reference_build','factorized_audit')]
for n in compiler_paths:files[n]=((C/n) if (C/n).is_file() else (R/n)).read_bytes()
# Explicit base-byte binding for optional existing build files; unknown physical files are preserved.
allowed={n:[sha(b)] for n,b in files.items()}
for n in files:
 if (R/n).is_file():allowed[n].append(sha((R/n).read_bytes()))
for row in json.loads((H/'PIPELINE_ADAPTER.json').read_text())['files']:
 if row['path'] in allowed:allowed[row['path']].append(row['before'])
legacy=json.loads((H.parent/'latest_internal_20261015_r1/PATCH_SPEC.json').read_text())
for row in legacy['files']:
 if row['path'] in allowed:allowed[row['path']]+=[row['before'],row['after']]
policy=json.loads((C/'00_SYSTEM/PIPELINE.json').read_text())['document_build']
meta={'schema_version':'latest-selection-delivery-v1','code_root':str(C.relative_to(R)),'candidate':f['candidate'],'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in files.items()},'allowed_existing_build_hashes':allowed,'document_build':policy,'runtime_replacements':['02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/lawrag/pipeline/search_selection.py',*compiler_paths],'base_spec_sha256':sha((B/'BUNDLE_SPEC.json.gz').read_bytes())}
(H/'PAYLOAD.zip').write_bytes(pack(files));meta['payload_sha256']=sha((H/'PAYLOAD.zip').read_bytes());(H/'PAYLOAD_MANIFEST.json').write_bytes(enc(meta));(H/'FILENAME_EXCEPTIONS.json').write_bytes(files['00_SYSTEM/FILENAME_EXCEPTIONS.json'])
s=(B/'apply_patch.py').read_text().replace('GENOS_CUMULATIVE_MAIL_20261015_R1','GENOS_LATEST_SELECTION_20261015_R1').replace('TRANSFER/cumulative-mail-r1','TRANSFER/latest-selection-r1')
old="config = json.loads(payload['00_SYSTEM/PIPELINE.json'])\n    changed = set(changes)";assert old in s;s=s.replace(old,"config = json.loads(changes.get('00_SYSTEM/PIPELINE.json', payload['00_SYSTEM/PIPELINE.json']))\n    changed = set(changes)")
(H/'installer.py').write_text(s)
shutil.copyfile(B/'BUNDLE_SPEC.json.gz',H/'BASE_SPEC.json.gz')
print('Pipeline/selection source files',len(files),'payload ZIP bytes',len((H/'PAYLOAD.zip').read_bytes()))
