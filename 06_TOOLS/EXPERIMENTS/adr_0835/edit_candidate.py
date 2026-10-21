from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0835/connected/snapshot';W=S/'02_BACKEND/workflow'
p=W/'risk_team_compare_workflow/task_board.py';s=p.read_text()
s=s.replace("            if row['text'].strip() and not row['citations']:raise ValueError('finding requires actual original')\n",'')
s=s.replace("            if row['status']=='CONFIRMED' and (not row['citations'] or not row['scope_sufficient'] or row['missing']):raise ValueError('confirmed field requires receipts and reviewed dependency closure')\n", "            if row['status']=='CONFIRMED' and not row['citations']:raise ValueError('confirmed field requires a read original')\n")
s=s.replace("            if row['status']=='MISSING' and (row['text'] or row['citations'] or row['scope_sufficient']):raise ValueError('missing is not a finding')\n",'')
s=s.replace("            if row['scope_sufficient'] and not row['citations']:raise ValueError('scope coverage needs read originals')\n",'')
s=s.replace("        if item['content_status']!='UNKNOWN' and any(item[side]['status'] in ('MISSING','CONFLICT') for side in ('internal','external')):raise ValueError('missing or conflicting fields cannot establish a content match')\n",'')
s=s.replace("            if item[task['side']]['status']=='CONFIRMED':raise ValueError('do not research an already complete field')\n",'')
s=s.replace("                '미확보는 MISSING, 일부만 확인되면 PARTIAL, 충돌은 양쪽 문구를 보존해 CONFLICT다. CONFIRMED는 해당 항목의 필요한 범위가 실제 읽힌 경우만 가능하다. '","                '상태와 충분성은 원문을 보고 판단한다. 미확보 이유도 text에 설명할 수 있다. MISSING은 확인하지 못했다는 뜻이며 규정 부재의 증명은 아니다. '")
s=s.replace("                '이미 확인한 자료는 previous에 보존돼 있다. 서로 다른 결과는 충돌과 원문을 보존한다. 조회 실패는 규정 부재가 아니다.'", "                '이전 확인은 previous에 있다. 문장 표현만 달라진 것은 충돌이 아니다. 의미가 양립할 수 없을 때만 CONFLICT로 판단하라. '")
s=s.replace("                            item[side].update(status='CONFLICT',scope_sufficient=False,missing='; '.join(filter(None,[new['missing'],'이전 확인과 다른 문구: 양쪽 원문 재검토 필요'])))\n",'')
s=s.replace("                    if any(item[s]['status'] in ('MISSING','CONFLICT') for s in ('internal','external')):item.update(content_status='UNKNOWN',difference='')\n",'')
s=s.replace("                    # Lossless retention, never last-failure-wins. Changed claims\n                    # remain alternatives pending semantic conflict resolution.","                    # Preserve earlier evidence without inferring a semantic\n                    # conflict from changed wording. The LLM owns that judgment.")
s=s.replace("' / 이전 확인(재검토): '","' / 이전 확인: '")
s=s.replace("        items.append({'issue_id':row['issue_id'],**current,'legal_assessment':'아래 별도 근거 관계·적용성 검토 참조'})", "        items.append({'issue_id':row['issue_id'],**current,'legal_assessment':'LLM 검토 의견 — 근거와 함께 사용자 검토 가능'})")
p.write_text(s)
p=W/'risk_team_compare_workflow/basis.py';s=p.read_text()
a=s.index('        if app[\'status\']==\'MATCH\':');b=s.index('        path=pair[\'basis_path\']',a);s=s[:a]+s[b:]
a=s.index("            target=sources[edge['to_evidence']]");b=s.index('    for gap in value[\'gaps\']:',a)
s=s[:a]+'''        # Relation, applicability and material sufficiency are model judgments.
        # Exact witnesses/endpoints remain checked; no inferred legal approval.
'''+s[b:]
a=s.index("            if any(p['comparison_eligibility'] and p['issue_id'] in blocked");b=s.index("            if {'internal','external'}",a);s=s[:a]+s[b:]
s=s.replace("            'dependency_closure_complete=false이면 전체 조건을 검토한 것으로 판정하지 마라. '\n            'child_gap_constraints.blocked_issue_ids에 있는 쟁점의 comparison_eligibility는 false다. '\n            '자식에 남은 핵심 부족은 시스템이 보존하며 부모가 삭제하거나 해결된 것으로 바꿀 수 없다. 영향이 없는 독립 쟁점은 따로 판단하라. '","            '자식의 부족 기록과 원문 범위를 참고해 비교 가능 여부를 직접 판단한다. 부족 기록이 남았다는 이유만으로 모든 내용 비교를 보류하지 않는다. '")
s=s.replace("            '유사 내용은 CONTENT_ONLY. 기준일·판본 미확인이어도 내용 비교 짝을 남기고 applicability=UNKNOWN, comparison_eligibility=false로 표시하라. '", "            '명시 인용 없이 내용이 대응하면 CONTENT_ONLY로 비교할 수 있다. 기준일·판본 미확인은 applicability에 설명한다. '")
p.write_text(s)
p=W/'risk_team_compare_workflow/compare.py';s=p.read_text();a=s.index("        if row['verdict']!='DEFERRED':");b=s.index('\n\ndef deferred',a)
s=s[:a]+'''        if row['verdict']!='DEFERRED' and (
                not citations.intersection(pair['internal']) or not citations.intersection(pair['external'])):
            raise ValueError('substantive judgment needs both original sides')
        for dimension in row['dimensions']:
            check_citations(dimension['citations'],sources)
            if {c['evidence'] for c in dimension['citations']}-set(pair['internal']+pair['external']):
                raise ValueError('dimension cites evidence outside assessed pair')
        # Scope, exceptions, numerical meaning and the verdict are the LLM's
        # review. An incomplete inventory is not a reason to discard that review.
'''+s[b:]
a=s.index("            elif not data['packet']['dependency_closure_complete']:");b=s.index('            else:\n                try:',a);s=s[:a]+s[b:]
a=s.index("                        '제시된 한 쌍을 비교하라.");b=s.index("checked)",a)+len('checked)')
s=s[:a]+'''                        '양쪽 원문을 비교해 사용자가 검토할 수 있는 판단과 이유를 작성하라. '
                        '근거 관계, 적용 범위, 기존 부족 기록은 참고 사항이며 의미 판단은 직접 한다. '
                        '명시 인용 관계가 없어도 내용상 대응하는 규정은 비교할 수 있다. '
                        '수치는 이번 판단에 필요한 차원만 검토한다. 확인되지 않은 조건·예외·판본은 이유나 unresolved에 남긴다. '
                        '확인한 범위에서 부합/내부 추가기준/상충/미비 후보를 판단하고, 판단 자체가 어려울 때만 DEFERRED로 둔다. '
                        '문구 차이 자체는 상충이 아니다. 미확보를 규정 부재로 단정하지 않는다. '
                        'citations에는 실제 제공된 양측 원문을 선택한다. DEFERRED여도 이해 가능한 설명을 남긴다.',checked)'''+s[b:]
