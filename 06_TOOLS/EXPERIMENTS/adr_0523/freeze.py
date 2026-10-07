"""Freeze explicit user Gemma override, public provenance, paired code/data and six inputs."""
from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe';P=R/'04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8388608):h.update(b)
 return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 assert not (A/'artifacts/frozen-design.json').exists()
 active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path'])
 package=read(R/'04_EXPERIMENTS/ADR/ADR-0522-scoped-reference-returns/artifacts/review-package.json')
 runtimes={'baseline':release['code_root'],'guarded':package['code_root']}
 gens={'baseline':'01_DATA/TERM/relation-subtree-main-serving-20260920-v1/generation','guarded':'01_DATA/TERM_RELEASES/adr0521-shared-reference-v1/generation'}
 grant=read(P/'artifacts/export-rebinding.json');policy=A/'artifacts/gemma-policy.json';prod=read(A/'product-cases.json')
 assert set(prod['public_scope_document_ids'])==set(grant['scope_document_ids'])
 assert sha(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json')==grant['source_authorization_sha256']
 for doc in grant['document_provenance']:
  assert sha(R/'01_DATA/RAW'/doc['raw_relative_path'])==doc['raw_sha256']
 for arm,g in gens.items():
  m=read(R/g/'manifest.json');assert m['store_sha256']==grant['source_store_sha256'] and m['generation_id']==grant['generation_id']
  assert sha(R/g/'store.sqlite')==m['store_sha256']
  nav=read(R/g/'navigation/manifest.json');assert sha(R/g/'navigation/navigation.sqlite')==nav['index_sha256']
  print('Verified data',arm,flush=True)
 grant.update(experiment_policy_path=str(policy.relative_to(R)),policy_sha256=sha(policy),basis='Explicit current user instruction: gemma로 실험. Six public regression questions and hash-verified145 public documents, no private/gold inputs. Both immutable generations share identical original store; navigation changed only.',parent_rebinding_sha256=sha(P/'artifacts/export-rebinding.json'))
 write(A/'artifacts/export-rebinding.json',grant)
 plans=[{'stage_id':'discovered','kind':'source','parent_stage_ids':[]},{'stage_id':'read','kind':'filter','parent_stage_ids':['discovered']},{'stage_id':'presented','kind':'present','parent_stage_ids':['read']}]
 text='''# Gemma paired scoped exploration probe\n\nUser authorization: gemma로 실험.\n\nSix previously hash-selected public questions from ADR0521, frozen without new result inspection. Fresh model-driven question planning, search, read, root selection, relation tools, composition and review. No historical seed pools or gold in product inputs. Two arms: selected r3 code/old DB and frozen ADR0522 rev002 review package/new ADR0521 DB. Identical Gemma4 31B DeepInfra FP8, thinking off, temperature0, 14 physical sends, 300s request wall, 6400 output tokens, three process workers. Setup included separately; outer420s watchdog records incomplete results. No automatic provider/model fallback.\n\nPrimary: decisive article recall at discovered/read/actually presented stages; distinguish protected original closure, adopted roots and cited answer. Record missing cases, errors, partial frontier, calls, tokens, cost, wall time. Direction/range contracts were tested in ADR0522; this probe does not certify legal correctness or generalization. Success requires no reference contract corruption, valid completed result and candidate delivered recall at least baseline on this fixed sample. Any miss/degraded/incomplete case is retained and diagnosed; 90/90 is not a mandatory threshold. No model judge planned; offline canonical-coordinate comparison only. No MAIN or GENOS activation.\n'''
 (A/'PLAN.md').write_text(text)
 m=read(A/'실험/manifest.json');hyp='Corrected relation DB and recursive scoped graph with model-reviewed roots can preserve necessary delivered originals without unsupported traversal.'
 m['lineage']['hypothesis_delta']=hyp;m['design'].update(hypothesis=hyp,primary_metric='Required article recall at model-delivered stage; protected originals and selected roots measured separately',success_criteria='No contract corruption or incomplete/error cases; candidate delivered recall >= paired baseline; no forced90/90',failure_criteria='Unsupported traversal, required-source regression, timeout, incomplete frontier or invalid final result; preserve all failures',criteria_frozen_before_run=True,retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{arm:plans for arm in runtimes}})
 for arm in m['design']['arms']:
  arm['changes']='Selected r3 runtime and old relation generation' if arm['id']=='baseline' else 'ADR0522 rev002 full review package and ADR0521 corrected immutable DB'
  arm['controls']='Same questions, public originals, Gemma route and call/time/output budgets; no historical retrieval seeds or gold'
  arm['derived_from']=['ADR-0522-experiment-v1/guarded'] if arm['id']=='guarded' else []
 c=R/'02_BACKEND/lawrag/research/candidates/adr_0523/transport';cm=read(c/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('run_probe.py')
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'transport','experiment_id':m['experiment_id'],'arm_id':'guarded','run_ids':['run-001'],'manifest_path':str((c/'candidate.json').relative_to(R)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}])
 override={'schema_version':'user-authorized-openrouter-product-v1','policy_path':str(policy.relative_to(R)),'policy_sha256':sha(policy)}
 m['llm_policy'].update(product_required_model='google/gemma-4-31b-it',llm_calls=[{'role':'end_to_end_product','class':'product','model':'google/gemma-4-31b-it','repeats':1}],experiment_override=override)
 m['gemma_binding']={**override,'live_calls_planned_max':168,'live_calls':0}
 m['runs'][0].update(selection_rule='Same six hash-selected ADR0521 public case IDs; fresh paired execution, alternating arm order, three workers',case_ids=[x['case_id'] for x in prod['cases']],artifact_path=str((A/'artifacts/run-001/results.json').relative_to(R)))
 m['dataset'].update(name='Six public CM/FSC regression questions from ADR0513',version='20260922-fixed-six',frozen_source=str((A/'product-cases.json').relative_to(R)),sha256=sha(A/'product-cases.json'),legal_version_checked=False,reference_version_checked=True)
 write(A/'실험/manifest.json',m)
 paths=[A/'PLAN.md',A/'product-cases.json',policy,A/'artifacts/export-rebinding.json',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/active['manifest_path'],c/'candidate.json',R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py']
 paths+=list(Path(__file__).parent.glob('*.py'));paths += [R/x['frozen_path'] for x in rev['files']]
 for arm,root in runtimes.items():paths+=sorted(p for p in (R/root).rglob('*') if p.is_file() and '__pycache__' not in str(p))
 for g in gens.values():paths += [R/g/x for x in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
 write(A/'artifacts/frozen-design.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_roots':runtimes,'generations':gens,'transport_path':rev['files'][0]['frozen_path'],'export_authorization':grant,'design':m['design'],'runs':m['runs'],'file_hashes':{str(p.relative_to(R)):sha(p) for p in paths},'grader_only_hashes':{str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')},'workers':3,'product_gold_visible':False,'model':'google/gemma-4-31b-it','max_physical_calls':168})
 print('Frozen',len(paths),'inputs; no calls',flush=True)
if __name__=='__main__':main()
