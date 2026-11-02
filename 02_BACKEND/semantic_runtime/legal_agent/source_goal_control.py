"""Execute explicit source locators; source arrival never certifies legal meaning."""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError, ProposalError
from .completion_contracts import obj
from lawrag.core.legal_coordinate import find_coordinates

VERSION='source-goal-execution-v3'
# Structural branches, not coordinate levels. appendix remains a supported legacy branch.
COORDINATE_SCOPES=('body','addendum','annex','form','repeated','appendix')

def validate_scope(value, *, persisted=False, path='/source_targets/coordinate_scope'):
    if value not in COORDINATE_SCOPES:
        message='source_targets.coordinate_scope must name a structural branch: '+', '.join(COORDINATE_SCOPES)+'. 조/항/호/목 are levels, not scopes; preserve the target and correct the scope before lookup.'
        if persisted:raise ContractError(message)
        from .output_contract import OutputContractError,issue
        row=issue('INVALID_COORDINATE_SCOPE',path,expected={'enum':list(COORDINATE_SCOPES)})
        row.update(received=value,message=message)
        raise OutputContractError(message,[row])


def target_coordinate(row, *, path='/source_targets/coordinate'):
    """Parse one exact locator; a matching display scope adds no new meaning."""
    from .output_contract import OutputContractError,issue
    text=row['coordinate'].strip()
    if ':' in text:
        prefix,coordinate=text.split(':',1)
        if prefix not in COORDINATE_SCOPES or prefix!=row['coordinate_scope']:
            item=issue('SOURCE_TARGET_SCOPE_CONFLICT',path,
                related=[path.rsplit('/',1)[0]+'/coordinate_scope'],
                expected={'matching_scope':row['coordinate_scope']})
            item.update(received=text,message='Coordinate prefix must equal coordinate_scope; choose the intended scope explicitly.')
            raise OutputContractError('source target coordinate prefix conflicts with coordinate_scope',[item])
        text=coordinate.strip()
    occurrences=find_coordinates(text)
    if len(occurrences)!=1 or occurrences[0].start!=0 or occurrences[0].end!=len(text):
        item=issue('SOURCE_TARGET_COORDINATE_INVALID',path,
            expected='one complete legal coordinate; matching scope prefix optional; ranges use structure selection')
        item.update(received=row['coordinate'],message='Use one exact coordinate such as 제1조, with coordinate_scope in its separate field.')
        raise OutputContractError('source_targets.coordinate requires one complete legal coordinate; ranges need ordinary structure selection',[item])
    return occurrences[0].coordinate.canonical_surface()


PROMPT='''origin_heading이 있는 목표는 서버가 질문과 직접 맞는 저장 표제에서 찾은 원문이다. 다른 원문이나 이유만으로 제외할 수 없으며 먼저 해당 원문을 확인한다. 원문 확보 뒤 실제 적용 여부는 판단하며 무관하면 답변에서 제외할 수 있다. source_targets에는 이번에 반드시 확보할 원문의 document_ref(허용된 문서 D번호), coordinate(정확한 조·항·호), coordinate_scope, issue_id, reason을 쓴다. 위치가 불명확하면 []이며 조문번호를 추측하지 않는다. coordinate_scope는 body(본문), addendum(부칙), annex(별표), form(서식), repeated(반복 범위), appendix(기존 부록) 중 선택한다. 조·항·호·목은 범위 값이 아니다. 기존 목표는 SOURCE_GOAL의 goal_id만 선택한다. 서버가 문서와 좌표를 현재 도구 번호에 연결하며 이미 확정된 목표는 모델 선택 전에 조회·READ를 집행한다. source_goal_context의 미확보 목표는 다른 문서를 읽거나 FINISH한다고 사라지지 않는다. 불필요함을 실제 원문으로 확인한 경우에만 source_goal_exclusions에 goal_id, reason, basis_refs를 쓴다. 원문 확보는 법률적 충분성이나 판단 완료가 아니다.'''
PROMPT += '\n기존 선언한 필요를 위한 목표이면 source_targets.need_refs에 answer_progress_context.declared_needs 또는 read_judgments.needs의 ID를 연결한다. 새 필요여서 아직 ID가 없으면 생략할 수 있으며, 목표 자체에도 지속 ID가 부여된다. 필요한 참조는 각각 선택한다. 같은 문장에 참조됐다는 이유로 서버가 나머지 조문을 선택하지 않는다.'

def enabled(inv):return inv.policy.get('source_goal_control',False) and inv.policy.get('supervisor_mode')=='enforce'

def state(inv,data):
    from . import investigation_supervisor as su
    return su.state_for(inv,data)

def commit(inv,st):
    from . import investigation_supervisor as su
    su.save(inv,st)

