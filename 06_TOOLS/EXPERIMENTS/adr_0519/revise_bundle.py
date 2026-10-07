from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations';C=R/'02_BACKEND/lawrag/research/candidates/adr_0519/selection'
(A/'artifacts/frozen-design-before-bundle-correction.json').write_bytes((A/'artifacts/frozen-design.json').read_bytes())
p=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py';s=p.read_text()
s=s.replace('준용·위임·인용·역참조 등 연결로 회수한 원문은 시스템이 별도 보호한다. 연결 조문을 개별적으로','채택한 시작점에서 준용·위임·인용·역참조 등으로 연결되는 원문은 시스템이 함께 보호한다. 연결 조문을 개별적으로')
s=s.replace('한 조항이 시작점과 연결 조항을 겸하면 시작점으로 미선택하더라도 연결 원문으로 계속 보존된다.','시작점을 제외하면 그 시작점에만 연결된 원문도 함께 제외된다. 다른 채택 시작점에서 연결되는 공유 원문은 유지된다.\n한 조항을 시작점으로 미선택해도 다른 채택 시작점에서 연결되면 연결 원문으로 보존된다.')
pos=s.index('def preserve_result(')
s=s[:pos]+'''def root_bundles(record,chosen):
    """Reachability along recorded retrieval edges, with selected-root ownership.

    Retrieval direction anchor->candidate is not necessarily the legal citation
    direction. Native reference receipts keep the latter independently. Traverse
    cycles once; a shared source survives while any chosen root can reach it.
    """
    pool=set(record['read_complete']);adj=defaultdict(set)
    for target,routes in record['routes'].items():
        for route in routes:
            if route.get('anchor'):adj[route['anchor']].add(target)
    owners=defaultdict(list);paths={};unacquired=set()
    for root in chosen:
        seen={root};queue=[root];predecessor={root:None}
        for source in queue:
            for target in sorted(adj[source]):
                if target not in seen:
                    seen.add(target);queue.append(target);predecessor[target]=source
        paths[root]=predecessor
        for sid in sorted(seen):
            if sid in pool:owners[sid].append(root)
            else:unacquired.add(sid)
    return {'selected_root_owners':dict(owners),'root_reachability_paths':paths,
            'reachable_acquired_ids':[s for s in record['read_complete'] if s in owners],
            'reachable_unacquired_ids':sorted(unacquired)}


'''+s[pos:]
s=s.replace("pool=list(dict.fromkeys(record['read_complete']));protected=partition['protected_ids']", "pool=list(dict.fromkeys(record['read_complete']))\n    bundles=root_bundles(record,chosen if not error else partition['root_ids'])\n    reachable=bundles['reachable_acquired_ids']\n    protected=[s for s in reachable if s not in chosen]")
s=s.replace("final=pool if error else [s for s in pool if s in set(chosen)|set(protected)]", "final=pool if error else reachable")
s=s.replace("    assert not ((set(pool)-set(final)) & set(partition['linked_ids']))", "    assert error or set(final)==set(chosen)|set(protected)")
s=s.replace("result={**partition,'all_source_ids':pool", "result={**partition,**bundles,'protected_ids':protected,'retained_linked_ids':[s for s in final if s not in chosen], 'all_source_ids':pool")
s=s.replace("'direct_root_not_selected_no_relation_path'", "'no_remaining_selected_root_reaches_source'")
s=s.replace("for s in partition['linked_ids']}", "for s in final if s in partition['linked_ids']}")
s=s.replace("'protected_as_linked':sid in part['linked_ids']", "'also_retrieved_by_link':sid in part['linked_ids']")
s=s.replace("'protected_linked_count':len(part['linked_ids']),", "'available_linked_count':len(part['linked_ids']),")
s=s.replace("'unclassified_preserved_count':len(part['unclassified_ids'])", "'unclassified_unassigned_count':len(part['unclassified_ids'])")
s=s.replace("'사용할 첫 시작점만 선택하라. 연결 회수 원문은 별도 자동 보호되며 개별 제거 대상이 아니다.'", "'사용할 첫 시작점만 선택하라. 채택 시작점의 연결 원문은 함께 보호된다. 제외 시작점에만 연결된 원문은 함께 제외된다.'")
s=s.replace("'연결 회수 원문: 개별 제거 대상에서 제외'", "'채택 시작점에서 연결됨: 개별 제거 대상에서 제외'")
s=s.replace("c['protected_as_linked']=sid in part['linked_ids'];c['protection_status']='LINKED' if sid in part['linked_ids'] else 'UNCLASSIFIED' if sid in part['unclassified_ids'] else 'ROOT'", "c['protected_as_linked']=sid in result['retained_linked_ids'];c['protection_status']='ROOT' if sid in chosen else 'LINKED';c['selected_root_owners']=result['selected_root_owners'].get(sid,[])")
s=s.replace("appendix['protected_linked_count']=len(part['linked_ids'])", "appendix['protected_linked_count']=len(result['retained_linked_ids'])")
s=s.replace("str(len(part['linked_ids']))+'개 / 중복 제거 후 전체 '", "str(len(result['retained_linked_ids']))+'개 / 중복 제거 후 전체 '")
p.write_text(s)
m=json.loads((A/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']='Select starting roots; preserve all linked originals reachable from any selected root; removing a root removes only exclusively owned descendants. Shared descendants survive. No individual child pruning.'
m['design']['hypothesis']='Root-bundle selection preserves complete acquired relation branches for chosen roots and drops only unselected-root-exclusive branches; no independent linked-source deletion.'
m['design']['success_criteria']='90/90 required originals retained; all acquired nodes reachable from any chosen root preserved (protected loss0); removed-root-exclusive descendants absent; shared descendants retained;no source/scope/witness corruption;errors0;composed p95<=240s. No count target.'
m['design']['failure_criteria']='Required original loss, dropping a reachable node, retaining an orphaned branch as if selected,source mutation or model error. On failure all originals preserved with explicit DEGRADED status,not a successful root selection.'
m['design']['arms'][1]['changes']='One Gemma call selects direct search roots with320char original excerpts. Directed reachability over recorded anchor->candidate retrieval edges builds each selected root bundle. Keep union of reachable acquired nodes; remove exclusively unselected-root branches; cycles deduplicated/shared nodes retained. Unresolved edges retain unconfirmed status. Error preserves whole pool as degraded. No fresh corpus-wide retrieval.'
m['design']['retrieval_stage_plan']['stages_by_arm']['selection']=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'root_candidates','kind':'filter','parent_stage_ids':['acquired']},{'stage_id':'root_selection','kind':'select','parent_stage_ids':['root_candidates']},{'stage_id':'bundle_expansion','kind':'expand','parent_stage_ids':['root_selection']},{'stage_id':'final_pool','kind':'present','parent_stage_ids':['bundle_expansion']}]
polp=A/'artifacts/gemma-policy.json';pol=json.loads(polp.read_text());pol['authorization'].update(scope='Public61 root-bundle selection;max61 Gemma calls; protect selected-root reachable originals; remove exclusively unselected-root branches;MAIN unchanged',latest_steering='연결 조문은 개별 제거하지 않음;시작점이 없어지면 그 연결된 조문들도 제시 불필요;공유 연결은 채택 시작점이 남으면 보존')
polp.write_text(json.dumps(pol,ensure_ascii=False,indent=2)+'\n');ph=hashlib.sha256(polp.read_bytes()).hexdigest();m['llm_policy']['experiment_override']['policy_sha256']=ph;m['gemma_binding']['policy_sha256']=ph
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
gp=A/'artifacts/export-rebinding.json';g=json.loads(gp.read_text());g['policy_sha256']=ph;gp.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
with (A/'PLAN.md').open('a') as f:f.write('\n## 사용자 최종 정정 — 첫 모델 호출 전\n\n이 절이 앞선 모든 연결 무조건 보존 설계를 대체한다. 시작점이 제외되면 그 시작점에만 연결된 원문도 제외한다. 선택 시작점의 연결 원문만 전부 보호하며 공유 원문은 선택 시작점 중 하나라도 닿으면 보존한다. 실제 모델 호출0회. 이전 rev001은 미실행 설계로 보존한다.\n\n'+json.dumps(m['design'],ensure_ascii=False,indent=2)+'\n')
print('Corrected to root bundles;no model calls yet.')
