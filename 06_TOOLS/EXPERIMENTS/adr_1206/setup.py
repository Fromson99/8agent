from common import *
import sqlite3
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.ontology_compiler import content_hash
from semantic_runtime.ontology_work.profile import compile_profile
m=read(ADR/'실험/manifest.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);data=ROOT/release['data_path'];generation=read(data/'manifest.json')
put(DES/'baseline.json',{'active':active,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release_sha256':sha(ROOT/active['manifest_path']),'data_path':release['data_path'],'generation_manifest_sha256':sha(data/'manifest.json'),'data_binding':generation,'authorization_path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json')})
items=[]
for ident,old,n,pointer in [('saved-007-a','1198-main117-live-cm007','006','/claims/0/rule/condition_tree'),('saved-007-b','1200-supervisor-recovery-live-cm007','009','/claims/2/rule/norms/0')]:
 path=ROOT/f'04_EXPERIMENTS/ADR/ADR-{old}/artifacts/live/cm-007/canonical/{n}-output.json.gz';whole=read(path);payload=whole
 for key in pointer.strip('/').split('/'):payload=payload[int(key)] if isinstance(payload,list) else payload[key]
 items.append({'id':ident,'origin':{'path':str(path.relative_to(ROOT)),'sha256':sha(path),'pointer':pointer},'payload':payload,
  'labels':['상장주선인','상장예비심사','사모'],'original_ids':['S1'] if ident.endswith('a') else ['S1','S2','S3','S4','S5']})
raw(DES/'cases.json',items)
originals=[]
with sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 for ident,doc,unit,label in [('S1','3521c3aaa5a735fd','180','코스닥시장 상장규정 제13조제5항 본문'),('S2','eae25aa6e8a83c58','86','코스닥시장 상장규정 시행세칙 제15조제4항 본문'),('S3','eae25aa6e8a83c58','87','코스닥시장 상장규정 시행세칙 제15조제4항제1호'),('S4','eae25aa6e8a83c58','88','코스닥시장 상장규정 시행세칙 제15조제4항제2호'),('S5','eae25aa6e8a83c58','89','코스닥시장 상장규정 시행세칙 제15조제4항제3호')]:
  ver=db.execute('select source_artifact_sha256 from document where document_id=?',(doc,)).fetchone()[0]
  text='\n'.join(r[0] for r in db.execute('select text from source_block where document_id=? and unit_id=? order by cast(block_id as integer)',(doc,unit)))
  assert text
  originals.append({'id':ident,'anchor':{'document_id':doc,'version':ver,'unit_id':unit,'content_sha256':content_hash(text),'label':label},'text':text})
raw(DES/'originals.json',originals)
for item in items:
 for s in originals:
  if s['id'] in item['original_ids']:assert s['anchor']['document_id'] in read(ROOT/'04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/artifacts/design/corpus.json')['document_ids']
criteria={'user_request':'실제 데이터 넣고 실험해서 어떻게 동작하는지 보여줘봐','selection':'Two preselected exact stored model-output subtrees; A=1198 C1 condition_tree, B=1200 C3 first norm; do not alter prior opinions or inject analyst corrections. Whole CM007 is not rerun. Sources are exact scoped units, not complete articles. Known development probes, not holdout.',
 'hypothesis':'The unchanged local domain-profile implementation preserves a real erroneous opinion during normalization and proposes a source-grounded correction and complementary acquisition rules during sequential accumulation.',
 'success_criteria':['Both recorded subtrees normalized with exact locators and absent-reason preservation','A source comparison detects that acquisition is obligatory rather than a voluntary applicability condition; original opinion remains in ledger','B proposes the three actual acquisition method/time/remaining-share count rules while retaining previous observation and source binding','Both draft revisions and deterministic compile previews succeed without forged IDs, source/ACL/hash drift, unlimited repair or publication'],
 'failure_criteria':'Any normalization/accumulation repeated contract rejection, UNKNOWN, loss of original observation, false source adoption, or missing draft/preview is not a successful demonstration. Partial stage results retained. No output/prompt/schema edits or automatic rerun after observation.',
 'budget':{'logical_jobs':4,'physical_calls_max':9,'normalization_jobs':2,'accumulation_jobs':2,'repairs_per_job':1,'provider_switches_max':1,'per_call_seconds':180,'job_seconds':360,'batch_seconds':1800,'parallel_heavy':1},
 'plan':['Normalize A; if valid accumulate A and preview','Normalize B even if A failed; accumulate B only if A draft exists and B normalization valid','Stop all dependent model work on UNKNOWN, integrity or resource failure; persist remaining NOT_RUN'],
 'assessment':'Analyst evidence comparison after frozen run, no judge LLM, no legal gold accuracy score; full48cell E1/E2 not run','publication':'DRAFT/PREVIEW only; experimental profile approval in isolated work DB, no knowledge approval/PUB/HEAD writes','boundaries':['No MAIN/GENOS/operating DB writes','No claim about current legal effectiveness of archived rules','No vendor performance or causal quality comparison']}
put(DES/'criteria.json',criteria)
put(ART/'evaluation-only/expectations.json',{'A_recorded_quote':items[0]['payload']['leaves'][0]['text'],'A_original':'取 required: 원문은 취득하여 보유하여야 한다. 취득하는 경우로 의무를 조건화하면 안 된다.','B_checks':['사모','상장예비심사 신청일','신규상장 신청일','나머지 수량','포함'],'reason':'Both saved subtrees contain no explicit reasoning; do not invent original reason. Source comparison may newly explain its verdict.','gold_status':'Analyst diagnostic expectations, not independent legal gold'})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Stage completion, faithful original text, source contradiction/complement and exact compiled draft',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Historical recorded inputs only; no new model execution or accuracy denominator','controls':'Exact original subtrees/hash retained'},{'id':'profile','role':'candidate','derived_from':['baseline'],'changes':'Existing local domain workflow unchanged, two sequential actual authoring inputs','controls':'Frozen profile/code/model/originals/glossary/budget; no expected answer in product'}])
m['runs'][0].update(arm_ids=['profile'],selection_rule=criteria['selection'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Two actual stored CM007 judgment subtrees plus five public source units',version='1198-final-condition-and1200-final-acquisition-norm',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
reason='No RAG retrieval or pruning is run: operator-frozen archived source units are supplied directly for authoring. Bounded glossary candidate lookup is recorded separately; no article recall/quality score inferred.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
files=set(release['files'])|set(read(ROOT/'09_ARTIFACTS/AUDITS/20261029-domain-profile-implementation/pin-update.json')['product_files'])
files|={str(p.relative_to(ROOT)) for p in (ROOT/'00_SYSTEM/ONTOLOGY_PROFILES').glob('*.json')}
files|={'02_BACKEND/lawrag/research/experiment_client.py'}
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(ADR,'profile',sorted(files),experiment_id=m['experiment_id'],arm_id='profile',run_ids=['run-001']);ac.freeze(candidate)
assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1]
binding={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'candidate.json',{'code_root':str((candidate/'revisions'/v['revision_id']/'snapshot').relative_to(ROOT)),'files':{n:sha(ROOT/n) for n in sorted(files)},'candidate_revision':binding})
print('Prepared',len(files),'unchanged code files;',[(x['id'],len(json.dumps(x['payload'],ensure_ascii=False))) for x in items],'; source units',len(originals),flush=True)