def options(data,actions):
    names={x['document_id']:x['name'] for x in data.get('laws',[])}
    return [{'lookup_target':k,'document_id':a['identity']['document_id'],
             'document_name':names.get(a['identity']['document_id'],'')}
        for k,a in actions.items() if a['action']=='SEARCH_STRUCTURE' and a['identity'].get('document_id')]

def fields(inv,data,actions):
    targets=list(dict.fromkeys(r['document_id'] for r in options(data,actions)))
    current=[s['id'] for s in data.get('sources',[]) if s.get('text')]
    st=state(inv,data);ids=[g['goal_id'] for g in st.get('source_goals',[]) if g['status'] in ('REQUIRED','BLOCKED')]
    ref={'type':'array','minItems':1,'maxItems':len(current),'items':{'enum':current},'uniqueItems':True} if current else {'type':'array','maxItems':0,'items':{'type':'string'}}
    target=obj({'document_ref':{'enum':targets},'coordinate':{'type':'string','minLength':1,'maxLength':100},'coordinate_scope':{'type':'string','enum':list(COORDINATE_SCOPES)},'issue_id':{'enum':[i['id'] for i in data['issues']]},'reason':{'type':'string','minLength':1,'maxLength':400}}) if targets else {'type':'object'}
    if targets:
        from . import need_continuity, read_judgment
        target['properties']['need_refs']=read_judgment.strings(need_continuity.known_needs(inv,data))
    exclude=obj({'goal_id':{'enum':ids},'reason':{'type':'string','minLength':1,'maxLength':400},'basis_refs':ref}) if ids and current else {'type':'object'}
    return {'source_targets':{'type':'array','maxItems':4 if targets else 0,'items':target},
            'source_goal_exclusions':{'type':'array','maxItems':len(ids) if current else 0,'items':exclude}}

def attach(schema,inv,data,actions):
    out=deepcopy(schema);props=fields(inv,data,actions)
    for b in out['anyOf']:
        b['properties'].update(deepcopy(props));b['required']+=list(props)
    return out

def validate(value,inv,data,actions):
    offered={r['lookup_target']:r for r in options(data,actions)}
    from .need_continuity import known_needs
    needs=known_needs(inv,data)
    for index,row in enumerate(value.get('source_targets',[])):
        validate_scope(row.get('coordinate_scope'),path='/source_targets/'+str(index)+'/coordinate_scope')
        did=target_document(row,offered)['document_id']
        if did not in inv.s.scope:raise ContractError('source target document unauthorized')
        target_coordinate(row,path='/source_targets/'+str(index)+'/coordinate')
        refs=row.get('need_refs',[])
        if len(refs)!=len(set(refs)) or any(n not in needs or row['issue_id'] not in needs[n]['issue_refs'] for n in refs):
            raise ProposalError('source target need_refs must bind known needs of the same issue')
    st=state(inv,data);goals={g['goal_id']:g for g in st.get('source_goals',[])}
    current={s['id'] for s in data.get('sources',[]) if s.get('text')}
    ids=[]
    for row in value.get('source_goal_exclusions',[]):
        ids.append(row['goal_id'])
        if row['goal_id'] not in goals or not row['reason'].strip() or not row['basis_refs'] or not set(row['basis_refs'])<=current:
            raise ProposalError('source_goal_exclusions require an existing goal, reason and current original evidence')
        from .scope_completion import validate_exclusion
        validate_exclusion(inv,data,goals[row['goal_id']],row)
    if len(ids)!=len(set(ids)):raise ProposalError('duplicate source goal exclusion')

