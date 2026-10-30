from common import *
import shutil,sys,subprocess
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(pointer);release_path=ROOT/active['manifest_path'];release=read(release_path);B=ROOT/release['code_root']
assert active['generation']==107 and all(sha(B/n)==h for n,h in release['files'].items())
oldf=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/artifacts/freeze.json');OLD=ROOT/oldf['arms']['ontology']['code_root']
criteria={'hypothesis':'Source-bound measurement, calculation, condition and effect dependency plans distilled from actual agent judgments expose meaning omitted by flat A1 bundles; same sources and fixed landing isolate downstream differences.',
 'primary':['schema/anchor/quote/judgment/dependency integrity','model-built semantic plan consumed by current ASSESS','source-exact distinction of threshold exclusion versus refund, presumption versus deeming, and gain calculation inputs in final answer'],
 'success':'All contract tests pass; generated proposal structurally valid or bounded failure preserved; same source evidence delivered to both arms; candidate retains all three predeclared semantic distinctions with no unsupported rule addition. If extraction fails, no fabricated fallback graph.',
 'arms':{'baseline':'MAIN107 +1105 A1 originals and relations','semantic':'identical A1 plus source-bound typed dependency plan; final answer schema and prompts otherwise unchanged'},
 'build':'One Qwen3.8 proposal from saved CM023 agent claims and corresponding original spans; up to one structural repair with explicit errors only. No gold, previous final prose, evaluator critique or handcrafted legal rules. Runtime treats output as experiment proposal, not human-approved law.',
 'sample':'Previously exposed authorized CM023 only; in_sample=true decision_eligible=false',
 'run':'run-001: build then baseline then semantic; first two stored request-entry/READ responses replayed through native gateway in both arms, new model calls from ASSESS onward. No cell reruns. Before each answer call verify hashes and exact evidence equivalence at first ASSESS; abort affected arm on mismatch.',
 'scope':'Small MVP: explicit node roles, concept/type/unit/scope, calculation input edges, condition/effect targets, exact quotes, source/judgment bindings, topological composition, unknowns. No automatic legal applicability or general numeric execution; result changes are described, not certified.',
 'limits':{'build_calls':2,'answer_calls_per_arm':40,'max_output_tokens':None,'wall_seconds_per_arm':1800,'tools_per_arm':1024,'heavy_processes':1,'max_rss_gib':4,'min_available_gib':3,'min_disk_gib':20,'max_swap_used_gib':1},
 'failure_contract':{'structure':'one build repair only; failure preserves raw output and blocks semantic arm','integrity':'hash, unknown refs, invalid quote, cross-scope dependency or cycle raises ContractError; no semantic repair/guessing','uncertainty':'explicit unresolved and review-required, never false/zero; existing MAIN gaps and reentry remain','proposal':'no operational approval or SQL load; hashed experimental artifact only'},
 'evaluation':'Frozen source-based rubric applied offline to both answers; exact citations, 3 semantic dimensions, paired outcomes; no new evaluator model, no legal certification. Single pair, fixed order, partial replay not full fresh E2E or timing causal proof.'}
put(ART/'criteria.json',criteria);put(ART/'baseline.json',{'pointer':active,'pointer_sha256':sha(pointer),'release':release,'release_manifest_path':str(release_path.relative_to(ROOT)),'release_manifest_sha256':sha(release_path)})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria=criteria['success'],failure_criteria='Any integrity violation or failure to retain the specified distinctions; no automatic quality certification',criteria_frozen_before_run=True)
m['integration'].update(result_arm='semantic',rationale=criteria['hypothesis'],common_invariants=['MAIN107 source/schema/SQL/model/profile preserved','ontology only; no active release mutation'],no_conflict_reason='MAIN107 changes no files used for the four 1105 ontology integration hunks; exact comparison asserted by prepare.py',conflicts=[])
for p in m['integration']['parent_contributions']:
 p.update(adopted='Whole selected MAIN107 serving code' if '1111' in p['parent_ref'] else 'Four ontology hooks, five modules, schema and test support',excluded='None' if '1111' in p['parent_ref'] else 'MAIN106 release selection and historical product responses except explicitly frozen two-response landing control')
for a in m['design']['arms']:a.update(changes=criteria['arms'][a['id']],controls='Same code, corpus, original bundle, 2-response landing replay, provider, output schema and budget; semantic overlay only differs')
m['runs'][0].update(selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
# Snapshot first, then transplant only the verified ontology differences.
C=ac.snapshot(ADR,'semantic-r1',list(release['files']),experiment_id=m['experiment_id'],arm_id='semantic',run_ids=['run-001']);S=C/'snapshot'
for n in release['files']:shutil.copyfile(B/n,S/n)
comp=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/artifacts/composition.json')
BASE106=ROOT/'08_DEPLOYMENT/RELEASES/compact-input-20261027-r1/code'
for n in comp['changed_product']:
 assert sha(B/n)==sha(BASE106/n),n
 shutil.copyfile(OLD/n,S/n)
known=set(release['files'])
for n in oldf['arms']['ontology']['files']:
 if n not in known:
  p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/n,p)
  ac.register_file(C,n,upstream_state='present' if (ROOT/n).exists() else 'absent');known.add(n)
put(ART/'composition.json',{'base':'MAIN107','base_files':len(release['files']),'changed_product':comp['changed_product'],'added_product':comp['added_product'],'support_reused_from':'ADR1105 frozen snapshot','scope':'same candidate code for both arms; semantic graph injection only candidate arm'})
print(S)
