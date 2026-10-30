from common import *
T=Path(__file__).parent
p=T/'test_consistency_native.py';s=p.read_text();s=s.replace("        response = api.post('/v1/rag/ask', json=request)","        from semantic_runtime.legal_agent.answer_stream import capture\n        tokens=[]\n        with capture('r1',tokens.append):response = api.post('/v1/rag/ask', json=request)")
s=s.replace("            assert response.status_code==422", "            assert response.status_code==422\n            assert not tokens")
s=s.replace("        result = response.json()", "        result = response.json()\n        assert ''.join(t['text'] for t in tokens)==result['answer']['text']")
p.write_text(s)
p=T/'regression.py';s=p.read_text().replace("'test_unattempted_gap_finish.py']", "'test_unattempted_gap_finish.py','test_completion_v4.py','test_source_span_norm.py','test_narrative_answer.py','test_token_answer_stream.py']")
p.write_text(s)
p=T/'live.py';s=p.read_text().replace("if (base/'dispatch.json').exists():raise RuntimeError('Live case already dispatched; no automatic repeat')", "if (base/'dispatch.json').exists():raise RuntimeError('Live case already dispatched; no automatic repeat')\nif case_id!='cm-001':\n previous='cm-001' if case_id=='cm-007' else 'cm-007'\n assert read(ART/'live'/previous/'gate.json')['passed'], 'Previous case gate did not pass'\nreg=read(ART/'regression-comparison.json');assert reg['new_regressions']==[],reg\nassert read(ART/'saved-cm001-rejection.json')['assessment_rejected']")
p.write_text(s)
s=s.replace("base=ART/'live'/case_id", "base=ART/'saved-replay'/case_id")
s=s.replace("  try:\n   response=super().post(url,**kwargs)", "  try:\n   parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1173-required-source-server-execution/artifacts/live/cm-001/raw'\n   if row['stage']=='memory-assess-repair':raise errors.TransportError('Stored response replay reached new ASSESS repair boundary; no model called',unknown=False,retryable=False)\n   response=httpx.Response(200,json=read(parent/f'call-{n:03d}'/'response.json'),request=httpx.Request('POST',url))")
(T/'replay_saved.py').write_text(s)
print('capture stream and parent regression, sequential live gate prepared')