def record(value,inv,data,actions,st):
    validate(value,inv,data,actions)
    receipts=list(st.get('source_goal_submissions',[]));signature=digest([data['presentation_id'],value.get('source_targets',[]),value.get('source_goal_exclusions',[])])
    if signature in receipts:return
    goals=deepcopy(st.get('source_goals',[]));offered={r['lookup_target']:r for r in options(data,actions)}
    for row in value.get('source_targets',[]):
        doc=target_document(row,offered);coordinate=target_coordinate(row)
        ident=digest([row['issue_id'],doc['document_id'],coordinate,row['coordinate_scope']])
        for existing in goals:
            if existing['identity']==ident:existing.pop('origin_reference_bundle',None)
        if not any(g['identity']==ident for g in goals):
            if len(goals)>=16:raise ProposalError('source goal limit16 reached; preserve existing goals')
            goals.append({'goal_id':'SG'+str(len(goals)+1),'identity':ident,'issue_id':row['issue_id'],
                'document_id':doc['document_id'],'document_name':doc['document_name'],'coordinate':coordinate,
                'coordinate_scope':row['coordinate_scope'],'reason':row['reason'],'status':'REQUIRED','routes':[],'arrivals':[]})
        selected=next(g for g in goals if g['identity']==ident)
        selected['need_refs']=sorted(set(selected.get('need_refs',[])) | set(row.get('need_refs',[])))
    # A validated ASSESS locator is an existing model opinion with a server
    # binding. Carry it forward even when the next selector forgets it.
    if data.get('assessment_gaps'):
        from .answer_progress import assessment_requirements
        required={r['gap_id'] for r in assessment_requirements(data,inv)}
        for gap in data['assessment_gaps']:
            binding=gap.get('target_binding',{})
            if gap['gap_id'] not in required or binding.get('status')!='EXACT':continue
            for pair in binding.get('pairs',[]):
                did,uid=pair['document_id'],str(pair['unit_id'])
                if did not in inv.s.scope:raise ContractError('ASSESS source goal unauthorized')
                key=(did,uid);node=inv.s.matcher.units.get(key);coord=inv.s.matcher.stored_coordinates.get(key)
                if not node or not coord or coord.canonical_surface()!=pair['coordinate']:raise ContractError('ASSESS source goal coordinate changed')
                scope=node.get('coordinate_scope')
                if not scope:continue
                ident=digest([gap['issue_id'],did,pair['coordinate'],scope])
                if any(g['identity']==ident for g in goals):continue
                if len(goals)>=16:raise ProposalError('source goal limit16 reached')
                goals.append({'goal_id':'SG'+str(len(goals)+1),'identity':ident,'issue_id':gap['issue_id'],
                    'document_id':did,'document_name':pair['document_name'],'coordinate':pair['coordinate'],
                    'coordinate_scope':scope,'reason':gap['reason'],'status':'REQUIRED','routes':[],'arrivals':[],
                    'origin_gap_id':gap['gap_id'],'expected':pair_expected(inv.s,binding,pair)})
    # Only the model selects needed references/ranges. A citation to a sibling
    # is an offered lead, not authorization to create another source goal.
    for row in value.get('source_goal_exclusions',[]):
        goal=next(g for g in goals if g['goal_id']==row['goal_id'])
        from .scope_completion import validate_exclusion
        validate_exclusion(inv,data,goal,row)
        goal['status']='EXCLUDED';goal['exclusion']=deepcopy(row)
    refresh(inv,goals)
    receipts.append(signature);st['source_goal_submissions']=receipts;st['source_goals']=goals;commit(inv,st)

def context(inv,data):
    return {'version':VERSION,'goals':deepcopy(state(inv,data).get('source_goals',[])),
        'meaning':'ACQUIRED는 실제 요청 원문 확보이며 적용·답변 충분성 인증이 아니다. REQUIRED/BLOCKED는 명시한 원문이 아직 확보되지 않았음이다.'}

def matches(inv,identity,goal):
    did=identity.get('document_id');uid=identity.get('unit_id')
    source=inv.s.matcher.sources.get(identity.get('source_id')) if identity.get('source_id') else None
    if source:
        if did is not None and source['document_id']!=did:raise ContractError('source goal read identity document mismatch')
        did=source['document_id'];uid=source.get('unit_id') if uid is None else uid
    if did!=goal['document_id'] or uid is None:return False
    key=(did,str(uid));node=inv.s.matcher.units.get(key);coordinate=inv.s.matcher.stored_coordinates.get(key)
    return bool(node and coordinate and coordinate.canonical_surface()==goal['coordinate'] and node.get('coordinate_scope')==goal['coordinate_scope'])

