"""One actual authorised-log build and an idempotent follow-up, no API retest."""
import json
import shutil
import time
from harness import R,A,C,candidate,write,sha

def main():
    m=json.loads((A/'실험/manifest.json').read_text())
    for p,h in m['design']['frozen_inputs'].items():assert sha(R/p)==h,p
    out=A/'artifacts/run-001';out.mkdir(exist_ok=False)
    shutil.copytree(A/'artifacts/log-snapshot/runtime',out/'runtime')
    with candidate():
        from lawrag.pipeline.action_memory import build
        from lawrag.core.action_memory import Memory
        start=time.monotonic();first=build(R,runtime=out/'runtime',batch_size=8,max_seconds=120)
        write(out/'first.json',first)
        store=Memory(out/'runtime/action-memory/memory.sqlite',readonly=True)
        count=store.db.execute('SELECT count(*) FROM observation').fetchone()[0];store.close()
        second=build(R,runtime=out/'runtime',batch_size=8,max_seconds=120);write(out/'second.json',second)
        store=Memory(out/'runtime/action-memory/memory.sqlite',readonly=True)
        after=store.db.execute('SELECT count(*) FROM observation').fetchone()[0]
        catalogue=store.catalogue();states=dict(store.db.execute('SELECT state,count(*) FROM episode GROUP BY state'))
        store.close()
    result={'status':'complete','classification':'CURRENT_GRANT_PUBLIC_NATIVE_LOGS','seconds':time.monotonic()-start,
        'first_state':first['state'],'second_state':second['state'],'first_model_calls':first['counts']['model_calls'],
        'second_model_calls':second['counts']['model_calls'],'built_episodes':first['counts']['built_episodes'],'concepts':catalogue,
        'relations':first['relations'],'proposed_exclusions':first['proposed_exclusions'],'episode_states':states,
        'generation_pass':first['state']=='COMPLETED' and first['counts']['built_episodes']>=1 and first['concepts']>=1 and first['relations'].get('GUIDES_TO',0)>=1,
        'idempotence_pass':count==after and second['counts']['new_episodes']==0 and second['counts']['model_calls']==0,
        'privacy_pass':states.get('WAITING_AUTH')==1,'online_main_changed':False,'observation_count_before':count,'observation_count_after':after}
    write(out/'result.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
