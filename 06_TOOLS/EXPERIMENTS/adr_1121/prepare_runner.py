from common import *
p=Path(__file__).with_name('build.py');s=p.read_text().replace("out/'failure-'+str(attempt+1)+'.json'", "out/('failure-'+str(attempt+1)+'.json')");p.write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1105/live.py').read_text()
s=s.replace("all_freeze=read(ART/'freeze.json');f={**all_freeze,**all_freeze['arms'][arm]}","all_freeze=read(ART/'freeze.json');f=all_freeze")
s=s.replace("('baseline','ontology')","('baseline','semantic')")
s=s.replace("if arm=='ontology':", "if arm in ('baseline','semantic'):")
s=s.replace("profile=check_profile", "if arm=='semantic':\n result=read(ART/'build/result.json');assert result['status']=='complete'\n assert sha(ART/'build/binding.json')==result['binding_sha256']\n pinned['candidate_navigation']['ontology_context']['semantic_binding']=read(ART/'build/binding.json')\nprofile=check_profile",1)
s=s.replace('MAIN106','MAIN107').replace("cases=read(DES/'cases.json')","cases=read(ART/'cases.json')")
s=s.replace("values['SwapTotal']-values['SwapFree']<=512*1024**2","values['SwapTotal']-values['SwapFree']<=1024**3")
s=s.replace("n=client.calls+1;payload=", "n=len(current['calls'])+1;payload=")
needle="    print('MODEL',current['case']['id'],n,phase,flush=True);started=time.monotonic()"
replacement="""    if n<=2:
        prefix=read(ART/'prefix.json')['calls'][n-1];assert sha(ROOT/prefix['path'])==prefix['sha256']
        data=read(ROOT/prefix['path']);data['usage']={};data['id']='explicit-replay-prefix-'+str(n)
        put(out/'replay'/f'{n:03d}-response.json',data)
        row.update(status='replayed',new_model_call=False,seconds=0,source=prefix);put(out/'calls.json',current['calls'])
        print('PREFIX_REPLAY',n,phase,flush=True)
        return {'status_code':200,'body_json':data,'body_text':None,'body_sha256':hashlib.sha256(json.dumps(data).encode()).hexdigest(),'acceptance':'ACCEPTED'}
    row['new_model_call']=True
    print('MODEL',current['case']['id'],n,phase,flush=True);started=time.monotonic()"""
assert needle in s;s=s.replace(needle,replacement)
needle="    schema=self.protocol.schema(schema_name);gz(out/'canonical'/f'{number:03d}.json.gz',{'phase':phase,'view':view,'schema':schema})"
replacement=needle+"""
    if view.get('source_stage')=='memory-assess' and number==3:
        cards=view.get('ontology_bundles',[]);assert cards and len(cards[0]['payload']['provisions'])==28,'Landing/source control failed'
        exact=sorted([{k:o[k] for k in ('document_id','block_id','start_cp','end_cp','text')} for o in view['evidence_options']],key=lambda x:json.dumps(x,sort_keys=True))
        put(out/'first-assess-originals.json',exact)
        if arm=='semantic':
            assert exact==read(ART/'run-001/baseline/cm-023/first-assess-originals.json'),'Paired original set differs'
            assert cards[0]['payload'].get('semantic_plan',{}).get('ordered_steps'),'Semantic plan missing'
            put(out/'semantic-plan.json',cards[0]['payload']['semantic_plan'])
"""
assert needle in s;s=s.replace(needle,replacement)
s=s.replace("    check_resources()\n", "    check_resources()\n",1)
s=s.replace("    if body.get('model')", "    if body.get('model')",1)
# The primary input is persisted before every call, including controlled replay.
p=Path(__file__).with_name('live.py');p.write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1105/check.py').read_text().replace("f['arms']['ontology']['code_root']","f['code_root']").replace("f['arms']['ontology']['files']","f['files']").replace("('test_projection.py','test_direct.py')","('test_projection.py','test_direct.py','test_semantics.py')")
Path(__file__).with_name('check.py').write_text(s)
print('runners written')
