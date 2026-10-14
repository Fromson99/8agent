from pathlib import Path
import json, subprocess, os, datetime, hashlib
R=Path(__file__).resolve().parent
meta=json.loads((R/'session.json').read_text())
P=Path(meta['package'])
env={**os.environ,'CLAUDE_CONFIG_DIR':meta['config_directory']}
auth=subprocess.run(['/home/jin/.local/bin/claude','auth','status'],env=env,capture_output=True,text=True,check=True)
assert json.loads(auth.stdout).get('email')==meta['account_email'],'Claude account does not match requested account'
assert meta['status']=='prepared','Run already started; preserve existing record'
cmd=['/home/jin/.local/bin/claude','--print','--model',meta['requested_model'],'--effort','xhigh','--session-id',meta['session_id'],'--name','MAIN50 불필요 탐색·반복 루프 설계','--permission-mode','plan','--permission-prompts','none','--tools','Read,Grep,Glob','--restricted','--safe-mode','--strict-mcp-config','--mcp-config',str(R.parent/'mcp-empty.json'),'--output-format','stream-json','--verbose']
prompt=(P/'REQUEST.md').read_text()
meta.update(status='running',started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),request_sha256=hashlib.sha256(prompt.encode()).hexdigest(),command=cmd)
(R/'session.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
with (R/'claude-output.jsonl').open('x') as out,(R/'claude-stderr.log').open('x') as err:
 result=subprocess.run(cmd,input=prompt,text=True,cwd=P,env=env,stdout=out,stderr=err)
events=[json.loads(line) for line in (R/'claude-output.jsonl').read_text().splitlines() if line.strip()]
init=next((e for e in events if e.get('type')=='system' and e.get('subtype')=='init'),{})
final=next((e for e in reversed(events) if e.get('type')=='result'),{})
review=final.get('result','')
ok=result.returncode==0 and not final.get('is_error',True) and bool(review)
meta.update(status='design_received' if ok else 'failed',exit_code=result.returncode,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),confirmed_model=init.get('model'),design_received=ok,num_turns=final.get('num_turns'),is_error=final.get('is_error'))
if ok: (R/'CLAUDE_DESIGN.md').write_text(review+'\n')
else: meta['failure']=review[:3000]
(R/'session.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:meta.get(k) for k in ['status','session_id','account_email','confirmed_model','num_turns','exit_code','failure']},ensure_ascii=False))
raise SystemExit(result.returncode)
