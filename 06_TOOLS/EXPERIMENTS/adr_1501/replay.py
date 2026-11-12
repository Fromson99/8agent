"""ADR-1501: resend the exact body of an UNKNOWN (180 s whitespace) request once, with stream=true and a
420 s limit, and record what the model actually produces and when. One call per request, no retries."""
import gzip, json, sys, time, hashlib, pathlib, httpx
ROOT = pathlib.Path('/home/jin/8-AGENT'); OUT = ROOT/'04_EXPERIMENTS/ADR/ADR-1501-blank-180s-replay/artifacts/replay'
name, src = sys.argv[1], ROOT/sys.argv[2]
env = dict(l.split('=', 1) for l in (ROOT/'.env').read_text().splitlines() if '=' in l and not l.lstrip().startswith('#'))
key = env['OPEN_ROUTER'].strip().strip('"\'')
body = json.load(gzip.open(src)); body['stream'] = True
out = OUT/name; out.mkdir(parents=True, exist_ok=False)
(out/'source.json').write_text(json.dumps({'request': str(src.relative_to(ROOT)), 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(), 'changed': {'stream': True}}, ensure_ascii=False, indent=1))
start = time.monotonic(); text = []; marks = []; meta = {}; first = None; err = None
try:
    with httpx.stream('POST', 'https://openrouter.ai/api/v1/chat/completions', json=body,
                      headers={'Authorization': 'Bearer '+key}, timeout=httpx.Timeout(30, read=60)) as r:
        meta['http_status'] = r.status_code
        for line in r.iter_lines():
            now = time.monotonic()-start
            if now > 420: err = 'LOCAL_LIMIT_420S'; break
            if not line.startswith('data: '):
                if line.strip(): marks.append([round(now, 1), line[:80]])
                continue
            data = line[6:]
            if data == '[DONE]': break
            chunk = json.loads(data)
            if chunk.get('error'): err = chunk['error']; break
            for c in chunk.get('choices', []):
                piece = (c.get('delta') or {}).get('content') or ''
                if piece:
                    if first is None: first = now
                    text.append(piece)
                if c.get('finish_reason'): meta['finish_reason'] = c['finish_reason']
            if chunk.get('usage'): meta['usage'] = chunk['usage']
            if chunk.get('provider'): meta['provider'] = chunk['provider']
            if len(text) % 200 == 0 and text: marks.append([round(now, 1), 'chars', sum(map(len, text))])
except Exception as e:
    err = type(e).__name__+': '+str(e)[:200]
full = ''.join(text)
(out/'content.txt').write_text(full)
res = {'name': name, 'seconds': round(time.monotonic()-start, 1), 'first_content_at': first and round(first, 1), 'chars': len(full),
       'error': err, **meta, 'marks': marks[-40:], 'json_parses': None}
try: json.loads(full); res['json_parses'] = True
except Exception: res['json_parses'] = False
(out/'result.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != 'marks'}, ensure_ascii=False))