def resolve(inv,data,actions,payload,value,decision,expand,st,*,preselection=False):
    """One existing action per turn; no hidden SQL/reads or semantic adoption."""
    if not enabled(inv):return None
    from .scope_completion import discover
    discover(inv,data,st)
    record(value,inv,data,actions,st)
    refresh(inv,st.get('source_goals',[]));commit(inv,st)
    pending=[g for g in st.get('source_goals',[]) if g['status'] in ('REQUIRED','BLOCKED')]
    if not pending:return None
    from . import investigation_supervisor as su
    receipts=st.setdefault('source_goal_actions',{})
    commit(inv,st)
    if data['presentation_id'] in receipts:
        accepted=deepcopy(receipts[data['presentation_id']]['decision']);inv.validate(accepted,data,actions)
        su.authorize(inv,data,accepted,st,recovery=True);return accepted
    if inv.left()<=inv.s.profile['selection_time_reserve_seconds']:su.stop(inv,st,'SOURCE_GOAL_TIME_RESERVE')
    terminal=decision['next_action'] in ('FINISH','PENDING')
    for goal in pending:
        chosen=None;kind=None
        # Execute only the exact offered coordinate. Hints/previews never prove arrival.
        reads=[k for k,a in actions.items() if a['action']=='READ_ARTICLES' and matches(inv,a['identity'],goal)]
        if len(reads)==1 and 'READ' not in goal['routes']:
            chosen={'choice':'READ','selections':[{'target':reads[0],'issue_id':goal['issue_id'],'missing_need':goal['reason'],'relation':'DIRECT','source_ref':None}]};kind='READ'
        elif 'LOOKUP' not in goal['routes']:
            lookups=[k for k,a in actions.items() if a['action']=='SEARCH_STRUCTURE' and a['identity'].get('document_id')==goal['document_id']]
            if lookups:
                chosen={'choice':'LOCATE','target':lookups[0],'issue_id':goal['issue_id'],'missing_need':goal['reason'],'relation':'DIRECT','source_ref':None,'structure_filter':{'coordinate':goal['coordinate'],'title':'','coordinate_scope':goal['coordinate_scope']}};kind='LOOKUP'
            elif (goal.get('origin_gap_id') or goal.get('origin_heading') or goal.get('reference_purposes')) and goal['coordinate_scope']=='body':
                global_targets=[k for k,a in actions.items() if a['action']=='SEARCH_STRUCTURE' and a['identity'].get('document_id') is None]
                if global_targets:
                    chosen={'choice':'CATALOG_SEARCH','target':global_targets[0],'issue_id':goal['issue_id'],'missing_need':goal['reason'],'relation':'DIRECT','source_ref':None,'queries':[goal['document_name']+' '+goal['coordinate']]};kind='LOOKUP'
        if chosen is None:continue
        if inv.policy.get('read_judgment'):
            for item in chosen['selections'] if chosen['choice']=='READ' else [chosen]:
                item['judgment_refs']=[]
        for name in ('read_review','answer_progress','source_targets','source_goal_exclusions'):
            if name in value:chosen[name]=deepcopy(value[name])
        try:accepted=expand(chosen)
        except ProposalError as exc:
            goal['routes'].append(kind);goal['status']='BLOCKED';goal['route_failure']=str(exc);commit(inv,st)
            continue
        goal['routes'].append(kind)
        receipts[data['presentation_id']]={'goal_id':goal['goal_id'],'kind':kind,'decision':deepcopy(accepted),'status':'AUTHORIZED'}
        su.authorize(inv,data,accepted,st,recovery=True)
        inv.s.repo.event('SOURCE_GOAL_DISPATCH',{'goal_id':goal['goal_id'],'document_id':goal['document_id'],'coordinate':goal['coordinate'],'coordinate_scope':goal['coordinate_scope'],'operation':kind,'cancelled':decision,'accepted':accepted,'legal_judgment_adopted':False})
        return accepted
    if preselection:
        # No exact action is available now. Keep the durable goals and receipts,
        # but let the existing selector repair the route before any handoff.
        inv.s.repo.event('SOURCE_GOAL_SELECTION_REQUIRED',{'goal_ids':[g['goal_id'] for g in pending],
            'remaining_intermediate_routes':max(0,2-len(st.get('source_goal_bridges',[]))),
            'goals_resolved':False,'model_call':False})
        return None
    # A genuinely new intermediate route may investigate the unresolved goal.
    # It never replaces the goal and has a shared bounded permit, not a fresh loop.
    if not terminal:
        bridges=st.setdefault('source_goal_bridges',[]);route=su.route_identity(decision)
        if route not in bridges and len(bridges)<2 and set(decision.get('issue_refs',[])) & {g['issue_id'] for g in pending}:
            bridges.append(route);su.authorize(inv,data,decision,st,recovery=True)
            inv.s.repo.event('SOURCE_GOAL_INTERMEDIATE',{'goal_ids':[g['goal_id'] for g in pending],'decision':decision,'goals_resolved':False})
            return decision
    su.stop(inv,st,'SOURCE_GOALS_UNRESOLVED:'+','.join(g['goal_id'] for g in pending))

def after_execute(inv,data,decision,applied):
    if not enabled(inv):return
    st=state(inv,data);row=st.get('source_goal_actions',{}).get(data['presentation_id'])
    if not row or row['status']=='COMPLETED':return
    if digest(row['decision'])!=digest(decision):raise ContractError('source goal action differs from authorized decision')
    goal=next(g for g in st['source_goals'] if g['goal_id']==row['goal_id'])
    if row['kind']=='READ' and applied is not False:
        # Existing executor's read plan must contain a committed original.
        completed=[plan for plan in inv.p.get('read_plans',{}).values() if plan.get('status')=='ACQUIRED' and any(t in decision['targets'] and gid in inv.p.get('selected',{}) for t,gid in plan.get('completed',{}).items())]
        if not completed:raise ContractError('source goal READ lacks committed original receipt')
        refresh(inv,[goal])
        if goal['status']!='ACQUIRED':
            goal['status']='BLOCKED';goal['route_failure']='READ_INCOMPLETE_ORIGINAL_COVERAGE'
    row['status']='COMPLETED' if applied is not False else 'NOT_APPLIED';commit(inv,st)
    inv.s.repo.event('SOURCE_GOAL_RESULT',{'goal_id':goal['goal_id'],'status':goal['status'],'operation':row['kind'],'legal_judgment_adopted':False})

