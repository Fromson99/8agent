from pathlib import Path
import json,subprocess,datetime
D=Path(__file__).resolve().parent;meta=json.loads((D/'session.json').read_text());P=Path(meta['package'])
previous=meta.get('status')!='prepared'
cmd=['/home/jin/.local/bin/claude','--print','--model','claude-opus-5-5','--effort','xhigh',('--resume' if previous else '--session-id'),meta['session_id'],'--name','MAIN50 불필요 탐색·반복 루프 설계','--permission-mode','plan','--permission-prompts','none','--tools','Read,Grep,Glob','--restricted','--safe-mode','--strict-mcp-config','--mcp-config',str(D/'mcp-empty.json'),'--output-format','stream-json','--verbose']
meta.update(status='running',started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,read_only=True);(D/'session.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
attempt=1
while (D/f'claude-output-attempt-{attempt:03}.jsonl').exists():attempt+=1
with (D/f'claude-output-attempt-{attempt:03}.jsonl').open('w') as out,(D/f'claude-stderr-attempt-{attempt:03}.log').open('w') as err:
 result=subprocess.run(cmd,input=(P/'REQUEST.md').read_text(),text=True,cwd=P,stdout=out,stderr=err)
meta.update(status='process_exited',exit_code=result.returncode,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(D/'session.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('Claude Code finished',result.returncode,'session',meta['session_id'])
raise SystemExit(result.returncode)
