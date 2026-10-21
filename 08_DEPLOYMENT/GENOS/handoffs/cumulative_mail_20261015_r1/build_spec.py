"""Compose sealed mail deltas over the complete approved inventory graph."""
import ast,base64,gzip,hashlib,importlib.util,json,zipfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

OUT=Path(__file__).resolve().parent;BASE=OUT.parent
NAME='GENOS_CUMULATIVE_MAIL_20261015_R1'
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

FOLDERS=['rag_focused_rules_20261013_r1','rag_narrative_stream_20261013_r2',
 'model_stream_fix_20261013_r1','ad_request_logs_20261013_r2','successful_shortcut_20261013_r1',
 'assessment_gap_action_20261013_r2','public_failure_guidance_20261014_r1',
 'model_input_metrics_20261014_r1','urllib_tls_20261014_r1','schema_recovery_20261014_r1',
 'dependency_recovery_20261014_r1','tool_availability_20261014_r1','tool_recovery_20261014_r1',
 'length_recovery_20261015_r2','fact_reason_20261015_r2','output_unlimited_20261015_r1']

def main():
    ins=load('cumulative_ins',OUT/'apply_patch.py')
    tr=load('cumulative_transform',BASE/'ad_request_logs_20261013_r1/build_delivery.py')
    # Memoize byte hashing during offline graph enumeration only.
    cached_sha=lru_cache(maxsize=20000)(sha);ins.sha=cached_sha;tr.sha=cached_sha
    sources={f:json.loads(gzip.decompress((BASE/f/'PATCH_SPEC.json.gz').read_bytes())) for f in FOLDERS}
    policy=sources[FOLDERS[0]]['budget_policy']
    specs=list(sources.values());blobs={h:base64.b64decode(raw) for s in specs for h,raw in s['blobs'].items()}
    assert all(sha(v)==k for k,v in blobs.items())
    additions=defaultdict(list)
    for s in specs:
        assert s['budget_policy']==policy
        for p,ns in s['engine_additions'].items():
            for n in ns:
                if n not in additions[p]:additions[p].append(n)
    maps=[]
    for s in specs:
        mapping={}
        for state in s['signatures'].values():
            for p,r in state['patches'].items():
                key=p,r['before_sha256'];v=r['after_sha256']
                assert key not in mapping or mapping[key]==v
                mapping[key]=v
        maps.append(mapping)
    # The two narrow focused-rule fixes had a different legacy spec format.
    for folder in ('rag_focused_rules_20261013_r2','rag_focused_rules_20261013_r3'):
        s=json.loads(gzip.decompress((BASE/folder/'PATCH_SPEC.json.gz').read_bytes()))
        if 'variants' in s:
            mapping={(s['target'],r['before_sha256']):r['after_sha256'] for r in s['variants'].values()}
            for r in s['variants'].values():blobs[r['after_sha256']]=base64.b64decode(r['after'])
        else:
            mapping={(s['target'],s['before_sha256']):s['after_sha256']};blobs[s['after_sha256']]=base64.b64decode(s['after'])
        maps.insert(1 if folder.endswith('_r2') else 2,mapping)
    fields=sorted({p for m in maps for p,h in m})
    transition_by_key=defaultdict(list)
    for folder,s in sources.items():
        for key,state in s['signatures'].items():transition_by_key[key].append((folder,s,state))
    search=BASE/'search_latest_20261015_r1'
    with zipfile.ZipFile(search/'CODE.zip') as z:
        search_final={n:z.read(n) for n in ['02_BACKEND/semantic_runtime/storage.py','02_BACKEND/semantic_runtime/term_index.py',
            '02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/team_scope.py',
            '02_BACKEND/semantic_runtime/legal_agent/shortcut_ingress.py','02_BACKEND/semantic_runtime/search_selection.py',
            '02_BACKEND/lawrag/pipeline/search_selection.py']}
    search_before={n:(search/'before'/n).read_bytes() for n in search_final if (search/'before'/n).exists()}
    @lru_cache(maxsize=None)
    def search_change(n,raw):
        if raw is None:return search_final[n]
        # The old field team catalogue has no projected-team feature to adjust.
        if n.endswith('/team_scope.py') and b'def bind_projected_teams(' not in raw:return raw
        result=tr.transform(raw,search_before[n],search_final[n],n)
        ast.parse(result,feature_version=(3,10));return result
    result={'revision':NAME,'signatures':{},'blobs':{},'budget_policy':policy,
        'engine_additions':dict(additions),'unrecorded_schema_preimages':sources['length_recovery_20261015_r2']['unrecorded_schema_preimages']}
    seen=set();proofs=[];fixtures=[];excluded_bases=[]
    def register(label,payload,manifest):
        key=ins.signature(payload,manifest,result)
        if key in seen:return
        seen.add(key);ins.verify_bindings(payload)
        updates={}
        for n in fields:
            raw=payload.get(n)
            for mapping in maps:
                nxt=mapping.get((n,cached_sha(raw) if raw is not None else None))
                if nxt is not None:raw=blobs[nxt]
            if raw is not None and raw!=payload.get(n):updates[n]=raw
        final={**payload,**updates}
        # Core completion and output policies must be the last mailed policies.
        assert '결론을 하나로 확정하려면' in final['02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'].decode()
        for n,variants in json.loads((BASE/'output_unlimited_20261015_r1/SOURCE_BINDING.json').read_bytes())['field_variants'].items():
            assert cached_sha(final[n]) in set(variants.values()),('unlimited not reached',label,n)
        for n in search_final:
            raw=search_change(n,final.get(n))
            if raw!=payload.get(n):updates[n]=raw
        for entry in json.loads(payload['00_SYSTEM/PIPELINE.json'])['engines'].values():
            p=entry['manifest']
            if '02_BACKEND/semantic_runtime/storage.py' in json.loads(payload[p])['files']:
                n='02_BACKEND/semantic_runtime/search_selection.py'
                if n not in result['engine_additions'].setdefault(p,[]):result['engine_additions'][p].append(n)
        final=tr.repin(payload,updates,result['engine_additions']);ins.verify_bindings(final)
        output=ins.signature(final,manifest,result)
        for n,raw in updates.items():result['blobs'][cached_sha(raw)]=base64.b64encode(raw).decode()
        result['signatures'][key]={'label':label,'output_signature':output,'patches':{
            n:{'before_sha256':cached_sha(payload[n]) if n in payload else None,'after_sha256':cached_sha(raw)} for n,raw in updates.items()}}
        proofs.append({'input':key,'output':output,'label':label,'changed_product_files':len(updates)})
        if key=='7e3b5d20b21d33cd6e667896fdd023a9842b1c2d82dbef81892438e0b92b9686':
            fixtures.append({'kind':'field_before_fact','input':key,'output':output})
        # Enumerate every supported outgoing edge from this immutable state.
        for folder,s,state in transition_by_key.get(key,[]):
            delta={n:blobs[r['after_sha256']] for n,r in state['patches'].items()}
            child=tr.repin(payload,delta,s['engine_additions'])
            assert ins.signature(child,manifest,s)==state['output_signature'],folder
            register(label+'/'+folder,child,manifest)
        if len(seen)%250==0:print('Enumerated known complete states:',len(seen),flush=True)
    # Start with all focused R3 inputs, then include the earlier latency/R5 bases
    # and focused R1/R2/R3 intermediates through their original sealed builders.
    parent=load('cumulative_base',BASE/'rag_focused_rules_20261013_r1/build_delivery.py')
    catalogue,bases,_=parent.source_material()
    fix2=load('cumulative_fix2',BASE/'rag_focused_rules_20261013_r2/apply_patch.py')
    fix3=load('cumulative_fix3',BASE/'rag_focused_rules_20261013_r3/apply_patch.py')
    s2=json.loads(gzip.decompress((BASE/'rag_focused_rules_20261013_r2/PATCH_SPEC.json.gz').read_bytes()))
    s3=json.loads(gzip.decompress((BASE/'rag_focused_rules_20261013_r3/PATCH_SPEC.json.gz').read_bytes()))
    for index,row in enumerate(bases):
        payload={n:catalogue[h] for n,h in row['pins'].items()};manifest=json.loads(payload.pop('CODE_MANIFEST.json'))
        # The user's photo selects the mailed resident-cache R4 serving line.
        # Older nonresident R3 branches are historical alternatives, not the
        # active target. Do not silently replace that architecture here.
        if (payload.get('02_BACKEND/semantic_runtime/storage.py')!=search_before['02_BACKEND/semantic_runtime/storage.py']
                or b'def resident_connect(' not in payload['02_BACKEND/semantic_runtime/term_index.py']):
            excluded_bases.append(row['label']);continue
        register(row['label'],payload,manifest)
        s=sources[FOLDERS[0]];state=s['signatures'][ins.signature(payload,manifest,s)]
        p1=tr.repin(payload,{n:blobs[r['after_sha256']] for n,r in state['patches'].items()},s['engine_additions'])
        p2={**p1,**fix2.repinned(p1,s2)};register(row['label']+'/focused-r2',p2,manifest)
        p3={**p2,**fix3.repinned(p2,s3)};register(row['label']+'/focused-r3',p3,manifest)
        if index%25==0:print('Base',index+1,'of',len(bases),'states',len(seen),flush=True)
    assert fixtures,'screenshot state absent'
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(result),mtime=0))
    (OUT/'COMPOSITION_PROOF.json.gz').write_bytes(gzip.compress(enc(proofs),mtime=0))
    (OUT/'BUILD_RESULT.json').write_bytes(enc({'revision':NAME,'known_inputs':len(seen),'outputs':len({r['output_signature'] for r in result['signatures'].values()}),
        'blob_count':len(result['blobs']),'field':fixtures,'sources':{f:sha((BASE/f/'PATCH_SPEC.json.gz').read_bytes()) for f in FOLDERS},'product_sources':'sealed mailed artifacts only; SEARCH_LATEST compatibility fix uses exact existing delta',
        'historical_nonresident_bases_not_targeted':excluded_bases,
        'target':'existing resident-cache R4 GENOS/CM checkout shown in user photo',
        'local_main_changed':False,'field_execution':'NOT_RUN'}))
    print('DONE',len(seen),flush=True)

if __name__=='__main__':main()