def unresolved(investigation,issues):
    ids={i['id'] for i in issues};rows=[]
    from .investigation_supervisor import seal
    for st in investigation.get('investigation_supervisor',{}).values():
        if st.get('state_hash')!=seal(st):raise ContractError('source goal assessment state hash mismatch')
        rows.extend(deepcopy(g) for g in st.get('source_goals',[])+st.get('scope_discovery',{}).get('overflow',[])+[r for r in st.get('reference_bundles',[]) if r.get('overflow')] if g['issue_id'] in ids and g['status'] in ('REQUIRED','BLOCKED'))
    return rows

def limit_assessment(result,goals):
    if not goals:return
    result['disposition']='LIMITED_ANSWER'
    if result.get('answer_coverage')=='COVERED':result['answer_coverage']='PARTIAL'
    for goal in goals:
        text=goal['document_name']+' '+goal['coordinate']+' 원문을 확보하지 못했습니다.'
        row={'id':'L-source-'+goal['identity'][:20],'kind':'EXECUTION_LIMIT','issue_id':goal['issue_id'],'text':text}
        if row not in result['limitation_items']:result['limitation_items'].append(row)
    result['limitations']=list(dict.fromkeys(r['text'] for r in result['limitation_items']))


def target_document(row,offered):
    # Legacy internal adapters are accepted only if their tool still has the exact document.
    if 'document_ref' in row:row={**row,'document_id':row['document_ref']}
    if 'document_id' in row:
        matches=[r for r in offered.values() if r['document_id']==row['document_id']]
        if not matches:raise ContractError('source target is outside the offered document scope')
        if 'lookup_target' in row and offered.get(row['lookup_target'],{}).get('document_id')!=row['document_id']:
            raise ContractError('source goal document/tool mismatch')
        return matches[0]
    if row.get('lookup_target') not in offered:raise ContractError('source target is outside the offered document scope')
    return offered[row['lookup_target']]


def contained_arrivals(inv,goal):
    """Existing ancestor receipt, not a new read or a semantic exclusion."""
    from . import evidence_inventory as inventory, unit_reading
    plans=[p for p in inv.p.get('read_plans',{}).values() if p.get('status')=='ACQUIRED']
    if not plans:return []
    did=goal['document_id'];matcher=inv.s.matcher
    if did not in inv.s.scope:raise ContractError('source goal outside current document scope')
    # Resolve one stored coordinate, never guess from the text or a label prefix.
    coordinates=matcher.stored_coordinates
    if goal['coordinate_scope']=='body':
        from .structure_query import coordinate_index
        rows=[((did,str(uid)),coordinates.get((did,str(uid)))) for uid in coordinate_index(matcher).get((did,goal['coordinate']),[])]
    else:rows=coordinates.for_document(did) if hasattr(coordinates,'for_document') else coordinates.items()
    candidates=[]
    for (document,uid),coordinate in rows:
        if document!=did or not coordinate or coordinate.canonical_surface()!=goal['coordinate']:continue
        node=matcher.units[(did,str(uid))]
        if node.get('coordinate_scope')==goal['coordinate_scope'] and node.get('coordinate_binding',{}).get('mode')!='unresolved':candidates.append(str(uid))
    if len(candidates)!=1:return []
    target=candidates[0];ancestors=set();current=target
    while current is not None:
        if current in ancestors:raise ContractError('source goal structure parent cycle')
        ancestors.add(current);node=matcher.units.get((did,current))
        if node is None:raise ContractError('source goal structure parent missing')
        parent=node.get('parent');current=str(parent) if parent is not None else None
    expected=None;arrivals=[]
    for plan in plans:
        for identity in plan.get('targets',[]):
            source=matcher.sources.get(identity.get('source_id'))
            if not source or source['document_id']!=did:continue
            if identity.get('document_id',did)!=did:raise ContractError('source goal read identity document mismatch')
            uid=str(identity.get('unit_id') or source.get('unit_id'))
            if uid==target or uid not in ancestors:continue
            if matcher.units[(did,uid)].get('coordinate_scope')!=goal['coordinate_scope']:continue
            for gid in plan.get('completed',{}).values():
                record=inv.p.get('selected',{}).get(gid)
                if not record or record.get('document_id')!=did or record.get('source_id')!=identity.get('source_id'):continue
                if expected is None:
                    expected=inventory.expected(inv.s,did,unit_reading.blocks(inv.s,did,target,'subtree'))
                    if any(p.get('document_id',did)!=did for p in goal.get('expected',[])):raise ContractError('source goal expected original document mismatch')
                    expected+=goal.get('expected',[])
                actual=[span for e in record.get('evidence',[]) for span in e.get('spans',[])]
                if not expected or not inventory.covers(expected,actual):continue
                for evidence in record['evidence']:
                    if evidence['document_id']!=did or evidence['source_id']!=record['source_id']:raise ContractError('source goal original identity changed')
                    inv.s.source.verify(evidence)
                goal['expected']=deepcopy(expected)
                arrivals.append(gid)
    if arrivals:
        inv.s.repo.event('SOURCE_GOAL_CONTAINED_ORIGINAL',{'goal_id':goal['goal_id'],'document_id':did,
            'coordinate':goal['coordinate'],'coordinate_scope':goal['coordinate_scope'],
            'unit_id':target,'arrivals':sorted(set(arrivals)),'new_read':False,'legal_judgment_adopted':False})
    return arrivals