a=s.index('                else:\n                    if any(row[\'verdict\']==\'DEFERRED\'');b=s.index("            progress['completed'][key]",a);s=s[:a]+s[b:]
p.write_text(s)
p=W/'risk_team_compare_workflow/report.py';s=p.read_text();a=s.index('    substantive=');b=s.index('    display_basis[\'summary\']',a);s=s[:a]+'''    # Keep the model's explanation even when it defers. Exact source cards and
    # immutable proposals make that review inspectable without regenerating it.
'''+s[b:]
s=s.replace("lines=[('확인된 '+str(confirmed)+'개 비교 항목의 결과입니다.' if confirmed else", "lines=[('LLM이 검토한 '+str(confirmed)+'개 비교 항목의 결과입니다.' if confirmed else")
s=s.replace("            'report':", "            'report':")
p.write_text(s)
p=W/'adapters/projection.py';s=p.read_text().replace("VERSION = 'workflow-mechanical-projection-v4'", "VERSION = 'workflow-mechanical-projection-v5'")
a=s.index('            if numeric:\n');b=s.index('        if stage==\'COMPARE\' and',a)
s=s[:a]+'''            # Numerical dimensions are optional observations, not a mandatory
            # ten-way checklist. Non-numeric rows keep an empty host-owned list.
            result['required'].remove('dimensions')
            if not numeric:props['dimensions']['maxItems']=0
        if stage=='ITEMS' and set(props)=={'status','text','citations','dependencies','scope_sufficient','missing'}:
            for name in ('dependencies','scope_sufficient'):
                props.pop(name);result['required'].remove(name)
        if stage=='ITEMS' and 'anchor_ids' in props and 'locator_id' in props:
            props.pop('anchor_ids');result['required'].remove('anchor_ids')
            props['locator_id']['enum']=[*data.get('locators',{}),None]
        if stage=='ITEMS' and 'field' in props and data.get('fields'):
            props['field']['enum']=list(data['fields'])
'''+s[b:]
a=s.index('                if numeric:\n',s.index('    def expand('));b=s.index("        if stage=='BASIS':",a)
s=s[:a]+'''                row.setdefault('dimensions',[])
        if stage=='ITEMS':
            for item in result['items']:
                for side in ('internal','external'):
                    item[side]['dependencies']=[]
                    item[side]['scope_sufficient']=item[side]['status']=='CONFIRMED'
                for task in item['next_tasks']:
                    locator=data.get('locators',{}).get(task['locator_id']) if task['locator_id'] else None
                    origin=locator.get('origin_evidence_id') if locator else None
                    task['anchor_ids']=[origin] if origin in source_ids else []
'''+s[b:]
p.write_text(s)
print('Edited candidate only: semantic gates, ID projection, optional dimensions, model explanation preservation')
