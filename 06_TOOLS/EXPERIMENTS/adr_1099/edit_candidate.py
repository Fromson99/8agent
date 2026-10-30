"""Apply only planned hunks inside the unexecuted isolated candidate."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1099/performance-r1/snapshot'
def edit(name, old, new, count=1):
    p=CODE/name
    text=p.read_text()
    assert text.count(old)==count, (name,old[:90],text.count(old))
    p.write_text(text.replace(old,new))
BASE='02_BACKEND/semantic_runtime/'
AG=BASE+'legal_agent/'

# A: share the exact existing title matcher, without glossary or morphology work.
edit(BASE+'navigation_match.py',
"    def starts(self, question, scope):\n        scope=set(self.tools.validate_scope(scope))\n        docs=self.document_names.match(question)\n        docs=[h for h in docs if not any(x['start']<=h['start'] and x['end']>=h['end'] and len(x['key'])>len(h['key']) for x in docs)]\n        named={d for h in docs for d in h['values'] if d in scope}",
"    def _document_matches(self, question, scope):\n        scope=set(self.tools.validate_scope(scope))\n        docs=self.document_names.match(question)\n        docs=[h for h in docs if not any(x['start']<=h['start'] and x['end']>=h['end'] and len(x['key'])>len(h['key']) for x in docs)]\n        return scope, docs, {d for h in docs for d in h['values'] if d in scope}\n\n    def document_starts(self, question, scope):\n        _, _, named = self._document_matches(question, scope)\n        return [{'id':d,'name':self.documents[d],'document_context':self.document_context.get(d,{})} for d in sorted(named)]\n\n    def starts(self, question, scope):\n        scope, docs, named = self._document_matches(question, scope)")
edit(AG+'memory_rag.py', "self.s.sources.matcher.starts(self.host.question(state),self.s.sources.scope)['documents']", "self.s.sources.matcher.document_starts(self.host.question(state),self.s.sources.scope)")
shutil.copyfile(ROOT/'02_BACKEND/lawrag/research/candidates/adr_1067/profile-optimized-r1/revisions/rev-002/snapshot'/AG/'schema_preparation.py', CODE/AG/'schema_preparation.py')
edit(AG+'memory_rag.py', 'from jsonschema import validate', 'from .schema_preparation import validate')
edit(AG+'memory_rag.py','validate(out,schema)','validate(out,schema,owner=self.s)')
edit(AG+'read_candidate_pages.py','from jsonschema import validate','from .schema_preparation import validate')
edit(AG+'read_candidate_pages.py','validate(value, wire)','validate(value, wire, owner=inv.s)')
edit(AG+'decision_projection.py','from jsonschema import validate','from jsonschema import validate\nfrom .schema_preparation import validate as prepared_validate, OrderedSchemaValidators')
edit(AG+'decision_projection.py','    def expand(raw):\n        validate(raw,wire)','    validators = OrderedSchemaValidators()\n    def expand(raw):\n        validators.validate(raw,wire)')
edit(AG+'decision_projection.py','        validate(value,schema)\n        return value','        validators.validate(value,schema)\n        return value')
edit(AG+'decision_projection.py','        validate(value,schema)','        prepared_validate(value,schema,owner=inv.s)',count=2)
edit(AG+'decision_projection.py','judgment.validate_review(value,judgment_context,current,issues)','judgment.validate_review(value,judgment_context,current,issues,owner=inv.s)')
edit(AG+'read_judgment.py','def validate_review(value, ctx, current, issues):','def validate_review(value, ctx, current, issues, *, owner=None):')
edit(AG+'read_judgment.py','    validate(review, review_schema(ctx, current, issues))',
"    schema = review_schema(ctx, current, issues)\n    if owner is None:\n        validate(review, schema)\n    else:\n        from .schema_preparation import validate as prepared_validate\n        prepared_validate(review, schema, owner=owner)")
edit(AG+'read_judgment.py',"validate_review(value, ctx, current, [i['id'] for i in data['issues']])", "validate_review(value, ctx, current, [i['id'] for i in data['issues']], owner=inv.s)")

# B: use the existing authorized source view and bounded batching. Metadata
# lengths are exact Unicode lengths, including the rare embedded NUL case.
edit(BASE+'storage.py',"        ids = [str(b) for b in bids]\n        found = {}", "        requested = [str(b) for b in bids]\n        ids = list(dict.fromkeys(requested))\n        found = {}")
edit(BASE+'storage.py',"        return [found[b] if b in found else self.source(did,b) for b in ids]",
"        self.check_unchanged()\n        for b in requested:\n            if b not in found:raise KeyError((did,b))\n        return [dict(found[b]) for b in requested]\n\n    def source_lengths(self, did, bids):\n        \"\"\"Exact codepoint lengths from the same bound source view, no body copy.\"\"\"\n        self.check_unchanged()\n        requested = [str(b) for b in bids]\n        ids = list(dict.fromkeys(requested)); found = {}\n        for start in range(0, len(ids), 800):\n            part = ids[start:start+800]\n            marks = ','.join('?' for _ in part)\n            for bid, size, nul_text in self.db.execute(\n                'SELECT block_id,LENGTH(text),CASE WHEN instr(text,char(0))>0 THEN text END '\n                'FROM source_block WHERE document_id=? AND block_id IN ('+marks+')', [did,*part]):\n                found[str(bid)] = len(nul_text) if nul_text is not None else size\n        self.check_unchanged()\n        for b in requested:\n            if b not in found:raise KeyError((did,b))\n        return {b:found[b] for b in requested}")
p=CODE/AG/'unit_reading.py';t=p.read_text();start=t.index('def block_chars(');end=t.index('\n\ndef exact_offer(',start)
t=t[:start]+'''def block_lengths(s, did, ids):
    """Request-owned metadata; changed store or permission binding cannot hit."""
    s.store.check_unchanged()
    binding = (s.store, getattr(s.store, '_binding_state', None), frozenset(s.scope))
    if getattr(s, '_unit_block_chars_binding', None) != binding:
        s._unit_block_chars = {}
        s._unit_block_chars_binding = binding
    cache = s._unit_block_chars
    wanted = list(dict.fromkeys(str(b) for b in ids))
    missing = [b for b in wanted if (did,b) not in cache]
    if missing:
        if hasattr(s.store, 'source_lengths'):
            lengths = s.store.source_lengths(did, missing)
        else:
            # Adapters without an exact metadata contract keep their full checks.
            lengths = {b:len(s.store.source(did,b)['text']) for b in missing}
        s.store.check_unchanged()
        if set(lengths) != set(missing):raise ContractError('source length batch is incomplete')
        cache.update({(did,b):n for b,n in lengths.items()})
    return {b:cache[(did,b)] for b in wanted}


def block_chars(s, did, ids):
    lengths = block_lengths(s, did, ids)
    return sum(lengths[str(b)] for b in ids)
'''+t[end:];p.write_text(t)
edit(AG+'unit_reading.py',"'blocks': [s.store.source(hit['document_id'], b) for b in offer['block_ids']]", "'blocks': s.store.sources(hit['document_id'], offer['block_ids'])")
edit(AG+'unit_reading.py',"            for b in source['blocks']:\n                raw=s.store.source(did,b['block_id']); uid=str(raw.get('unit_id') or root)","            for raw in s.store.sources(did, [b['block_id'] for b in source['blocks']]):\n                uid=str(raw.get('unit_id') or root)")
edit(AG+'tool_availability.py',"any(s.store.source(did,b)['text'] for b in wanted)", "any(ur.block_lengths(s,did,wanted).values())")
edit(AG+'tool_availability.py',"    for bid in offer['block_ids']:\n        size=len(s.store.source(hit['document_id'],bid)['text']);end=0", "    lengths_by_block = ur.block_lengths(s, hit['document_id'], offer['block_ids'])\n    for bid in offer['block_ids']:\n        size=lengths_by_block[str(bid)];end=0")
edit(AG+'tool_availability.py',"        known.append({'source_id':hit['source_id'],'spans':[", "        lengths = ur.block_lengths(s, hit['document_id'], offer['block_ids'])\n        known.append({'source_id':hit['source_id'],'spans':[")
edit(AG+'tool_availability.py',"'end_cp':len(s.store.source(hit['document_id'],b)['text'])", "'end_cp':lengths[str(b)]")

# C: one projection per exact authorized query, including selected unit scope.
edit(BASE+'unit_fulltext.py','def _projection(self, db, terms, allowed):','def _projection(self, db, terms, allowed, unit_keys=None):')
edit(BASE+'unit_fulltext.py',"binding = ('matches', self.cache_namespace(), tuple(terms), scope, MATCH_CACHE_ROWS)","units = None if unit_keys is None else tuple(sorted(set(unit_keys)))\n        binding = ('matches', self.cache_namespace(), tuple(terms), scope, units, MATCH_CACHE_ROWS)")
edit(BASE+'unit_fulltext.py',"'AND u.source_id IN (SELECT value FROM json_each(?)) LIMIT ?',\n                    [expression(terms), json.dumps(sorted(scope)), MATCH_CACHE_ROWS+1], 'project_matches')", "'AND u.source_id IN (SELECT value FROM json_each(?))' +\n                    ('' if units is None else ' AND u.key IN (SELECT value FROM json_each(?))') + ' LIMIT ?',\n                    [expression(terms), json.dumps(sorted(scope)),\n                     *([] if units is None else [json.dumps(units)]), MATCH_CACHE_ROWS+1], 'project_matches')")
edit(BASE+'unit_fulltext.py',"self._projection(db, terms, allowed) if unit_keys is None else None", "self._projection(db, terms, allowed, unit_keys)", count=3)
print('Applied A-C candidate hunks; not frozen or executed.')
