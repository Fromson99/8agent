"""Disposition of every active-path audit item; no blanket semantic certification."""
from common import *
items = [
 ('ASSESS_MEMORY','fixed','request_repair.py; corrected_memory.py; law_navigation.py; completion_execution.py','Preserve verified-span-bound prior opinions across gap reentry and restart; rebind only to current authorized originals. Hash/current request/current issue checks remain. Empty later claims cannot erase prior review state; model must reassess rather than automatically accept old opinions.'),
 ('SCOPE','fixed','request_entry.py; query_scope.py','One model scope decision binds document hints and FULLTEXT/STRUCTURE. Missing named documents remain unresolved; no widening.'),
 ('SEARCH','fixed','request_entry.py; decision_projection.py','Content questions use scoped content search; READ candidates carry stored parent headings, so same-titled provisions retain company/subject context.'),
 ('QUERY','fixed','request_entry.py; decision_projection.py','First content search uses a distinguishing expression per independent issue; broad variants follow actual results. Native OR semantics are explained to the model; source numbers and contents must not be guessed.'),
 ('ASSESS_SCOPE','fixed','completion_execution.py','Keep assessment within the requested answer type, preserve supported claims alongside gaps, and re-evaluate previous materiality against new originals while retaining history.'),
 ('A01','fixed','structure_query.py','Title overlap orders candidates but no longer discards permitted article roots. Pagination retained.'),
 ('A02','fixed','structure_query.py','No four-character short-title floor; one ambiguous title does not discard independent unique hits.'),
 ('A03','fixed','law_title_hints.py','Removed six-item cutoff and partial-match threshold; available names remain model-visible hints, not authoritative scope choices.'),
 ('A04','fixed','law_name_recovery.py; law_navigation.py','Every unresolved query can recover names independently. Removed eight-candidate cap; retain multi-article/range clues for model structure selection.'),
 ('A05','fixed','navigation_match.py; term_morph.py','Nested valid term matches survive instead of longest-surface-only deletion; token boundaries retained.'),
 ('A06','fixed','fulltext.py','All extracted query terms enter grouped fulltext expressions instead of silently truncating to 32.'),
 ('A07','retained_with_connected_fix','completion_execution.py','Definition prefetch is evidence acquisition, not sufficiency. Material follow-up research now remains available after an initial claim (A08).'),
 ('A08','fixed','completion_execution.py','Existing claims and answer_first no longer defer material research to a future user turn. Native bounded reentry, duplicate and budget rules retained.'),
 ('A09','fixed','completion_v6.py; completion_contracts.py','Modern model materiality is preserved rather than forcing all missing facts/sources material. Coherence, original-source and fact provenance checks remain.'),
 ('A10','fixed','relation_read_policy.py','Lexical reference hints no longer decide reading obligation or legal applicability. Model chooses FOLLOW/SKIP with reasons; FOLLOW still binds complete target sources.'),
 ('A11','fixed','completion_v8.py','Same-source norm reuse across issues is not rejected solely for repeated semantic content. Exact-source and receipt integrity remain.'),
 ('A12','fixed','completion_execution.py','Compact ASSESS requires and preserves model issue reasons; no replacement by status/count-derived reasons.'),
 ('A13','retained_resource_contract','source and scope request limits','Read/page/context/selection budgets are resource contracts, not legal sufficiency judgments. Existing pagination/reentry behavior and bounded failure remain.'),
 ('A14','retained_nonblocking_metadata','comparison result metadata','Derived comparison status labels do not establish legal correctness or block original delivery. No unverified legal interpretation promoted to fact.'),
 ('A15','audit_correction_no_active_exclusion','pipeline.py','Selected unified-v6 planning already defaults to 전체. The audit attribution of default revision-history exclusion to this active path was incorrect; conditional legacy behavior was not activated.'),
 ('HIERARCHY','integrated_parent_fix','structure_query.py; structure_selection.py; viewer.py','Preserve ADR0976 stored path-qualified identities and legacy division traversal; remaining two malformed nested data bindings are documented, not invented.'),
 ('MULTITURN','integrated_existing_fix','memory_rag.py; readable_log.py','Preserve existing current-request and structured-scope refresh wiring; verify with native multi-turn API contracts.'),
 ('B01-B10','conditional_legacy_not_active','original audit conditional paths','Not represented as active MAIN defects or newly fixed functionality. Their files remain preserved; no legacy activation or broad semantic certification.')
]
save(ART/'fix-coverage.json', {'scope':'All previously reported active-path items classified; candidate implementation and native contracts only until promotion receipts exist.',
 'source_audit':'09_ARTIFACTS/AUDITS/20261022-semantic-decision-audit/FINDINGS.json',
 'items':[dict(id=i,status=s,code=c,disposition=d) for i,s,c,d in items],
 'guards_retained':['ACL','original bytes and spans','code/data hashes','state/revision','publication and duplicate consistency','bounded retries and budgets'],
 'remaining_semantics':'Model sufficiency and applicability judgments may still over-investigate or err. Actual observed cases and partial results are preserved separately.'})
print('Recorded',len(items),'audit dispositions')
