from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
def change(name,old,new):
 p=C/'02_BACKEND'/name;t=p.read_text();assert old in t,(name,old);p.write_text(t.replace(old,new))
L='semantic_runtime/legal_agent/'
change(L+'structure_query.py','matcher.structures.match(question, include_nested=True)','matcher.structures.match(question)')
change(L+'structure_query.py','matcher.structures.match(query, include_nested=True)','matcher.structures.match(query)')
p=C/'02_BACKEND'/L/'completion_contracts.py';t=p.read_text()
old='def assessment_errors(value, schema, issues):';assert old in t
t=t.replace(old,'def assessment_errors(value, schema, issues, *, model_materiality=False):')
t=t.replace("if gap['kind'] != 'UNRESOLVED_REFERENCE' and not gap['material']:\n            errors.append", "if not model_materiality and gap['kind'] != 'UNRESOLVED_REFERENCE' and not gap['material']:\n            errors.append")
p.write_text(t)
change(L+'completion_v6.py','cc.assessment_errors(legacy,legacy_schema,issues)','cc.assessment_errors(legacy,legacy_schema,issues,model_materiality=True)')

# Unsupported raw ranges are not guessed into coordinates: expose name clues and
# let the next native structured decision express the requested original set.
p=C/'02_BACKEND'/L/'law_name_recovery.py';t=p.read_text()
old="""        result = _attach_one(attempt, matcher, scope).get('law_name_recovery')
        if result and result['recovery_id'] not in {r['recovery_id'] for r in recoveries}:"""
new="""        result = _attach_one(attempt, matcher, scope).get('law_name_recovery')
        if result is None:
            result = unresolved_name_clues(attempt, matcher, scope)
        if result and result['recovery_id'] not in {r['recovery_id'] for r in recoveries}:"""
assert old in t;t=t.replace(old,new)
pos=t.index('def attach(page, matcher, scope):')
t=t[:pos]+'''def unresolved_name_clues(page, matcher, scope):
    """Expose a failed query verbatim; the model must choose its structure."""
    failed = [r for r in page.get('resolutions',[]) if r.get('status')=='MISS']
    codes = {r.get('failure',{}).get('code') for r in failed}
    if page.get('failure'): codes.add(page['failure']['code'])
    if not codes or not codes <= RECOVERABLE | {'UNSUPPORTED_STRUCTURE_RANGE'}:
        return None
    queries = page.get('queries',[])
    if len(queries)!=1 or matcher is None: return None
    query = queries[0]; mentions = find_coordinates(query)
    if not mentions: return None
    name = query[:mentions[0].start].strip(' \\t\\n「」『』“”')
    # A full failed phrase is a lexical search, never an invented exact name.
    if not name: return None
    items,total=candidates(matcher,scope,name)
    value={'contract':CONTRACT,'name_query':name,'original_queries':queries,
        'original_document_id':page.get('document_id'),
        'original_failure':deepcopy(page.get('failure') or next((r.get('failure') for r in failed if r.get('failure')),None)),
        'structure_filter':None,'requires_structure_decision':True,
        'candidates':items,'total_candidates':total,'omitted_candidates':0,
        'citation_eligible':False,'no_match_means':'이름 조회 미확인은 법령 부재의 증명이 아닙니다.'}
    value['recovery_id']=digest(value)
    return value


'''+t[pos:]
p.write_text(t)
p=C/'02_BACKEND'/L/'law_navigation.py';t=p.read_text()
old="""                tried = retry_key(name_recovery,row['document_id']) in self.p['law_name_retry_history']
                row['already_tried'] = tried"""
new="""                if name_recovery.get('requires_structure_decision'):
                    row['retry_action'] = None
                    row['structure_search_action'] = offer('SEARCH_STRUCTURE',
                        {'document_id':row['document_id']},
                        row['title']+'에서 미확인 요청의 범위·복수·제외를 구조화해 조회: '+
                        ' / '.join(name_recovery['original_queries']))
                    continue
                tried = retry_key(name_recovery,row['document_id']) in self.p['law_name_retry_history']
                row['already_tried'] = tried"""
assert old in t;t=t.replace(old,new);p.write_text(t)
change(L+'law_name_recovery.py',"    filters = recovery['structure_filter']\n    if 'selection' in filters:","    filters = recovery['structure_filter']\n    if filters is None:\n        raise ProposalError('unresolved raw scope requires a new structured selection')\n    if 'selection' in filters:")

for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if 'files' in v:
  for n in v['files']:v['files'][n]=sha(C/n)
  save(p,v)
def pins(v):
 if isinstance(v,dict):
  if v.get('manifest') and 'sha256' in v and (C/v['manifest']).is_file():v['sha256']=sha(C/v['manifest'])
  for x in v.values():pins(x)
 elif isinstance(v,list):
  for x in v:pins(x)
p=C/'00_SYSTEM/PIPELINE.json';v=read(p);pins(v);save(p,v)
print('Consumers, recovery alternatives and engine pins connected')
