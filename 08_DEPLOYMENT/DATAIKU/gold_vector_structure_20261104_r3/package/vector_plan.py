"""Count and validate structural inputs before deletion or embedding; store no bodies."""
import json
import os
import sqlite3
import time
from gold_io import Stop, canonical, digest
from structure_segments import source_segments


def prepare(job, store, navigation, source, migration):
    path = job.work/'segment-plan.sqlite'
    binding = digest(job.state['binding'])
    if path.exists():
        plan = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
        meta = json.loads(plan.execute('SELECT json FROM metadata').fetchone()[0])
        if meta['binding'] != binding or meta['status'] != 'COMPLETE':
            plan.close(); raise Stop('VECTOR_PLAN_BINDING_CHANGED')
        job.progress.emit('VECTOR_PLAN_REUSED', total_rows=meta['rows'], total_sources=meta['sources'])
        return plan, meta
    temp = path.with_name(path.name+'.tmp')
    if temp.exists(): temp.unlink()  # Incomplete derived plan, under the same writer lock.
    plan = sqlite3.connect(temp)
    total_sources = navigation.execute('SELECT COUNT(*) FROM source').fetchone()[0]
    started = time.monotonic()
    meta = {'binding': binding, 'status': 'BUILDING', 'rows': 0, 'sources': 0}
    plan.execute('CREATE TABLE source(id TEXT PRIMARY KEY,n INTEGER NOT NULL,sha TEXT NOT NULL)')
    plan.execute('CREATE TABLE metadata(json TEXT NOT NULL)')
    allowed = set(job.state['binding']['manifest']['documents'])
    job.progress.emit('VECTOR_PLANNING', completed_sources=0, total_sources=total_sources, planned_rows=0)
    try:
        for sid, raw in navigation.execute('SELECT id,json FROM source ORDER BY id'):
            job.guard()
            item = json.loads(raw)
            if item['id'] != sid or item['document_id'] not in allowed:
                raise Stop('VECTOR_PLAN_SOURCE_SCOPE:'+sid)
            parts = source_segments(store, item, source['dataset_version'], migration)
            plan.execute('INSERT INTO source VALUES(?,?,?)', (sid, len(parts), digest([p['id'] for p in parts])))
            meta['rows'] += len(parts); meta['sources'] += 1
            if meta['sources'] % 100 == 0:
                plan.commit()
                job.progress.emit('VECTOR_PLANNING', completed_sources=meta['sources'],
                                  total_sources=total_sources, planned_rows=meta['rows'],
                                  remaining_seconds=round((time.monotonic()-started)/meta['sources']*(total_sources-meta['sources'])))
        if meta['sources'] != total_sources or not meta['rows']:
            raise Stop('VECTOR_PLAN_EMPTY_OR_INCOMPLETE')
        meta['status'] = 'COMPLETE'
        plan.execute('INSERT INTO metadata VALUES(?)', (canonical(meta),))
        plan.commit(); job.guard()
    finally:
        plan.close()
    os.replace(temp, path)
    job.progress.emit('VECTOR_PLAN_COMPLETE', total_rows=meta['rows'], total_sources=meta['sources'])
    return sqlite3.connect(path.as_uri()+'?mode=ro', uri=True), meta
