"""Sequential offline reconstruction through the frozen native service entry."""
from common import *
from native_transport import RecordedTransport, ReplayBoundary, checked, load, digest, offline_network, require, answer_content
import argparse
import asyncio
from copy import deepcopy
from functools import wraps
import importlib
import importlib.util
import os
import resource
import shutil
import sqlite3
import sys
import time
import traceback

def resources():
    fields={r.split(':')[0]:int(r.split()[1])*1024 for r in Path('/proc/meminfo').read_text().splitlines()
            if r.startswith(('MemAvailable:', 'SwapTotal:', 'SwapFree:'))}
    return {'rss_bytes':next(int(r.split()[1])*1024 for r in Path('/proc/self/status').read_text().splitlines() if r.startswith('VmRSS:')),
            'available_memory_bytes':fields['MemAvailable'], 'swap_used_bytes':fields['SwapTotal']-fields['SwapFree'],
            'disk_free_bytes':shutil.disk_usage(ROOT).free}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('arm',choices=['optimized']);args=parser.parse_args()
    frozen=read(DESIGN/'freeze.json');base=read(DESIGN/'baseline.json');contract=read(DESIGN/'secondary-replay.json')
    for name,h in frozen['files'].items():require(sha(ROOT/name)==h,'Frozen file changed: '+name)
    pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    require(sha(pointer)==base['pointer_sha256'],'Selected MAIN changed before experiment')
    inventory=load(contract['input_inventory']);native_binding=load(inventory['source_binding'])
    code=ROOT/frozen['code_root']
    out=ADR/'artifacts/run-002'/args.arm
    require(not (ADR/'artifacts/run-002/STOP.json').exists(), 'Sticky stop blocks replay')
    out.mkdir(parents=True,exist_ok=False)
    initial=resources();limits=contract['limits'];resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
    def guard():
        value=resources()
        require(value['rss_bytes']<=limits['rss_bytes'] and value['available_memory_bytes']>=limits['available_memory_bytes']
            and value['disk_free_bytes']>=limits['disk_free_bytes'] and value['swap_used_bytes']-initial['swap_used_bytes']<=limits['swap_growth_bytes'],
            'Replay resource boundary exceeded')
        require(sha(pointer)==base['pointer_sha256'],'Active pointer changed during replay')
        return value
    guard()
    put(out/'reservation.json',{'arm':args.arm,'freeze_sha256':sha(DESIGN/'freeze.json'),'initial_resources':initial,
        'limits':limits,'source':inventory['source_result'],'code_root':str(code.relative_to(ROOT)),
        'external_model_calls':0,'rerun_existing_output':False})
    for key in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE',
                'GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS',
                'GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT','TEAM_ID','AD_WORKSPACE'):
        require(not os.environ.get(key),'Unexpected runtime override: '+key)
    os.environ.update(GENOS_RUNTIME_DIR=str(out/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',
        GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
    policy=read(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    os.environ[policy['key_env']]='OFFLINE_REPLAY_NO_NETWORK'
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(code),str(code/'02_BACKEND'),str(ROOT/'02_BACKEND')]
    transport=RecordedTransport(inventory);spans=[];view_checks=[];transport_seconds=0.0
    def current_journal():
        paths=list((out/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
        require(len(paths)==1,'Current native journal missing or ambiguous')
        return paths[0]
    transport.current_journal=current_journal
    result={'arm':args.arm,'known_in_sample':True,'external_model_calls':0,'new_tokens':0,'new_cost_usd':0,
        'literal_response_rewrite':False,'active_main_changed':False,'completed':False,'quality_certified':False,
        'environment':'WSL isolated native service reconstruction; not selected-service activation or GENOS'}
    pipeline=None;started=None
    try:
        with offline_network():
            spec=importlib.util.spec_from_file_location('adr1078_native_service_'+args.arm,code/'service.py')
            service=importlib.util.module_from_spec(spec);sys.modules[spec.name]=service;spec.loader.exec_module(service)
            # Only deployment selection is injected. The native application,
            # profile construction, request pipeline, validators and consumers run.
            service._ROOT=ROOT
            binding=deepcopy(native_binding['binding'])
            for key in ('process_id','process_instance_id'):binding.pop(key,None)
            service._resolve_binding=lambda:(code,ROOT/base['manifest']['data_path'],deepcopy(binding))
            t0=time.perf_counter();app=service.application();result['application_prepare_seconds']=time.perf_counter()-t0
            pipeline=app.state.pipeline;t=pipeline.term_agent.transport
            require(Path(pipeline.contracts.root)==code and Path(t.code_root)==code,'Unexpected runtime imports')
            require(pipeline.term_agent.profile==native_binding['profile'],'Profile changed from live MAIN104')
            require(pipeline.store.selection.fingerprint==native_binding['search_selection_fingerprint'],'Selection changed')
            pkg=type(t).__module__.rsplit('.',1)[0]
            put(out/'binding.json',{'code_root':str(code.relative_to(ROOT)),'application_binding':service._BINDING,
                'binding_selection_injected':True,'application_injected':False,'profile':pipeline.term_agent.profile,
                'dataset':base['manifest']['data_path'],'data_manifest_sha256':sha(ROOT/base['manifest']['data_path']/'manifest.json'),
                'selected_pointer_unchanged':True,'runtime_root':str((out/'runtime').relative_to(ROOT))})
            def timed(owner,name,label):
                original=getattr(owner,name)
                @wraps(original)
                def measure(*a,**kw):
                    wall=time.perf_counter();cpu=time.process_time()
                    try:return original(*a,**kw)
                    finally:spans.append({'function':label,'seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu})
                setattr(owner,name,measure)
            timed(importlib.import_module(pkg+'.definition_entry'),'verified','definition_entry.verified')
            relations=importlib.import_module(pkg+'.unit_relations')
            for name in ('acquired_blocks','delivered_blocks'):
                timed(relations,name,'unit_relations.'+name)
            timed(importlib.import_module(pkg+'.connection_scope'),'offer_choices','connection_scope.offer_choices')
            navigation=importlib.import_module(pkg+'.law_navigation');original_view=navigation.Investigation.view
            @wraps(original_view)
            def view(inv):
                guard();ordinal=len(view_checks)+1;wall=time.perf_counter();cpu=time.process_time()
                value=original_view(inv)
                seconds=time.perf_counter()-wall;cpu_seconds=time.process_time()-cpu
                chain=inv.p['action_chain'];frame=chain['frames'][chain['current_frame']]
                hashes={k:digest(frame[k]) for k in ('data','actions','location')}
                row={'ordinal':ordinal,'seconds':seconds,'cpu_seconds':cpu_seconds,'hashes':hashes,
                    'exact':ordinal<=35 and hashes==inventory['frames'][ordinal-1]['hashes']}
                view_checks.append(row);put(out/f'view-{ordinal:03d}.json',row)
                require(row['exact'],'Navigation frame differs from original')
                print('VIEW',args.arm,ordinal,round(seconds,3),'exact',flush=True)
                return value
            navigation.Investigation.view=view
            def send_once(*,body,ticket):
                nonlocal transport_seconds
                guard();wall=time.perf_counter()
                try:return transport.reply(body)
                finally:
                    transport_seconds+=time.perf_counter()-wall
                    put(out/'transport-checks.json',transport.checks,replace=True)
                    print('RESPONSE',args.arm,transport.calls,flush=True)
            t.send_once=send_once
            started=time.perf_counter();cpu_start=time.process_time()
            response=asyncio.run(service.service({},load(inventory['request'])))
            result.update(request_seconds=time.perf_counter()-started,request_cpu_seconds=time.process_time()-cpu_start)
            put(out/'response.json',response)
            expected=load(inventory['response'])
            require(response.get('status')==expected.get('status')==200,'Native response not HTTP200')
            result['answer_exact']=answer_content(response['body'])==answer_content(expected['body'])
            require(result['answer_exact'],'Native final answer differs')
            journals=list((out/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
            require(len(journals)==1,'Expected one native journal')
            db=sqlite3.connect(journals[0].resolve().as_uri()+'?mode=ro')
            try:
                run=db.execute('SELECT status,phase FROM run WHERE singleton=1').fetchone()
                publication=db.execute('SELECT status,result_hash FROM publication WHERE singleton=1').fetchone()
                result['native_status']={'run':run,'publication':publication,'journal':str(journals[0].relative_to(ROOT))}
                require(run[0]=='COMPLETED' and publication[0]=='PUBLISHED','Native publication incomplete')
                identity=db.execute('SELECT run_id,query_id FROM run WHERE singleton=1').fetchone()
                require(identity==(response['body']['run_id'],response['body']['query']['id']), 'Response identities differ from native journal')
                result['answer_identity_bound_to_native_journal']=True
            finally:db.close()
            require(transport.calls==38 and len(view_checks)==35,'Incomplete reconstruction')
            require(all(x['protected_request_exact'] for x in transport.checks),'Request equivalence failed')
            for item in inventory['calls']:
                checked(item['wire']);checked(item['response'])
            checked(inventory['original_journal']);guard()
            result['completed']=True
    except BaseException as exc:
        result.update(error_type=type(exc).__name__,error=str(exc))
        (out/'error.txt').write_text(traceback.format_exc())
        stop=ADR/'artifacts/run-002/STOP.json'
        if not stop.exists():put(stop,{'arm':args.arm,'error_type':type(exc).__name__,'error':str(exc)})
    finally:
        result.update(recorded_responses_used=transport.calls,view_count=len(view_checks),
            view_seconds=sum(x['seconds'] for x in view_checks),offline_transport_seconds=transport_seconds,
            resource_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,final_resources=resources(),
            timing_note='View hashes/writes outside view timers. Request includes offline harness work. Nested spans are not additive; historical model usage is not new consumption.')
        if started is not None and 'request_seconds' not in result:result['request_seconds']=time.perf_counter()-started
        put(out/'spans.json',spans);put(out/'result.json',result)
        if pipeline is not None:pipeline.store.close()
        print('REPLAY_DONE',args.arm,result['completed'],result.get('view_seconds'),flush=True)
    return 0 if result['completed'] else 1

if __name__=='__main__':
    status=main();sys.stdout.flush();sys.stderr.flush();os._exit(status)
