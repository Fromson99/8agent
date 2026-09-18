from pathlib import Path
R=Path.cwd();T=R/'06_TOOLS/EXPERIMENTS/adr_0454';P=R/'06_TOOLS/EXPERIMENTS/adr_0452';B=R/'02_BACKEND/lawrag/research/candidates/adr_0454/routed/snapshot/02_BACKEND/semantic_runtime'
for f in ['fixtures.py','runtime.py','run_probe.py','score.py','finalize.py']:
 s=(P/f).read_text().replace('adr_0452','adr_0454').replace('ADR-0452','ADR-0454').replace('gemini-expression-routing-probe','robust-routing-short-handles').replace('452','454')
 if f!='fixtures.py':s=s.replace("'mapped'","'routed'").replace('metrics[\'routed\']','metrics[\'routed\']')
 if f=='runtime.py':
  s=s.replace('def load():','def load(frozen=True):')
  a=s.index(" cm=read(C/'candidate.json')");b=s.index('\ndef build',a)
  s=s[:a]+''' path=C/'snapshot'
 if frozen:
  cm=read(C/'candidate.json');rev=cm['revisions'][-1]
  for f in rev['files']:assert sha(R/f['frozen_path'])==f['snapshot_sha256']
  path=C/'revisions'/rev['revision_id']/'snapshot'
 package=mod.__package__
 for name in ['compact_handles','routed_navigation']:
  spec=importlib.util.spec_from_file_location(package+'.'+name,path/'02_BACKEND/semantic_runtime'/f'{name}.py');loaded=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loaded;spec.loader.exec_module(loaded)
 routed=loaded
 spec=importlib.util.spec_from_file_location('probe454binding',path/'02_BACKEND/semantic_runtime/expression_probe_binding.py');binding=importlib.util.module_from_spec(spec);spec.loader.exec_module(binding)
 return routed,mod,multi,mods,root,binding

''' +s[b:]
 elif f=='score.py':
  s=s.replace("'metadata_total':14","'metadata_total':16").replace("sorted(counts)[math.ceil(len(counts)*.95)-1]","sorted(counts)[round((len(counts)-1)*.95)]")
  a=s.index(" ok=summary[");b=s.index('\n drift=',a)
  s=s[:a]+" ok=summary['routed']['metadata_pass']==16 and not [x for x in comparison['baseline_only_regressions'] if metrics['routed'][x]['kind']!='content'] and all(not x['invalid_quotes'] and not x['scope_escapes'] and not x['failure'] for x in metrics['routed'].values())"+s[b:]
  s=s.replace('14 metadata/mapping','16 metadata/mapping')
 elif f=='finalize.py':
  s=s.replace('## 6. 중간 LLM 호출 — 해석/도구/판단','## 6. 중간 LLM 호출 — router/compiler/verifier/repair')
  s=s.replace("/16, 목록·매핑 {v['metadata_pass']}/14", "/18, 목록·매핑 {v['metadata_pass']}/16")
  s=s.replace('모의16질문','모의18질문').replace('문서/매핑14개','문서/매핑16개')
  s=s.replace('baseline(ADR0450 상속 클래스), mapped(ADR0451)','baseline(ADR0451 mapped), routed(ADR0454)')
  s=s.replace('| 기존 typed | 새 mapped |','| 기존 mapped | 수정 routed |')
 (T/f).write_text(s)
s=(R/'02_BACKEND/lawrag/research/candidates/adr_0452/mapped/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/expression_probe_binding.py').read_text().replace("arm=='mapped'","arm=='routed'").replace('typed.TypedAgent(pipeline,glossary,None,matcher,limits)','typed.MappedAgent(pipeline,glossary,None,matcher,limits,ledger=ledger,actor=\'synthetic-user\')');(B/'expression_probe_binding.py').write_text(s)
