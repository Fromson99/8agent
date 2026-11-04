"""Read-only local corpus contract audit, no provider calls or retrieval evaluation."""
from pathlib import Path
import collections
import json
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'package'))
import run_full
from structure_segments import source_segments
from lawrag.pipeline import oracle_migration as migration


def run(root,output):
    root=Path(root).resolve();started=time.monotonic()
    store=migration.source_open(root/'store.sqlite')
    navigation=migration.source_open(root/'navigation/navigation.sqlite')
    manifest=json.loads((root/'manifest.json').read_text())
    report={'source_root':str(root),'source_generation':manifest['generation_id'],
            'field_generation_equal':'UNCONFIRMED','sources':0,'segments':0,'errors':[],
            'extent_counts':{},'max_input_chars':0,'coverage_checked_blocks':0,'blank_sources':0,
            'live_model_calls':0,'oracle_calls':0}
    counts=collections.Counter()
    try:
        for sid,raw in navigation.execute('SELECT id,json FROM source ORDER BY id'):
            report['sources']+=1
            source=json.loads(raw)
            try:
                items=source_segments(store,source,'fixture-version',migration)
                if not items:
                    assert all(not block['text'].strip() for block in source['blocks'])
                    report['blank_sources']+=1
                spans=collections.defaultdict(list)
                for item in items:
                    counts[item['meta']['extent']]+=1
                    report['max_input_chars']=max(report['max_input_chars'],len(item['text']))
                    for span in item['meta']['body_spans']:spans[span['block_id']].append(span)
                if items:
                    for block in source['blocks']:
                        body=block['text'];s=spans[str(block['block_id'])]
                        assert s and s[0]['start']==0 and s[-1]['end']==len(body)
                        assert all(a['end']==b['start'] for a,b in zip(s,s[1:]))
                        assert ''.join(body[x['start']:x['end']] for x in s)==body
                        report['coverage_checked_blocks']+=1
                report['segments']+=len(items)
            except Exception as exc:
                report['errors'].append({'source_id':sid,'type':type(exc).__name__,'message':str(exc)})
        report['extent_counts']=dict(counts);report['elapsed_s']=round(time.monotonic()-started,2)
    finally:store.close();navigation.close()
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({**report,'errors':report['errors'][:10],'error_count':len(report['errors'])},ensure_ascii=False,indent=2))
    return not report['errors']


if __name__=='__main__':
    raise SystemExit(0 if run(sys.argv[1],sys.argv[2]) else 1)