def refresh(inv,goals):
    """Exact coordinate AND full verified span coverage; arrival is not a judgment."""
    from . import evidence_inventory as inventory
    for goal in goals:
        validate_scope(goal.get('coordinate_scope'),persisted=True)
        if goal['status'] not in ('REQUIRED','BLOCKED'):continue
        acquired=[]
        for plan in inv.p.get('read_plans',{}).values():
            if plan.get('status')!='ACQUIRED':continue
            identities=[x for x in plan.get('targets',[]) if matches(inv,x,goal)]
            if not identities:continue
            for gid in plan.get('completed',{}).values():
                record=inv.p.get('selected',{}).get(gid)
                if not record or record.get('document_id')!=goal['document_id']:continue
                # A batch receipt for another target cannot satisfy this target.
                offer=record.get('offer',{})
                exact=[x for x in identities if x.get('source_id')==record.get('source_id')]
                if not exact:continue
                expected=[p for p in goal.get('expected',[]) if p.get('document_id',goal['document_id'])==goal['document_id']]
                if not expected:
                    from . import unit_reading
                    identity=exact[0];uid=identity.get('unit_id')
                    if uid is None:uid=inv.s.matcher.sources[identity['source_id']].get('unit_id')
                    if uid is None:continue
                    blocks=unit_reading.blocks(inv.s,goal['document_id'],str(uid),'subtree')
                    expected=inventory.expected(inv.s,goal['document_id'],blocks)
                actual=[p for e in record.get('evidence',[]) for p in e.get('spans',[])]
                if not expected or not inventory.covers(expected,actual):continue
                # Validate original bytes through the same request source verifier.
                for e in record['evidence']:
                    if e['document_id']!=record['document_id'] or e['source_id']!=record['source_id']:raise ContractError('source goal original identity changed')
                    inv.s.source.verify(e)
                goal['expected']=deepcopy(expected)
                acquired.append(gid)
        if not acquired:acquired=contained_arrivals(inv,goal)
        if acquired:
            goal['status']='ACQUIRED';goal['arrivals']=sorted(set(acquired))


def native_decision(inv,data,actions,choice):
    """Mechanical assembly only; existing decision validator owns execution rights."""
    from .law_navigation import decision_schema
    kind='READ_ARTICLES' if choice['choice']=='READ' else 'SEARCH_STRUCTURE'
    schema=decision_schema(data,actions,{b['id'] for b in data['branches']})
    branches=[b for b in schema['anyOf'] if b['properties']['next_action']['const']==kind]
    branch=next(b for b in branches if kind=='READ_ARTICLES' or ('structure_filter' in b['properties'])==('structure_filter' in choice))
    decision={}
    for name,rule in branch['properties'].items():
        if 'const' in rule:decision[name]=deepcopy(rule['const'])
        elif len(rule.get('enum',[]))==1:decision[name]=deepcopy(rule['enum'][0])
        elif rule.get('type')=='array':decision[name]=[]
    rows=choice['selections'] if kind=='READ_ARTICLES' else [choice]
    rows=[{k:r[k] for k in ('target','issue_id','missing_need','relation','source_ref')} for r in rows]
    decision.update(next_action=kind,notes='',targets=[r['target'] for r in rows],issue_refs=list(dict.fromkeys(r['issue_id'] for r in rows)),
        reason='; '.join(r['missing_need'] for r in rows),evidence_sufficient=False,sufficiency_reason='확정된 원문을 확보한 뒤 판단한다.')
    if 'exploration' in branch['properties']:
        issues={i['id']:i for i in data['issues']}
        decision['exploration']=[{**r,'request_quote':issues[r['issue_id']].get('request_quote',inv.question),'source_quote':''} for r in rows]
    for name in ('queries','structure_filter'):
        if name in choice:decision[name]=deepcopy(choice[name])
    inv.validate(decision,data,actions)
    return decision


