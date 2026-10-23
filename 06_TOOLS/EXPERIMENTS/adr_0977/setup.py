"""Reserve design and snapshot before editing any proposed product file."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='One model-owned named/unrestricted scope decision drives both search modes; navigable lexical candidates and bounded research preserve missing work without rewriting semantic judgments.',
 primary_metric='Deterministic scope/source/decision invariants, with actual-model scope probe recorded separately from legal accuracy.',
 success_criteria='All new deterministic contracts pass; no ACL, original, hash, state, exclusion, budget or duplicate execution regression. Known failed examples are diagnostic only. Any model misses remain recorded; this probe cannot promote MAIN.',
 failure_criteria='Cross-scope original admission, invented evidence, lost current working changes or new critical contract failure rejects candidate.',
 criteria_frozen_before_run=True,
 sampling='Development examples from the prior audit plus new synthetic edge contracts. Separate prospective qualification is required before MAIN.',
 budget={'parallel_heavy_processes':1,'test_address_space_bytes':3*1024**3,'full_runtime_rss_bytes':10*1024**3,'minimum_available_ram_bytes':3*1024**3,'probe_physical_model_calls':24,'transport_retries':0},
 recovery={'entry':'Existing output_contract bounded_decision owns same-view repair, durable counts and repeated-conflict stop; no keyword scope inference.',
 'selection':'Missing/ambiguous coordinates preserve state and return failure; no scope widening.',
 'assessment':'Existing completion_execution owns one repair/reentry budget. Nonmaterial gaps remain nonmaterial. Source/ACL/hash errors cannot be semantically repaired.',
 'retrieval':'Expose navigable candidates and all query terms, retain request/context/time limits; no source absence inference from search miss.'})
m['integration'].update(result_arm='candidate',reason='Integrate current MAIN with completed hierarchy fix and current working multiturn repairs, then fix diagnosed online semantic policies.',
 common_invariants=['ACL and user scope','exact source binding','hash/state revisions','cumulative budgets and receipts'],
 conflicts=[],no_conflict_reason='Hierarchy changes replace structural traversal only; current multiturn changes are preserved by snapshotting current files. New edits are surgical against that snapshot.',
 rollback_ref='ADR-0974-experiment-v1/candidate')
for p in m['integration'].get('parent_contributions',[]):
 p['adopted']=['Current selected request/selection runtime' if '0974' in str(p) else 'Path-qualified divisions and legacy traversal']
 p['excluded']=['Historical model quality claims and deployment claims']
save(ADR/'실험/manifest.json',m)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
paths=sorted(set(release['files'])|{'02_BACKEND/lawrag/core/structure/viewer.py'})
candidate=ac.snapshot(ADR,'candidate',paths,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
save(ART/'stage.json',{'base_pointer':pointer,'base_release':release,
 'working_baseline':{p:sha(ROOT/p) for p in paths},
 'roots':{'baseline':release['code_root'],'candidate':str((candidate/'snapshot').relative_to(ROOT))},
 'candidate_dir':str(candidate.relative_to(ROOT)),
 'preexisting_differences':[p for p in paths if sha(ROOT/p)!=release['files'].get(p)]})
save(ART/'scope-decisions.json',{
 'entry':'Replace two independent title/scope choices by one named or authorized scope object; derive legacy command/hints deterministically.',
 'A01':'Preserve all structural candidates in the selected document, use title overlap only for order and pagination.',
 'A02':'Keep short exact headings and independent unambiguous matches; preserve ambiguity diagnostics.',
 'A03':'Do not truncate title clues; retain lexical origin and explicit no-match semantics.',
 'A04':'Recover failed queries independently, preserve structured selection and original failed request; candidate lists not truncated.',
 'A05':'Expose nested term matches while preserving lexical word/morpheme boundaries and unambiguous document routing.',
 'A06':'Preserve all content query terms; bounded input and chunked SQLite expressions protect resources.',
 'A07':'Auto-acquired definitions are evidence candidates only; do not let initial handoff imply all issues complete.',
 'A08':'A supported claim no longer suppresses bounded investigation of fresh material gaps.',
 'A09':'Preserve model materiality; retain supported-claim/source coherence checks and correction audit.',
 'A10':'Relation wording remains a hint, never a required reading/applicability verdict; model reasons preserved.',
 'A11':'Permit same source/effect for distinct issue contexts; source integrity remains checked.',
 'A12':'Receive and retain model issue reasons in compact assessment.',
 'A13':'Keep resource/representation bounds, explicit omitted IDs and continuations; not a legal relevance filter.',
 'A14':'Keep PARTIAL display and source preservation; status-derived field is compatibility metadata, not independent proof.',
 'A15':'Recheck found v6 Pipeline.plan already defaults to 전체; prior audit default-history exclusion does not apply to MAIN99 v6. Preserve provenance roles.',
 'navigation_scope':'Offer full user-authorized document body search independently of the current article cursor.',
 'B01-B10':'Do not activate unused/conditional legacy engines or claim them fixed by current online changes.'})
print(candidate)
