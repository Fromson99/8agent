"""Compare native return values and actual model stages against the archived failed goal."""
from common import ART,ROOT,put,read

origin = read(ART/'action-seed/origin.json')
archive_dir = ROOT/origin['parent_dir']
original = read(archive_dir/'turn-1/response.json.gz')['body']
old_ids = {x['id'] for x in original['assembly']['context']}
rows = []
for cell in sorted((ART/'public-live').glob('*')):
    for path in sorted(cell.glob('turn-*/response.json.gz')):
        raw = read(path)
        body = raw.get('body') or {}
        answer = body.get('answer') or {}
        agent = (body.get('assembly') or {}).get('term_agent') or {}
        contexts = (body.get('assembly') or {}).get('context') or []
        new_ids = {x.get('id') for x in contexts}
        item = {'variant':'structured' if cell.name.endswith('-action') else 'free_text',
                'http':raw.get('http_status'),'same_goal':body.get('question_id')==origin['case_id'],
                'old_revision':origin['revision'],'revision':body.get('revision'),
                'command':body.get('method_id'),'executed':body.get('executed'),
                'old_source_count':len(old_ids),'retained_source_ids':sorted(old_ids & new_ids),
                'new_source_ids':sorted(new_ids - old_ids),'coverage':agent.get('answer_coverage'),
                'stop_reason':agent.get('stop_reason'),'claims':answer.get('claims'),
                'answer_text':answer.get('text'),'stage_list':[x['stage'] for x in read(cell/'calls.json')],
                'public_answer':(path.parent/'public-answer.txt').read_text() if (path.parent/'public-answer.txt').exists() else None,
                'failure':body.get('error') or body.get('detail') if raw.get('http_status')!=200 else None}
        rows.append(item)
put(ART/'recovery-comparison.json',{'parent_question':origin['sent_question'],'parent_case':origin['case_id'],
    'parent_sources':sorted(old_ids),'parent_outcome':original['assembly']['term_agent']['stop_reason'],'variants':rows})
for row in rows:print(row['variant'],row['http'],row['same_goal'],row['command'],row['executed'],row['coverage'],row['public_answer'])