def prepare(inv,data,actions):
    """Import only current, server-bound ASSESS targets before the selector."""
    if not enabled(inv):return None
    st=state(inv,data)
    if st.get('pending'):raise ContractError('cannot bypass unknown pending supervisor outcome')
    from .scope_completion import discover
    discover(inv,data,st)
    record({},inv,data,actions,st)
    refresh(inv,st.get('source_goals',[]));commit(inv,st)
    return st


def preselect(inv,data,actions):
    st=prepare(inv,data,actions)
    if st is None or not any(g['status'] in ('REQUIRED','BLOCKED') for g in st.get('source_goals',[])):return None
    # No model proposal or rejected judgment enters this call. resolve uses the
    # exact existing executor/menu, durable intent, budget and resume receipts.
    return resolve(inv,data,actions,{}, {},{'next_action':'FINISH'},
        lambda value:native_decision(inv,data,actions,value),st,preselection=True)


def validate_recovery_choice(inv,data,actions,value):
    """Premature termination is a proposal error owned by the current selector."""
    if not enabled(inv) or value.get('choice') not in ('FINISH','PENDING'):return
    st=state(inv,data)
    excluded={r['goal_id'] for r in value.get('source_goal_exclusions',[])}
    pending=[g for g in st.get('source_goals',[]) if g['status'] in ('REQUIRED','BLOCKED') and g['goal_id'] not in excluded]
    if not pending or len(st.get('source_goal_bridges',[]))>=2:return
    available=[k for k,a in actions.items() if a['action'] not in ('FINISH','PENDING','DECIDE')]
    if not available:return
    from .output_contract import OutputContractError,issue
    row=issue('REQUIRED_SOURCE_RECOVERY_CHOICE','/choice',expected='Select a current investigation action or give a grounded source_goal_exclusions entry.')
    row.update(received=value['choice'],goal_ids=[g['goal_id'] for g in pending],
        message='The required original is still missing. An unsuccessful lookup does not exhaust the current investigation menu.')
    raise OutputContractError('required source needs a bounded alternative investigation choice',[row],category='DECISION_CONFLICT')


def validate_gap_closure(inv,data,row):
    """Use the same original proof for gap and source-goal closure."""
    gap=next(g for g in data['assessment_gaps'] if g['gap_id']==row['gap_id'])
    refs=set(row.get('basis_refs',[]));pages={p['id']:p for p in data.get('sources',[]) if p.get('text') and p.get('spans')}
    if not refs or not refs<=pages.keys() or not row.get('reason','').strip():
        raise ProposalError(row['status']+' requires current original basis_refs and target-specific reason; otherwise UNRESOLVED')
    from . import evidence_inventory as inventory
    for ref in refs:inventory.check_presented_page(inv.s,inv.p,pages[ref])
    st=state(inv,data)
    goals=[g for g in st.get('source_goals',[]) if g.get('origin_gap_id')==row['gap_id']]
    if row['status']=='RESOLVED' and any(g['status'] not in ('ACQUIRED','EXCLUDED') for g in goals):
        raise ProposalError('RESOLVED cannot erase an unacquired exact original; read it or give a grounded exclusion')
    if row['status']=='RESOLVED':
        for goal in goals:
            expected=goal.get('expected',[])
            if expected and not any(pages[ref]['document_id']==goal['document_id'] and any(
                str(span['block_id'])==str(want['block_id']) and span['start_cp']<want['end_cp'] and want['start_cp']<span['end_cp']
                for span in pages[ref]['spans'] for want in expected) for ref in refs):
                raise ProposalError('RESOLVED basis must include this exact target original; another document is insufficient')


def close_gaps(inv,data,value):
    if not enabled(inv):return
    st=state(inv,data)
    for row in value.get('gap_resolutions',[]):
        if row['status'] not in ('RESOLVED','NOT_NEEDED'):continue
        validate_gap_closure(inv,data,row)
        for goal in st.get('source_goals',[]):
            if goal.get('origin_gap_id')!=row['gap_id']:continue
            if row['status']=='NOT_NEEDED':goal['status']='EXCLUDED';goal['exclusion']=deepcopy(row)
            goal['resolution']=deepcopy(row)
    commit(inv,st)


def public_options(data,actions):
    return [{'document_ref':r['document_id'],'name':r['document_name']} for r in options(data,actions)]

