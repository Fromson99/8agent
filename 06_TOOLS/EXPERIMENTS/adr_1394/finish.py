"""Seal reviewed reports and measurements; the inputs are post-run records."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from common import ADR, ART, DES, RUN, ROOT, put, read, sha
import json
import re

folder=Path(sys.argv[1]).resolve()
document=read(ART/'final-review.json')
m=read(ADR/'실험/manifest.json')
candidate=read(DES/'candidate-selected.json')
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
summary={key:document[key] for key in ('verdict','details','observations','limits','usage','latency','error_taxonomy')}
summary['pin']=candidate['pin']
put(RUN/'result.json',summary)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'selected':summary},comparisons=[],judge_disagreements=0,
                    usage=document['usage'],latency=document['latency'],error_taxonomy=document['error_taxonomy'])
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
sections=[('결정 요약',document['verdict']),('문제와 변경 전 구조',document['context']),
    ('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),('실험 설계',document['design']),
    ('데이터·모델·재현성',document['environment']),('결과',document['details']),('사례별 오류 분석',document['observations']),
    ('비용·지연·회수 규모',json.dumps({'usage':document['usage'],'latency':document['latency']},ensure_ascii=False)),
    ('해석',document['meaning']),('한계와 일반화 가능 범위',document['limits']),
    ('운영 결정·롤백 조건',document['release']),('재현 명령',document['commands'])]
(ADR/'README.md').write_text('---'+front+'---\n\n# '+document['title']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
index=[]
for q in m['questions']:
    case=document['cases'][q['case_id']]
    sections=[('실행 메타',document['environment']),('사용자 질문 원문',case['questions']),
       ('기준답변 — 채점 전용, 제품 입력 비공개',case['expected']),
       ('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz, artifacts/source-wire-audit.json.'),
       ('제품 모델 호출 — run·arm별 실제 원문',case['raw']),('중간 LLM 호출 — router/compiler/verifier/repair',case['raw']),
       ('채점 호출과 반복 판정','채점 모델 0. 원문·실제 호출 단계·응답·재요청 결과를 대조했다.'),
       ('사례 최종 판정',case['result'])]
    (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
    index.append(f"- [{q['case_id']}]({q['file']})")
(ADR/'실험/README.md').write_text('# 질문 및 검토 기록\n\n'+'\n'.join(index)+'\n')
paths={f for f in ART.rglob('*') if f.is_file() and '.observer-versions' not in f.parts and f!=ART/'manifest.json'}
paths.update(folder.glob('*.py'));paths.add(Path(__file__).resolve())
if m['adr_id']=='ADR-1388':paths.add(ROOT/'05_TESTS/CONTRACTS/test_chat_review_command.py')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[
    {'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen implementation, measured response, verification or recovery record',
    'contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz'))} for p in sorted(paths)]})
