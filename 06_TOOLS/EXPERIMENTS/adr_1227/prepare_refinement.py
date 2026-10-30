from common import *
import shutil
T=ROOT/'06_TOOLS/EXPERIMENTS/adr_1229';T.mkdir(exist_ok=True)
target=ROOT/'04_EXPERIMENTS/ADR/ADR-1229-source-meaning-evidence';d=target/'artifacts/design';d.mkdir(parents=True,exist_ok=True)
parent=read(DES/'freeze.json');base=read(DES/'baseline.json');m=read(target/'실험/manifest.json')
criteria={'hypothesis':'Separate source interpretation text from exact evidentiary quote for every normative part; aggregate all invalid source paths for the existing one repair. Never correct legal answers in code.',
'success':['Exact nonempty quotes for every source norm/part, complete path errors in one response','Interpretation may paraphrase; selected action/modality/condition is assembled from source-only model interpretation and its exact quote','Source-only context and nullable recorded roles, existing canonical profile/validator/store remain preserved','Re-run affected synthetic contracts and unchanged47 after fixture-only new wire representation adaptation','Same original two saved normalized records from1228 may be reused after exact validation; up to4 physical remaining calls, total<=9 across1228/followup'],
'failure':'Fabricated quote, source drift, missing role evidence, hidden retry, clause/answer hardcoding or new regression',
'external_model_calls':0,'quality_certified':False,'fixture_change':'Source plan fixtures represent each interpreted phrase as text+quote; prior expectation errors retained. No validation bypass.'}
write_summary(d/'criteria.json',criteria);write_summary(d/'baseline.json',base);write_summary(d/'parent-candidate.json',parent)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source meaning/evidence contracts and regression',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((d/'criteria.json').relative_to(ROOT)),'sha256':sha(d/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1227-experiment-v1/source-first'],'changes':'Exact1227 rev003','controls':'same canonical profile and source authority'},{'id':'meaning-evidence','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':'Same model and stage budgets'}]);m['runs'][0].update(arm_ids=['baseline','meaning-evidence'],selection_rule='All affected contracts and original domain regression',artifact_path=str((target/'artifacts/run-001/result.json').relative_to(ROOT)));m['dataset'].update(name='Synthetic interpretation/evidence source contracts',version='v1',frozen_source=str((d/'criteria.json').relative_to(ROOT)),sha256=sha(d/'criteria.json'));m['llm_policy']['llm_calls']=[];m['retrieval_accounting']['not_applicable_reason']='Authoring only';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No retrieval experiment';(target/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(target,'meaning-evidence',sorted(base['manifest']['files']),experiment_id=m['experiment_id'],arm_id='meaning-evidence',run_ids=['run-001'])
for n in parent['files']:
 p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/parent['code_root']/n,p)
 if n not in base['manifest']['files']:ac.register_file(C,n,upstream_state='absent')
for n in ('common.py','check.py','consumer.py','test_semantics.py'):
 s=(Path(__file__).parent/n).read_text().replace('ADR-1227-source-first-authoring-semantics','ADR-1229-source-meaning-evidence').replace('adr_1227/source-first','adr_1229/meaning-evidence').replace('20261029-source-first-authoring','20261030-source-meaning-evidence').replace('source-first-authoring-20261029-r1','source-meaning-evidence-20261030-r1')
 if n=='test_semantics.py':
  s=s.replace("'regulated_actions':['물건을 제출한다']","'regulated_actions':[{'text':'물건을 제출한다','quote':'물건을 제출한다'}]")
  s=s.replace("['없는 행위']","[{'text':'없는 행위','quote':'없는 행위'}]")
  s=s.replace("=['물건을','제출한다']","=[{'text':v,'quote':v} for v in ('물건을','제출한다')]")
  s=s.replace("[part]=[phrase]","[part]=[{'text':phrase,'quote':phrase}]")
 (T/n).write_text(s)
(target/'artifacts/schema-sizes.json').write_text((ART/'schema-sizes.json').read_text())
print(C/'snapshot')
