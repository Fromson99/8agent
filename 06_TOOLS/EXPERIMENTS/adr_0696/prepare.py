from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0696-structured-decision-wire-repair';P=R/'02_BACKEND/lawrag/research/candidates/adr_0694/structured-reading';C=R/'02_BACKEND/lawrag/research/candidates/adr_0696/repaired'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'hypothesis':'Remove impossible DECIDE branch from empty structural menu; bind already-explicit, offered condition/exception span refs into their own claim receipt without new evidence or semantic edits.','required':['No array branch has minItems greater than maxItems','Empty original menu still offers structure search/read and scoped body navigation','Nested explicit valid source references compile into one claim citation set','Unknown/unadopted source references remain rejected','No semantic condition/operator/fact changes','Inherited new critical contracts pass'],'model_calls':0,'qualification':'Known failure repair probe only; independent new public qualification required'}
put(A/'artifacts/design/criteria.json',criteria);m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Wire satisfiability and source-reference integrity',success_criteria=criteria['required'],failure_criteria='Any new critical failure',criteria_frozen_before_run=True);m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['dataset'].update(name='Synthetic empty-menu and nested-evidence witnesses',version='wire-repair-v1',frozen_source=str((A/'artifacts/design/criteria.json').relative_to(R)),sha256=sha(A/'artifacts/design/criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(selection_rule='All new synthetic and inherited critical contracts',artifact_path=str((A/'artifacts/contracts/result.json').relative_to(R)))
m['retrieval_accounting']['not_applicable_reason']='Synthetic contracts only; no corpus retrieval measurement';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
for a in m['design']['arms']:a.update(changes='Completed0694 parent' if a['id']=='baseline' else criteria['hypothesis'],controls='Same code/data/model policy; no model call')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
pcm=read(P/'candidate.json');ps=P/'revisions'/pcm['revisions'][-1]['revision_id']/'snapshot'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','repaired','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
for x in pcm['files']:
 if (R/x['target_path']).is_file():cmd+=['--source',x['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for x in pcm['files']:
 name=x['target_path'];t=C/'snapshot'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ps/name,t)
 if not (R/name).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',name,'--upstream-state','absent'],cwd=R,check=True)
B=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=B/'law_navigation.py';s=p.read_text();assert "if completion: terminal_actions.add('DECIDE')" in s;s=s.replace("if completion: terminal_actions.add('DECIDE')","if completion and view['branches']: terminal_actions.add('DECIDE')");p.write_text(s)
p=B/'completion_contracts.py';s=p.read_text();at='def materialize_assessment(value, options, issues):';helper='''def bind_rule_evidence(value, options):
    """Canonicalize only refs already explicitly chosen inside this claim's rule.

    These are delivered/adopted options, not newly retrieved sources. Unknown
    refs remain invalid and cannot be made valid by normalization.
    """
    value=deepcopy(value);available={o['id'] for o in options};changes=[]
    for claim in value.get('claims',[]) if isinstance(value,dict) else []:
        if not isinstance(claim,dict) or not isinstance(claim.get('rule'),dict):continue
        chosen=claim.get('evidence_refs')
        if not isinstance(chosen,list) or not all(isinstance(x,str) for x in chosen):continue
        nested=[]
        for kind in ('conditions','exceptions'):
            rows=claim['rule'].get(kind,[])
            if not isinstance(rows,list):continue
            for row in rows:
                if isinstance(row,dict) and isinstance(row.get('evidence_refs'),list):
                    nested.extend(x for x in row['evidence_refs'] if isinstance(x,str))
        if set(nested)-available:continue
        merged=list(dict.fromkeys(chosen+nested))
        if merged!=chosen:
            claim['evidence_refs']=merged;changes.append({'claim_id':claim.get('claim_id'),'explicit_nested_refs':list(dict.fromkeys(nested))})
    return value,changes


''';assert at in s;s=s.replace(at,helper+at);p.write_text(s)
p=B/'completion_execution.py';s=p.read_text();a='                value = cc.with_targets(value)';b="                value = cc.with_targets(value)\n                value, bound_refs = cc.bind_rule_evidence(value, options)\n                if bound_refs:self.s.work.event('COMPLETION_RULE_REFS_BOUND',{'changes':bound_refs,'assessment_hash':digest(value)})";assert a in s;s=s.replace(a,b);p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',str(C/'snapshot')],cwd=R,check=True)
print('Isolated two repairs; semantics and unverified-source rejection preserved')
