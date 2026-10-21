from pathlib import Path
import hashlib,json,zipfile
R=Path('/home/jin/8-AGENT');H=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_transfer_20261020_r1';B=R/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1';N='GENOS_IGNORE_TRANSFER_20261020_R1'
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode();sha=lambda b:hashlib.sha256(b).hexdigest()
profiles=['.gitignore','genosIgnore','genosNoJsIgnore','genosMailIgnore','08_DEPLOYMENT/GENOS/v6-runtime.genosignore','08_DEPLOYMENT/GENOS/package-v6-cumulative-r4.ignore','08_DEPLOYMENT/GENOS/ad-mode-package.ignore']
block='''# GENOS transfer/trash exclusion — 2026-10-20 R1
.Trash/
.Trash-*/
/QUERY_TRANSFER_*/
*.db.partial
*.db.partial-*
*.db-journal
*.sqlite.partial
*.sqlite.partial-*
*.sqlite3.partial
*.sqlite3.partial-*
'''
(H/'IGNORE_RULES.txt').write_text(block)
for p in profiles:
 t=H/'updated-source'/p;t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes((R/p).read_bytes())
with zipfile.ZipFile(B/'code.zip') as z:m=json.loads(z.read('CODE_MANIFEST.json'))
(H/'MAIN92_BASE_INVENTORY.json').write_bytes(enc({'base_code_zip_sha256':sha((B/'code.zip').read_bytes()),'base_id':m['id'],'files':m['files'],'required_files':m.get('required_files',[])}))
excluded=['.Trash-1001/files/BACKUP/old.py','.Trash-1001/info/deleted.trashinfo','.Trash/files/old.py','nested/.Trash-1002/files/old.py','TRANSFER/archive.zip','QUERY_TRANSFER_20261020_R1/events.jsonl','QUERY_TRANSFER_20261020_R1/export-state.json','QUERY_TRANSFER_20261020_R1/job.lock','QUERY_TRANSFER_20261020_R1/query-data.db.partial','QUERY_TRANSFER_20261020_R1/query-data.db.partial-journal','QUERY_TRANSFER_20261020_R1/source-check.json','QUERY_TRANSFER_future/query-data.db','scratch/query-data.db.partial','scratch/query-data.db.partial-journal','scratch/query-data.db-journal','scratch/query-data.sqlite.partial','scratch/query-data.sqlite.partial-wal','scratch/query-data.sqlite3.partial','scratch/query-data.sqlite3.partial-journal']
kept=['service.py','02_BACKEND/semantic_runtime/legal_agent/model_contract.py','02_BACKEND/ENGINES/legal_agent/6.0.0/answer.json','06_TOOLS/COMMANDS/code_ship.py','00_SYSTEM/PIPELINE.json','01_DATA/README.md','01_DATA/CONTRACTS/example.schema.json','01_DATA/SOURCE_SETS/example.json','.env.example']
payload=['apply_ignore.py','IGNORE_RULES.txt','MAIN92_BASE_INVENTORY.json',*['updated-source/'+p for p in profiles]]
(H/'PATCH_SPEC.json').write_bytes(enc({'id':N,'profiles':profiles,'excluded_examples':excluded,'retained_examples':kept,'payload_hashes':{p:sha((H/p).read_bytes()) for p in payload}}))
old=(B/'GENOS_MAIN92_CUMULATIVE_20261020_R1_RUN.txt').read_text()
launcher=old.replace('GENOS_MAIN92_CUMULATIVE_20261020_R1',N).replace('main92-cumulative-r1-logs','genos-ignore-r1-logs').replace('MAIN92_CUMULATIVE_EXIT','GENOS_IGNORE_EXIT').replace('run.py','apply_ignore.py').replace('PACKAGE_SPEC.json','PATCH_SPEC.json')
launcher=launcher.replace("with zipfile.ZipFile(source) as z:", "if target.exists():\n    if (target/'apply_ignore.py').is_file() and (target/'PATCH_SPEC.json').is_file():\n        raise SystemExit(0)\n    raise ValueError('Existing package folder is incomplete; preserve it and use a fresh extraction folder')\nwith zipfile.ZipFile(source) as z:")
(H/(N+'_RUN.txt')).write_text(launcher)
print('Prepared',H)
