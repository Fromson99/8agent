from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0841/direct/snapshot'
def edit(n,f):
 p=S/n;s=p.read_text();p.write_text(f(s))
def replace(s,a,b):
 assert a in s,a[:100];return s.replace(a,b)
p=S/'02_BACKEND/workflow/risk_team_compare_workflow/basis.py'
p.write_text(p.read_text()+'''

def from_items(ctx,state):
    """Route field-selected originals to comparison, without another approval."""
    from ..presentation import evidence
    from ..contracts import digest
    sources=evidence(ctx,state);by=evidence_map(sources);pairs=[];gaps=[]
    for issue in state['scope']['issues']:
        selected={'internal':[],'external':[]}
        for row in state['task_board']['rows'].values():
            if row['issue_id']!=issue['id'] or not row['current']:continue
            for side in selected:
                value=row['current'][side]
                # Earlier grounded observations survive a later incomplete review.
                for observation in [value]+value.get('alternatives',[]):
                    citations=observation['citations']+observation['dependencies']
                    check_citations(citations,by)
                    check_sides(list(dict.fromkeys(c['evidence'] for c in citations)),side,by)
                    selected[side].extend(c for c in citations if c not in selected[side])
                if value.get('missing'):
                    gaps.append({'issue_id':issue['id'],'kind':'PARTIAL_PROVISION',
                        'reason':side+' / '+row['field']+': '+value['missing'],'action':None})
        if not all(selected.values()):continue
        pairs.append({'pair_id':'items-'+digest(issue['id'])[:24],'issue_id':issue['id'],
            **{side:list(dict.fromkeys(c['evidence'] for c in selected[side])) for side in selected},
            'applicability':{'status':'UNKNOWN','reason':'적용 범위와 의미는 비교 단계에서 검토합니다.','citations':[],'as_of':ctx.request['as_of']},
            'basis_relation':'CONTENT_ONLY','basis_path':[],'comparison_eligibility':True,
            'reason':'항목 검토에서 선택한 양측 원문입니다. 실제 대응 관계와 차이는 직접 판단합니다.',
            'content_difference':'','content_citations':selected['internal']+selected['external']})
    inherited=child_gap_requirements(state)
    state['basis_child_gaps']=inherited['audit']
    # Keep child shortages as observations, not a second permission gate.
    for row in inherited['audit']:
        original=row['original_gap']
        for issue in row['parent_issue_refs']:
            gap={'issue_id':issue,'kind':'PARTIAL_PROVISION',
                'reason':row['side']+' 조사 메모: '+str(original.get('reason') or original.get('missing_target') or '미확인 사항'), 'action':None}
            if gap not in gaps:gaps.append(gap)
    result={'pairs':pairs,'gaps':gaps,'summary':'항목별로 선택한 원문을 직접 비교합니다. 미확인 사항은 판단의 한계로 남깁니다.'}
    validate(result,sources,state['scope']['issues'],ctx.request['as_of'])
    ctx.repo.save(state)
    return result
''')
edit('02_BACKEND/workflow/risk_team_compare_workflow/task_board.py',lambda s:replace(s,"state['basis']=basis.assess(ctx,state)","state['basis']=basis.from_items(ctx,state)"))
# Remove administrative completeness requirements in modern navigation only.
n='02_BACKEND/semantic_runtime/legal_agent/law_navigation.py'
s=(S/n).read_text()
s=replace(s,"    completion = bool(view.get('completion_contract'))","    completion = bool(view.get('completion_contract'))\n    modern = view.get('completion_contract') in (cc.V5,cc.V6,cc.V7,cc.V8)")
s=s.replace("kind in INVESTIGATIVE_ACTIONS and len(gaps) > 1", "not modern and kind in INVESTIGATIVE_ACTIONS and len(gaps) > 1")
s=replace(s,"**({'minItems': len(gaps), 'maxItems': len(gaps)} if kind == 'FINISH' else {'maxItems': 0})", "**({'minItems': 0 if modern else len(gaps), 'maxItems': len(gaps)} if kind == 'FINISH' else {'maxItems': 0})")
s=replace(s,"            if not active:\n                raise output.OutputContractError", "            if not active and not self.modern:\n                raise output.OutputContractError")
s=replace(s,"            if not any(b.get('branch_id') in active and b['id'] in value['basis_refs'] for b in data['basis']):", "            if not self.modern and not any(b.get('branch_id') in active and b['id'] in value['basis_refs'] for b in data['basis']):")
s=replace(s,"            if self.completion and self.control:\n                self.coverage_gate(value, data)","            if self.completion and self.control and not self.modern:\n                self.coverage_gate(value, data)")
s=replace(s,"        if kind == 'FINISH':\n            if not active", "        if kind == 'FINISH':\n            if self.modern:\n                explicit={b['branch_id'] for b in data['basis'] if b.get('branch_id') and b['id'] in value['basis_refs']}\n                updates={r['branch_id']:r['status'] for r in value['branch_decisions']}\n                if any(updates.get(g) in ('DEFER','EXCLUDE') or (g not in updates and self.p['groups'][g]['status'] in ('DEFERRED','EXCLUDED')) for g in explicit):\n                    raise ProposalError('FINISH selects an explicitly deferred or excluded original')\n            if not active")
s=replace(s,"        if decision['next_action']=='FINISH' and self.control:\n            self.p['uncovered_issues']", "        if decision['next_action']=='FINISH' and self.control:\n            if self.modern:self.p['completion_basis_refs']=list(decision['basis_refs'])\n            self.p['uncovered_issues']")
s=replace(s,"            current=inventory.originals_for(self.s,self.p)", "            current=inventory.originals_for(self.s,self.p,self.p.get('completion_basis_refs',[]) if sufficient else [])\n            if self.modern and self.p.get('completion_basis_refs') and sufficient:\n                selected_ids={ident for original in current for ident in original['evidence_ids']}\n                evidence=list({e['evidence_id']:e for record in self.read_records().values() for e in record['evidence'] if e['evidence_id'] in selected_ids}.values())\n                result.update(selected_evidence=evidence,final_evidence_ids=[e['evidence_id'] for e in evidence],\n                    final_packets=[{'packet_id':'law-finish-selected','evidence':evidence}])")
# Modern prompts override legacy contracts without altering their old behavior.
s=replace(s,"        if self.modern:\n            system+='\\n gap_targets", "        if self.modern:\n            system=system.replace('FINISH는 이번 결정 반영 뒤 ADOPT/KEEP 원문이 하나 이상 남고 그 basis_refs를 인용할 때만 가능하다. evidence_sufficient=false는 일부 부족을 뜻하며 채택 0개 종료를 허용하지 않는다. 모두 보류라면 제공 조사 행동이나 PENDING을 선택한다. 근거를 억지로 채택하지 않는다.', 'FINISH는 실제 전달받은 원문 basis_refs를 선택하면 된다. 별도의 ADOPT 기록은 필수가 아니다. 충분성·의미 판단은 후속 검토에서 하며 부분 근거도 전달한다.')\n            system+='\\n 이 계약에서는 gap_ids와 gap_resolutions는 선택 사항이다. 비어 있어도 유효한 원문 읽기와 FINISH를 허용한다. 빠진 부족 항목은 UNRESOLVED로 보존한다. 쟁점별 채택 수는 조사 안내이며 종료 승인 조건이 아니다.'\n            system+='\\n gap_targets")
s=replace(s,"        if self.modern:\n            system+='", "        if self.modern:\n            system+='",) if False else s
# Schema/view rule should match executable contract.
pos="            data['completion_rule'] = ("
idx=s.index(pos);end=s.index('\n',s.index("not establish legal absence",idx)) if 'not establish legal absence' in s[idx:idx+900] else None
# Insert after the complete completion-rule assignment by finding next statement.
needle="        if self.completion:"
# Actual view ends later; explicit modern override before returning view below.
viewreturn=s.index('        return data, actions',s.index('    def view('))
s=s[:viewreturn]+"        if self.modern:\n            data['completion_rule']='FINISH may select any delivered, non-excluded original basis_refs. Separate ADOPT metadata and full issue coverage are optional; missing gap resolutions remain UNRESOLVED.'\n            data['reading_rule']='READ/VIEW delivers originals without adoption. gap_ids is optional bookkeeping; valid scoped reads do not require it.'\n"+s[viewreturn:]
(S/n).write_text(s)
n='02_BACKEND/semantic_runtime/legal_agent/evidence_inventory.py';s=(S/n).read_text();s=replace(s,'def originals_for(session, state):','def originals_for(session, state, selected_refs=()):');s=replace(s,'    return _pack(session, state, sources, gathered)\n\n\ndef delivered_originals_for', '''    for ref in selected_refs:
        page=state['basis_history'].get(ref)
        if not page or not page.get('accepted') or not page.get('spans'):
            raise ContractError('completion original lacks an accepted delivery receipt')
        gid=page['branch_id'];group=state['groups'][gid]
        if gid not in state['selected'] or group['status'] in ('DEFERRED','EXCLUDED'):
            raise ContractError('completion selected a deferred or missing original')
        gathered[group['source_id']].extend(page['spans'])
        sources[group['source_id']]=state['selected'][gid]
    return _pack(session, state, sources, gathered)


def delivered_originals_for''');(S/n).write_text(s)
n='02_BACKEND/semantic_runtime/legal_agent/request_repair.py';s=(S/n).read_text();s=replace(s,"    if len(rows) != len(gaps) or {r['gap_id'] for r in rows} != set(gaps):\n        raise ProposalError('FINISH must address every open gap exactly once')", "    ids=[r['gap_id'] for r in rows]\n    if len(ids)!=len(set(ids)) or set(ids)-set(gaps):\n        raise ProposalError('gap resolutions must name unique known gaps')")
s=replace(s,"        if not refs or not refs <= adopted or not covers_target(gap['target_binding'], checked, refs):\n            raise ProposalError('RESOLVED requires adopted original spans covering this exact missing target; another article is insufficient')", "        delivered={ref for ref,page in checked.get('basis_history',{}).items() if page.get('accepted') and page.get('spans')}\n        if not refs or not refs <= delivered:\n            raise ProposalError('RESOLVED requires actual delivered original references; target sufficiency is the model judgment')")
s=replace(s,"a not in receipts or row['gap_id'] not in receipts[a]['gap_ids']", "a not in receipts or (receipts[a]['gap_ids'] and row['gap_id'] not in receipts[a]['gap_ids'])")
(S/n).write_text(s)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
print('implemented direct review and optional native bookkeeping')
