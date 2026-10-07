import copy,hashlib,json,sys
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'02_BACKEND'))
import semantic_runtime
semantic_runtime.__path__.insert(0,str(R/'02_BACKEND/lawrag/research/candidates/adr_0652/integrated/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime'))
from semantic_runtime.release_qualification import verify
from semantic_runtime.release_integration import check
sys.path.insert(0,str(R/'05_TESTS/CONTRACTS'))
from test_release_integration import workspace,candidate,declaration,digest

def put(root,p,v):
 f=root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(v) if not isinstance(v,str) else v)
 return {'path':p,'sha256':digest(f.read_bytes())}

def qualified(root):
 rebase=put(root,'rebase.json',{})
 result=put(root,'ADR/artifacts/result.json',{'strict_success':True,'checks':{'quality':True,'contracts':True}})
 m={'in_sample':False,'decision_eligible':True,'reservation':{'status':'completed'},'results':{'status':'complete','by_arm':{'chosen':{'status':'complete'}}},'runs':[{'status':'complete','artifact_path':result['path'],'sha256':result['sha256'],'arm_ids':['chosen']}],'design':{'release_rebase':rebase}}
 source=put(root,'ADR/실험/manifest.json',m);readme=put(root,'ADR/README.md','---\nstatus: Accepted\nmain_wiring: promotion-candidate\n---\n')
 auth={'quality_gate_override':False,'qualification':{'source':source,'readme':readme,'arm':'chosen','result':result,'rebase':rebase}};report={'structural_checks_passed':True,'integration':{'rebase_receipt':rebase}}
 return auth,report,m

def test_qualified_source(tmp_path):
 a,r,m=qualified(tmp_path);assert verify(tmp_path,a,r)==a['qualification']

@pytest.mark.parametrize('field,value',[('in_sample',True),('decision_eligible',False),('reservation',{'status':'in_progress'}),('results',{'status':'complete','by_arm':{'chosen':{'status':'planned'}}})])
def test_refuses_unqualified_source(tmp_path,field,value):
 a,r,m=qualified(tmp_path);m[field]=value;a['qualification']['source']=put(tmp_path,'ADR/실험/manifest.json',m)
 with pytest.raises(ValueError):verify(tmp_path,a,r)

@pytest.mark.parametrize('drift',['source','readme','result','rebase'])
def test_refuses_changed_qualified_artifact(tmp_path,drift):
 a,r,m=qualified(tmp_path);p=tmp_path/a['qualification'][drift]['path'];p.write_text(p.read_text()+'\n')
 with pytest.raises(ValueError,match='drift'):verify(tmp_path,a,r)

def test_no_waiver_or_failed_check(tmp_path):
 a,r,m=qualified(tmp_path);a['quality_gate_override']=True
 with pytest.raises(ValueError,match='waiver'):verify(tmp_path,a,r)
 a['quality_gate_override']=False;r['structural_checks_passed']=False
 with pytest.raises(ValueError):verify(tmp_path,a,r)

def test_explicit_rebase_binds_baseline_candidate_and_every_stage_file(tmp_path):
 root,b,before=workspace(tmp_path);after={**before,'rag.py':digest('candidate rag')};c=candidate(root,digest('working tree differs from active'))
 d=declaration(root,b,after,c)
 receipt={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':c,'staged_files':after,'excluded_candidate_paths':{}}
 d['rebase_receipt']=put(root,'rebase.json',receipt)
 assert check(root,b,after,d)['changed_files']==1
 bad={**after,'scope.py':digest('undeclared new scope')}
 d2=declaration(root,b,bad,c);d2['rebase_receipt']=d['rebase_receipt']
 with pytest.raises(ValueError,match='exact stage'):check(root,b,bad,d2)
 receipt['staged_files']=bad;d2['rebase_receipt']=put(root,'rebase.json',receipt)
 with pytest.raises(ValueError,match='outside frozen candidate'):check(root,b,bad,d2)
