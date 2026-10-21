from pathlib import Path
import ast,hashlib,json,shutil,subprocess,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261020-basis-entry-fix';STAGE=AUDIT/'validation-code'
BASE=HERE.with_name('basis_batch_20261020_r4')
NAME='GENOS_BASIS_ENTRY_FIX_20261020_R1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (HERE/'SEALED.json').exists()
prior=json.loads((BASE/'PACKAGE.json').read_text())
code={n:sha(STAGE/n) for n in prior['code']}
patch=[n for n in code if code[n]!=prior['code'][n]]
assert '02_BACKEND/semantic_runtime/app.py' in patch
for n in patch:
    p=HERE/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(STAGE/n,p)
runner=(BASE/'runner.py').read_text().replace('pilot-review-skip-20261020-r4','pilot-review-entryfix-20261020-r1')
runner=runner.replace("'list','plan','run','resume','status','report','export']", "'list','plan','run','resume','status','report','export','release-gate']")
runner=runner.replace("elif args.command == 'gate':gate(root, spec)", """elif args.command == 'gate':gate(root, spec)
        elif args.command == 'release-gate':
            gate(root,spec)
            config=json.loads(plain(root/CONFIG).read_text())
            print(json.dumps({'event':'DEPLOYMENT_BINDING','root':str(root),
                'generation':config['generation'],'runtime':config['runtime'],
                'generation_manifest_sha256':sha(Path(config['generation'])/'manifest.json'),
                'code_zip_sha256':sha(HERE/'code.zip'),'serving_revision':'NOT_VERIFIED'},ensure_ascii=False),flush=True)
            return subprocess.call([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),
                '--code-zip',str(HERE/'code.zip'),'--deploy-root',str(root),
                '--generation',config['generation']],cwd=root)""")
(HERE/'runner.py').write_text(runner)
run=(BASE/'GENOS_BASIS_BATCH_20261020_R4_RUN.txt').read_text().replace('GENOS_BASIS_BATCH_20261020_R4',NAME).replace('basis-batch-r4-logs','basis-entry-fix-r1-logs')
(HERE/(NAME+'_RUN.txt')).write_text(run)
tools=HERE/'tools';tools.mkdir(exist_ok=True)
names=['runner.py','basis_batch_artifacts.py','basis_batch_report.py','basis_batch_candidates.py','basis_batch.py']
for n in names:shutil.copyfile(BASE/'tools'/n,tools/n)
put(tools/'CODE_REQUIREMENTS.json',{'schema_version':'basis-artifacts-code-v1','baseline':NAME,
    'checkout':code,'tool':{n:sha(tools/n) for n in names}})
manifest={'format':'8agent-code/1','files':[{'path':n,'sha256':code[n],'bytes':(STAGE/n).stat().st_size} for n in patch],
    'required_files':[{'path':n,'sha256':h} for n,h in code.items() if n not in patch]}
put(HERE/'CODE_MANIFEST.json',manifest)
with zipfile.ZipFile(HERE/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    z.write(HERE/'CODE_MANIFEST.json','CODE_MANIFEST.json')
    for n in patch:z.write(STAGE/n,n)
(HERE/'COMMIT_PATHS.txt').write_text('\n'.join(patch)+'\n')
files=['runner.py',NAME+'_RUN.txt','GUIDE_UTF8.txt','CODE_MANIFEST.json','COMMIT_PATHS.txt','code.zip']
if (HERE/'VALIDATION.json').exists():files+=['VALIDATION.json']
files += ['tools/'+n for n in names+['CODE_REQUIREMENTS.json']]+['payload/'+n for n in patch]
for n in files:
    if n.endswith('.py'):ast.parse((HERE/n).read_bytes(),filename=n,feature_version=(3,11))
subprocess.run(['bash','-n',str(HERE/(NAME+'_RUN.txt'))],check=True)
spec={'version':NAME,'supersedes':prior['version'],'prior_package_sha256':sha(BASE/'PACKAGE.json'),
    'code':code,'patch':patch,'allowed_before':{n:list(dict.fromkeys([prior['code'][n],h])) for n,h in code.items()},
    'payload':{n:sha(HERE/n) for n in files},
    'correction':'Route comparisons before native basis identity; preserve prepared team/session and document scope',
    'relationship_sqlite_changed':False,'local_MAIN_changed':False,'GENOS_field_verified':False}
put(HERE/'PACKAGE.json',spec)
files+=['PACKAGE.json']
with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n in sorted(files):
        assert Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
        z.write(HERE/n,n)
put(HERE/'BUILD.json',{'zip_sha256':sha(HERE/(NAME+'.zip')),'bytes':(HERE/(NAME+'.zip')).stat().st_size,
    'functional_files':['02_BACKEND/semantic_runtime/app.py'],'patch_files':len(patch),'checkout_files':len(code),
    'source_root':str(STAGE),'javascript_files':0})
print((HERE/'BUILD.json').read_text())
