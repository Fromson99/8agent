"""R1 hotfix: bind MAIN53's omitted request-entry profile validator."""
import ast,base64,gzip,hashlib,json,subprocess,zlib
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];PRIOR=OUT.with_name('rag_focused_rules_20261013_r1')
NAME='GENOS_RAG_FOCUSED_RULES_20261013_R2'
TARGET='02_BACKEND/semantic_runtime/legal_agent/workflow_tiers_policy.py'
RELEASE=ROOT/'08_DEPLOYMENT/RELEASES/focused-rules-20261013-r1'
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda o:(json.dumps(o,ensure_ascii=False,indent=2)+'\n').encode()

def main():
 assert not (OUT/(NAME+'.zip')).exists(),'Preserve sealed delivery'
 old=(ROOT/'08_DEPLOYMENT/RELEASES/session-runtime-v6-20261007-r1/code'/TARGET).read_bytes()
 new=(RELEASE/'code'/TARGET).read_bytes();release=json.loads((RELEASE/'release.json').read_bytes())
 assert sha(new)==release['files'][TARGET]
 r1=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()));predecessors={}
 for key,state in r1['signatures'].items():predecessors.setdefault(state['output_signature'],[]).append(key)
 spec={'revision':NAME,'prior_revision':'GENOS_RAG_FOCUSED_RULES_20261013_R1','budget_policy':r1['budget_policy'],
  'predecessors':predecessors,'target':TARGET,'before_sha256':sha(old),'after_sha256':sha(new),
  'before':base64.b64encode(old).decode(),'after':base64.b64encode(new).decode(),
  'source_release':'focused-rules-20261013-r1','source_release_manifest_sha256':sha((RELEASE/'release.json').read_bytes()),
  'prior_code_zip_sha256':json.loads((PRIOR/'HANDOFF.json').read_bytes())['code_zip_sha256']}
 (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
 p=OUT/'payload'/TARGET;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(new)
 code=(OUT/'apply_patch.py').read_bytes();ast.parse(code,feature_version=(3,10));ast.parse(new,feature_version=(3,10))
 bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py=('import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+"bundle=json.loads(raw);module=types.ModuleType('focused_r2_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
 prior=(PRIOR/'GENOS_RAG_FOCUSED_RULES_20261013_R1_RUN.txt').read_text()
 run=prior[:prior.index('python3 - "$@"')].replace('rag-focused-rules-r1','rag-focused-rules-r2')+'python3 - "$@" <<\'FOCUSED_RAG_PY\'\n'+py+'FOCUSED_RAG_PY\n'
 (OUT/(NAME+'_RUN.txt')).write_text(run);subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
 (OUT/'HANDOFF.json').write_bytes(encoded({'version':NAME,'source_release':spec['source_release'],'source_release_manifest_sha256':spec['source_release_manifest_sha256'],
  'source_code_root':str(RELEASE/'code'),'required_predecessor':spec['prior_revision'],'prior_code_zip_sha256':spec['prior_code_zip_sha256'],
  'changed_implementation':[TARGET],'before_sha256':sha(old),'after_sha256':sha(new),'known_r1_output_signatures':len(predecessors),'original_input_signatures':sum(map(len,predecessors.values())),
  'run_txt_sha256':sha(run.encode()),'local_active_pointer_sha256':sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),
  'field_code_root':'~/DEV','field_git_commit':None,'field_generation':None,'field_generation_manifest_sha256':None,'field_code_serving_revision':None,
  'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT'}))
 print(json.dumps({'version':NAME,'run_bytes':len(run.encode()),'known_r1_outputs':len(predecessors),'source_policy_sha256':sha(new)}))
if __name__=='__main__':main()
