from pathlib import Path
R=Path.cwd();P=R/'02_BACKEND/lawrag/research/candidates/adr_0454/routed/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime';B=R/'02_BACKEND/lawrag/research/candidates/adr_0455/repaired/snapshot/02_BACKEND/semantic_runtime';B.mkdir(parents=True,exist_ok=True)
s=(P/'routed_navigation.py').read_text()
s=s.replace('사용 가능한 첫 단계 행동은', '검증 실패를 받으면 last_results의 error와 repair_instruction을 반영해 한 번 수정한다. scope=current는 이 대화에 이미 허용된 모든 문서를 그대로 검색한다는 뜻이다. 범위 지정이 없는 내용 질문에는 current를 쓴다. all은 사용자가 전체 문서 목록을 명시했을 때만 쓴다. 매핑 제안은 검색 작업이 아니며 대상 bindings가 범위를 정한다. 빈 후보 조회를 같은 인수로 반복하지 말고 뜻을 확인한다.\n사용 가능한 첫 단계 행동은')
s=s.replace('resolved=None\n','resolved=None;lookup_seen={};empty_lookups=0;repairs=0\n',1)
s=s.replace("'last_results':route_cards(trace[-1:])", "'last_results':route_cards(trace[-1:]),'repair_instruction':'이전 오류가 있으면 그 오류를 바로잡은 해석을 제출하세요. scope=current는 기존 허용 범위를 유지합니다. 빈 조회 반복은 금지합니다.'")
a=s.index("                if action['tool']=='LOOKUP_ENTITIES':");b=s.index('                args=normalized_scope',a)
s=s[:a]+'''                if action['tool']=='LOOKUP_ENTITIES':
                    key=(args['type'],folders.normalized(args['query']),args.get('offset',0))
                    if key in lookup_seen:
                        resolved={'intent':'clarify','clarification':'요청한 표현의 대상을 확인하지 못했습니다. 어떤 폴더·문서·용어를 뜻하는지 알려 주세요.'}
                        trace.append({**action,'status':'OK','result':{'repeated_lookup_stopped':True,'content_read':False}});break
                    result=registry.lookup(args['type'],args['query'],args.get('offset',0));lookup_seen[key]=result
                    if not result['items']:empty_lookups+=1
                    trace.append({**action,'status':'OK','result':result})
                    if empty_lookups>=3:
                        resolved={'intent':'clarify','clarification':'저장된 이름에서 요청한 표현을 찾지 못했습니다. 해당 폴더·문서·용어의 이름을 알려 주세요.'};break
                    continue
''' +s[b:]
a=s.index("                args=normalized_scope");b=s.index('                # Validate the complete interpretation',a)
block=s[a:b]
block=block.replace("                if leaves:\n", "                if leaves and args['intent']!='mapping':\n")
block=block.replace("전체 범위 요청이 확인되지 않았습니다. 폴더·문서를 선택해 주세요.", "명시적인 전체 목록 요청이 아닙니다. 범위를 지정하지 않은 내용 질문이면 scope=current로 기존 허용 범위를 유지하세요. 폴더·문서를 명시했다면 해당 handle 배열을 선택하세요.")
# One semantic repair; full validation precedes every ledger mutation.
s=s[:a]+"                try:\n"+''.join('    '+line+'\n' for line in block.splitlines())+'''                except ValueError as exc:
                    if repairs>=1:raise
                    repairs+=1;scope=list(authorized);resolved=None
                    trace.append({**action,'status':'REJECTED','error':str(exc),'result':{'repair_allowed':True,'content_read':False}})
                    continue
''' +s[b:]
s=s.replace("state.update(interpretation=resolved,", "state.update(interpretation_repairs=repairs,metadata_lookup_count=len(lookup_seen),interpretation=resolved,")
(B/'repaired_navigation.py').write_text(s);(B/'compact_handles.py').write_text((P/'compact_handles.py').read_text())
s=(P/'expression_probe_binding.py').read_text().replace("arm=='routed'","arm=='repaired'");(B/'expression_probe_binding.py').write_text(s)
# Parent load returns parent454 plus its451 baseline; only parent454 is baseline here.
s=(R/'06_TOOLS/EXPERIMENTS/adr_0454/runtime.py').read_text();s=s.replace('adr_0454/routed','adr_0455/repaired').replace('ADR-0454-robust-routing-short-handles','ADR-0455-routing-validation-repair').replace("ARMS=['baseline','routed']","ARMS=['baseline','repaired']")
a=s.index(" p=R/'06_TOOLS/EXPERIMENTS/adr_0451/runtime.py'");b=s.index(" path=C/'snapshot'",a)
s=s[:a]+''' p=R/'06_TOOLS/EXPERIMENTS/adr_0454/runtime.py';lock=read(R/'04_EXPERIMENTS/ADR/ADR-0454-robust-routing-short-handles/artifacts/input-lock.json')['files'];assert sha(p)==lock[rel(p)]
 spec=importlib.util.spec_from_file_location('parent454_runtime',p);parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent);mod,old,multi,mods,root,_=parent.load()
''' +s[b:]
s=s.replace("'routed_navigation'","'repaired_navigation'").replace("'probe454binding'","'probe455binding'").replace('synthetic-expression-routing-454','synthetic-expression-routing-455')
(R/'06_TOOLS/EXPERIMENTS/adr_0455/runtime.py').write_text(s)
