"""Read existing document status ledgers; never invoke ingestion or a model."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import sys
import uuid

VERSION = 'data-status-20260929-r1'


def text_value(value):
    return ''.join(c if c.isprintable() else ' ' for c in safe(str('' if value is None else value)))


def csv_value(value):
    value = text_value(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def write_csv(path, columns, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows([[csv_value(v) for v in row] for row in rows])


def resolve_data(repo):
    # Same logical data root / inspection route used by genos_stages.offline_data_root.
    path = repo / '02_BACKEND/lawrag/platform/workspace.py'
    spec = importlib.util.spec_from_file_location('_genos_status_workspace', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.load_layout(repo).inspection_path('data', layout_version='v2').resolve()


def output_evidence(row):
    entry = row['phases']['structure']
    if entry['state'] != 'PASSED':
        return '완료 기록 없음'
    location = entry.get('output_path')
    if not location:
        return '미확인: 완료 기록의 저장 경로 없음'
    folder = Path(location)
    if not folder.is_absolute():
        return '미확인: 저장 경로가 상대 경로'
    try:
        receipt = folder / 'structure-receipt.json'
        store = folder / 'source.sqlite'
        if not receipt.is_file() or not store.is_file():
            return '미확인: 완료 기록은 있으나 영수증/원문 DB 없음'
        return '영수증/원문 DB 존재 (내용·전체 해시는 미검증)'
    except OSError as exc:
        return '미확인: ' + type(exc).__name__


def doc_lines(rows):
    if not rows:
        return '(해당 문서 없음)\n'
    lines = ['번호 | 문서 | 구조화 | 색인 | 원문 산출물 | 실패·보류 사유']
    for row in rows:
        lines.append(' | '.join([str(row['number']), text_value(row['relative']),
            _cell(row, 'structure'), _cell(row, 'index'), output_evidence(row), text_value(_error(row))]))
        lines.append('  문서 ID: ' + text_value(row['document_id']))
        lines.append('  파서: ' + text_value(row['route']) + ' [' + text_value(row['route_record']) + ']')
        for phase in PHASES:
            location = row['phases'][phase].get('output_path')
            if location:
                lines.append('  ' + LABELS[phase] + ' 저장 경로: ' + text_value(location))
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description='GENOS 문서 파싱 완료·실패·대기와 후속 색인 상태를 읽기 전용 조회')
    parser.add_argument('--repo', type=Path, default=Path.cwd(), help='checkout 입구 (기본: 현재 디렉터리)')
    parser.add_argument('--data-root', type=Path, help='다른 구축 기록을 조회할 때만 지정. LOGS의 부모 경로')
    parser.add_argument('--run-id', action='append', help='특정 실행만 조회. 여러 번 지정 가능. 기본: 전체 실행')
    parser.add_argument('--list', action='store_true', help='실행 요약만 저장·표시')
    parser.add_argument('--limit', type=int, default=30, help='터미널의 실패 표시 최대 문서 수, 0=전체. 파일은 항상 전체')
    parser.add_argument('--output', type=Path, default=Path(os.environ['GENOS_STATUS_OUTPUT_BASE']), help='결과 폴더의 부모')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('--limit는 0 이상')
    run_ids = list(dict.fromkeys(validate_run_id(v) for v in args.run_id or []))
    repo = args.repo.expanduser().resolve()
    data = args.data_root.expanduser().resolve() if args.data_root else resolve_data(repo)
    logs = data / 'LOGS'
    if not logs.is_dir():
        raise ValueError('구축 LOGS 폴더가 없습니다: ' + str(logs) + ' (--data-root로 실제 LOGS 부모 경로 지정)')
    if not run_ids:
        run_ids = sorted(p.name for p in logs.iterdir() if p.is_dir())
    output_base = args.output.expanduser().resolve()
    # Never put report files into source logs, caches, generations, or RAW.
    if output_base == data or data in output_base.parents:
        raise ValueError('--output은 조회 대상 data root 밖에 지정하세요')
    output_base.mkdir(parents=True, exist_ok=True)
    output = output_base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(mode=0o700)
    header = [VERSION, '조회 시각(UTC): ' + datetime.now(timezone.utc).isoformat(),
        'checkout: ' + str(repo), '구축 data root: ' + str(data), '입력 LOGS: ' + str(logs),
        '각 run의 마지막 실행 차수만 조회합니다. 날짜순 최신 실행을 운영 데이터로 선택하지 않습니다.',
        '다른 run에 같은 문서가 있을 수 있어 전체 합계를 고유 문서 수로 해석하지 않습니다.',
        'PASSED=저장된 단계 완료 기록. 전체 파싱 품질·MAIN 활성화·GENOS 배포 완료를 뜻하지 않습니다.',
        'RUNNING=마지막 진행 기록. 프로세스 생존 여부는 미확인입니다.',
        '대기·이번 실행 대상 아님·원장 없음은 실패 또는 성공으로 추정하지 않습니다.',
        '산출물 확인은 기록된 경로의 파일 존재 검사이며 본문·DB 내용·전체 해시 검증은 하지 않습니다.',
        '입력 읽기 전용. 파싱 재실행·모델 호출·코드 변경·CURRENT 변경 없음.', '']
    summaries = []
    overview = header + ['run ID | 마지막 기록 | 실행 단계/상태 | 선택/입력실패/제외 | 구조화 완료/실패/보류/중단/대기/진행/대상아님 | 색인 완료/실패 | 조회']
    read_errors = []
    recorded = 0
    for run_id in run_ids:
        try:
            report = read_report(logs / run_id)
            if not report['recorded']:
                overview.append(run_id + ' | 미확인: ' + report['note'])
                summaries.append([run_id] + [''] * 16 + [report['note']])
                continue
            recorded += 1
            a = report['attempt']
            selection = report['selection_counts']
            s = report['counts']['structure']
            idx = report['counts']['index']
            status_order = ('PASSED', 'FAILED', 'BLOCKED', 'INTERRUPTED', 'PENDING', 'RUNNING', 'NOT_REQUESTED')
            overview.append(' | '.join([run_id, text_value(a['updated_at']), text_value(a['stage']) + '/' + text_value(a['status']),
                '/'.join(str(selection.get(k, 0)) for k in ('SELECTED', 'INPUT_FAILED', 'EXCLUDED')),
                '/'.join(str(s[k]) for k in status_order), str(idx['PASSED']) + '/' + str(idx['FAILED']), '원장 확인']))
            summaries.append([run_id, a['id'], a['updated_at'], a['stage'], a['status'],
                *(selection.get(k, 0) for k in ('SELECTED', 'INPUT_FAILED', 'EXCLUDED')),
                *(s[k] for k in status_order), idx['PASSED'], idx['FAILED'], '원장 확인'])
            if args.list:
                continue
            run_out = output / run_id
            run_out.mkdir(mode=0o700)
            docs = report['documents']
            parsed = [d for d in docs if d['selection'] == 'SELECTED' and d['phases']['structure']['state'] == 'PASSED']
            failed = [d for d in docs if _failed(d)]
            unknown = [d for d in docs if d['selection'] == 'SELECTED' and
                       (any(d['phases'][p]['state'] in {'PENDING', 'RUNNING', 'NOT_REQUESTED'} for p in PHASES)
                        or (d['phases']['structure']['state'] == 'PASSED' and output_evidence(d).startswith('미확인')))]
            excluded = [d for d in docs if d['selection'] == 'EXCLUDED']
            prefix = '\n'.join(header + [render_console(report, limit=0).split('\n\n')[0], '']) + '\n'
            for filename, rows in [('전체.txt', docs), ('파싱완료.txt', parsed),
                                   ('실패_보류_중단.txt', failed), ('대기_미확인.txt', unknown), ('의도적제외.txt', excluded)]:
                (run_out / filename).write_text(prefix + doc_lines(rows), encoding='utf-8')
            columns = ['번호', '문서 ID', '문서명', '상대경로', '출처', '선택', '입력상태', '파서', '파서실행기록',
                       '구조화상태', '구조화방식', '구조화초', '구조화저장경로', '원문산출물존재',
                       '색인상태', '색인방식', '색인초', '색인저장경로', '실패사유']
            values = []
            for d in docs:
                st, ix = (d['phases'][p] for p in PHASES)
                values.append([d['number'], d['document_id'], d['title'], d['relative'], d['source'], d['selection'],
                    d['input_state'], d['route'], d['route_record'], st['state'], st.get('mode'), st.get('elapsed_seconds'),
                    st.get('output_path'), output_evidence(d), ix['state'], ix.get('mode'), ix.get('elapsed_seconds'),
                    ix.get('output_path'), _error(d)])
            write_csv(run_out / '전체.csv', columns, values)
            print('\n' + render_console(report, failures_only=True, limit=args.limit), flush=True)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            note = text_value(type(exc).__name__ + ': ' + str(exc))
            read_errors.append(run_id + ': ' + note)
            overview.append(run_id + ' | 조회 실패·미확인: ' + note)
            summaries.append([run_id] + [''] * 16 + [note])
    overview += ['', '확인 가능한 원장: ' + str(recorded) + '/' + str(len(run_ids)),
                 '조회 오류: ' + str(len(read_errors)), '결과 폴더: ' + str(output),
                 '분류 파일은 중복될 수 있습니다. 파싱 성공 후 색인 실패는 양쪽 목록에 표시합니다.']
    text = '\n'.join(overview) + '\n'
    (output / '요약.txt').write_text(text, encoding='utf-8')
    write_csv(output / '실행요약.csv', ['run ID', '차수', '마지막기록', '단계', '실행상태',
        '선택', '입력실패', '제외', '구조화완료', '구조화실패', '구조화보류', '구조화중단',
        '구조화대기', '구조화진행기록', '구조화대상아님', '색인완료', '색인실패', '조회상태'], summaries)
    print('\n' + text, flush=True)
    return 2 if read_errors or not recorded else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ImportError, AttributeError, KeyError, TypeError, sqlite3.Error) as exc:
        print('진단 실패: ' + text_value(type(exc).__name__ + ': ' + str(exc)), file=sys.stderr)
        raise SystemExit(2)
