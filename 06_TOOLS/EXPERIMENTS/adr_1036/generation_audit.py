"""Offline generation completion/whitespace audit; no output reconstruction."""
from common import *
P=ART/'known-query/candidate'; rows=[]
physical={r['call']:r for r in (json.loads(l) for l in (P/'physical-calls.jsonl').read_text().splitlines())}
for p in sorted((P/'model').glob('call-*/response.json')):
    d=read(p); n=int(p.parent.name.split('-')[1]); choice=(d.get('choices') or [{}])[0]
    content=choice.get('message',{}).get('content') or ''
    try:
        value=json.loads(content); syntax=True; syntax_error=None
    except (ValueError,TypeError) as exc:
        value=None;syntax=False;syntax_error=str(exc)
    rows.append({'call':n,'phase':physical.get(n,{}).get('phase'),'seconds':physical.get(n,{}).get('seconds'),
        'finish_reason':choice.get('finish_reason'),'usage':d.get('usage'),'chars':len(content),
        'whitespace_chars':sum(x.isspace() for x in content),'carriage_returns':content.count('\r'),
        'json_complete':syntax,'syntax_error':syntax_error,'choice':value.get('choice') if isinstance(value,dict) else None,
        'response_sha256':sha(p),'error':d.get('error')})
report={'calls':rows,'incomplete_length_calls':[r['call'] for r in rows if r['finish_reason']=='length'],
    'note':'No truncation repair or partial JSON completion. A partial READ or KEEP string is not an accepted judgment or executed tool action. Original responses stay unchanged.'}
save(ART/'generation-review.json',report)
print(json.dumps([{k:v for k,v in r.items() if k not in ('usage','response_sha256','syntax_error')} for r in rows],ensure_ascii=False,indent=2))