def from_goal_id(inv,data,actions,goal_id):
    goal=next((g for g in state(inv,data).get('source_goals',[]) if g['goal_id']==goal_id and g['status'] in ('REQUIRED','BLOCKED')),None)
    if goal is None:raise ProposalError('source goal is not currently offered')
    validate_scope(goal.get('coordinate_scope'),persisted=True)
    common={'issue_id':goal['issue_id'],'missing_need':goal['reason'],'relation':'DIRECT','source_ref':None}
    reads=[k for k,a in actions.items() if a['action']=='READ_ARTICLES' and matches(inv,a['identity'],goal)]
    if len(reads)==1 and 'READ' not in goal['routes']:
        return native_decision(inv,data,actions,{'choice':'READ','selections':[dict(common,target=reads[0])]})
    lookups=[k for k,a in actions.items() if a['action']=='SEARCH_STRUCTURE' and a['identity'].get('document_id')==goal['document_id']]
    if lookups and 'LOOKUP' not in goal['routes']:
        return native_decision(inv,data,actions,dict(common,choice='LOCATE',target=lookups[0],structure_filter={'coordinate':goal['coordinate'],'coordinate_scope':goal['coordinate_scope'],'title':''}))
    raise ProposalError('source goal has no remaining authorized exact route; retain UNRESOLVED')


def pair_expected(session,binding,pair):
    if not binding.get('expected'):return []
    from .unit_reading import blocks
    wanted=set(map(str,blocks(session,pair['document_id'],str(pair['unit_id']),'subtree')))
    return [deepcopy(x) for x in binding.get('expected',[]) if x['document_id']==pair['document_id'] and str(x['block_id']) in wanted]


def grant_required_targets(session,checkpoint,*,restore=False):
    """A verified reference endpoint may supply its required enclosing unit.

    This never adds a searchable document, crosses a canonical source, overrides
    explicit exclusions, or treats the model's locator as an ACL grant.
    """
    from . import query_scope as qs,request_repair as rr
    if not qs.active(session):return
    gaps=list(checkpoint.get('assessment_gaps',[]))
    if restore:
        gaps.extend(g for r in checkpoint.get('gap_rounds',[]) for g in r['gaps'])
    saved=checkpoint.get('scope_read_grants',{})
    for gap in gaps:
        binding=gap.get('target_binding',{})
        if not gap.get('material') or gap.get('kind')=='MISSING_FACT' or binding.get('status')!='EXACT':continue
        witness_hash=digest(gap)
        if restore and not any(w.get('kind')=='REQUIRED_CONNECTED_TARGET' and w.get('gap_hash')==witness_hash for rows in saved.values() for w in rows.values()):continue
        # Rebind against the request's current authorized generation and index.
        current=rr.bind_gap(gap,session)
        if current['target_binding_hash']!=gap['target_binding_hash'] or current['target_binding']!=binding:
            raise ContractError('required target binding changed')
        for pair in binding['pairs']:
            did=pair['document_id'];uid=pair['unit_id']
            if uid is None or qs.direct(session,did,uid):continue
            try:qs.check_selection_exclusions(session.matcher,[{'document_id':did,'unit_id':uid}],qs.active(session).get('selections',[]))
            except qs.UnresolvedScope:continue
            expected=pair_expected(session,binding,pair);ids={str(x['block_id']) for x in expected}
            sources=[sid for sid in binding['source_ids'] if session.tools.sources[sid]['document_id']==did and ids <= {str(b['block_id']) for b in session.tools.sources[sid]['blocks']}]
            if len(sources)!=1 or not ids:continue
            sid=sources[0];grants=session.scope_read_grants.get(sid,{})
            anchors={bid:w for bid,w in grants.items() if bid in ids and w.get('reference_id')}
            if not anchors:continue
            fresh=ids-qs.permitted_blocks(session,sid)
            if fresh:qs.grant(session,sid,fresh,witness={'kind':'REQUIRED_CONNECTED_TARGET','gap_hash':witness_hash,
                'gap_id':gap['gap_id'],'target_unit_id':uid,'binding_hash':gap['target_binding_hash'],
                'reference_ids':sorted({w['reference_id'] for w in anchors.values()})})


def pending_before_selection(inv):
    """Only durable exact goals can precede model/no-progress handoff."""
    if not enabled(inv):return False
    goals=[]
    from .investigation_supervisor import seal
    for st in inv.p.get('investigation_supervisor',{}).values():
        if st.get('state_hash')!=seal(st):raise ContractError('source goal priority state changed')
        goals.extend(st.get('source_goals',[]))
    if any(g['status'] in ('REQUIRED','BLOCKED') for g in goals):return True
    for gap in inv.p.get('assessment_gaps',[]):
        if not gap.get('material') or gap.get('kind')=='MISSING_FACT' or gap.get('target_binding',{}).get('status')!='EXACT':continue
        for pair in gap['target_binding']['pairs']:
            node=inv.s.matcher.units.get((pair['document_id'],str(pair['unit_id'])))
            if node and node.get('coordinate_scope'):
                identity=digest([gap['issue_id'],pair['document_id'],pair['coordinate'],node['coordinate_scope']])
                if not any(g['identity']==identity and g['status'] in ('ACQUIRED','EXCLUDED') for g in goals):return True
    return False
