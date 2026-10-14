from pathlib import Path
R=Path(__file__).resolve().parents[3]
S=R/'02_BACKEND/lawrag/research/candidates/adr_0771/source-cards/snapshot'
p=S/'02_BACKEND/semantic_runtime/progress.py';s=p.read_text()
s=s.replace('REVISION = "rag-compact-progress-20261009-r1"','REVISION = "rag-source-cards-20261013-r1"')
old='''        event = views().compact_event(event) if self.compact_public else views().public_event(event)
        if event is None:
            return
        if self.compact_public:
'''
new='''        # Retain scoped source labels for the source-list renderer. Other
        # progress still follows the compact public policy; model I/O remains
        # private. _activity has already checked admitted document identities.
        source_activity = (isinstance(basis, dict) and basis.get('detail_mode') == 'activity'
            and basis.get('kind') in {'LAW_FULLTEXT_DIRECTORY', 'SOURCE_FULLTEXT_RESULTS', 'UNIT_READ_STARTED'})
        event = (views().compact_event(event) if self.compact_public and not source_activity
                 else views().public_event(event))
        if event is None:
            return
        if self.compact_public and not source_activity:
'''
assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/chat_adapter.py';s=p.read_text();old='            for event in events:await display.progress(event)\n';assert s.count(old)==1
s=s.replace(old,old+'            await display._flush_source_reads()\n');p.write_text(s)
print('Candidate producer and non-socket consumer connected; working backend unchanged')
