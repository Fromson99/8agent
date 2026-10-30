import argparse,json,os
from pathlib import Path
from .configuration import workflow,repository,settings
from .repository import ddl

def main(argv=None):
    p=argparse.ArgumentParser(description='온톨로지 생성·검토·게시')
    p.add_argument('action',choices=['ddl','status','enqueue','generate','draft','preview','approve','reject','publish','withdraw'])
    p.add_argument('--input',type=Path);p.add_argument('--proposal',type=Path);p.add_argument('--bundle')
    p.add_argument('--revision',type=int);p.add_argument('--work-hash');p.add_argument('--expected-sequence',type=int)
    p.add_argument('--reason');p.add_argument('--owner',default='SIDDA');p.add_argument('--dialect',choices=['sqlite','oracle'],default='oracle')
    a=p.parse_args(argv)
    if a.action=='ddl':print(';\n\n'.join(ddl(a.owner if a.dialect=='oracle' else '',a.dialect))+';');return 0
    w=workflow(actor=os.environ.get('GENOS_ONTOLOGY_OPERATOR',''))
    if a.action=='status':out=w.repo.list() if not a.bundle else {'work':w.repo.latest(a.bundle),'head':w.repo.head(a.bundle)}
    elif a.action=='enqueue':out=w.enqueue(json.loads(a.input.read_text()))
    elif a.action=='generate':out=w.propose(json.loads(a.input.read_text()),bundle_id=a.bundle,expected_revision=a.revision or 0)
    elif a.action=='draft':out=w.save(json.loads(a.input.read_text()),json.loads(a.proposal.read_text()),bundle_id=a.bundle,expected_revision=a.revision or 0)
    elif a.action=='preview':out=w.preview(a.bundle)
    elif a.action in ('approve','reject'):out={'approval':w.review(a.bundle,a.revision,a.work_hash,a.action=='approve',a.reason or '')}
    elif a.action=='publish':out=w.publish(a.bundle,a.revision,a.work_hash,a.expected_sequence)
    else:out=w.repo.activate(a.bundle,None,a.expected_sequence,w.actor)
    print(json.dumps(out,ensure_ascii=False,indent=2));return 0
