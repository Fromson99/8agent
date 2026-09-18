"""A bounded live progress board; cumulative phase results and private detail."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import threading
import time
import traceback
import unicodedata

from .genos_build import atomic
from semantic_runtime.genos_backend import safe


def clean(value):
    return ''.join(ch if ch.isprintable() else ' ' for ch in safe(str(value)))


def reason(value):
    text = clean(value)
    if 'schema path' in text:
        text = text[text.index('schema path'):]
        text = text.replace('schema path', '스키마 필드')
        text = text.replace('is a required property', '필수 필드 없음')
        text = text.replace('is not one of', '허용된 값이 아님; 허용 값:')
        text = text.replace('should be non-empty', '빈 값은 허용되지 않음')
    for old, new in [('clause_predicate:', '절 PREDICATE 역할 수 오류: '),
                     ('document(s) failed structure;', '문서 구조화 실패;'),
                     ('invalid_unresolved:', '미해결 참조의 null/이유 불일치: '),
                     ('invalid_resolved:', '해결된 참조의 ID 연결 오류: '),
                     ('OUTPUT_LENGTH_LIMIT', '출력 토큰 한도: 응답 잘림'),
                     ('model_call_budget_exhausted', '문서별 모델 호출 횟수 상한 도달'),
                     ('authoring incomplete; nothing loaded.', '미통과 청크가 남아 문서 적재 보류.')]:
        text = text.replace(old, new)
    return text


def vlm_detail(row):
    """Render bounded metadata only; model prompts and responses stay in evidence files."""
    event = row['event']
    if event == 'recipe.basic.ready':
        return 'basic 구조화 완료 · 초기 LLM 틀 생성 없이 bbox 검수 시작'
    if event == 'recipe.review.budget':
        status = ' · 현재 상한으로 첫 검수 완료 불가' if row['minimum_exceeds_limit'] else ''
        return (f'검수 {row["total_pages"]}쪽 · 묶음 최대 {row["window_width"]}쪽 · '
                f'첫 검수 최소 {row["fresh_pass_min_calls"]}회 / 호출 상한 {row["max_calls"]}회'
                + status + ' · 수정·재검수 호출 별도 필요')
    if event == 'recipe.review.budget_exhausted':
        return (f'문서별 호출 상한 {row["calls"]}/{row["max_calls"]}회 도달 · '
                f'남은 {row["pending_pages"]}쪽 시각 미검수로 저장 · 입력 토큰 한도와 별개')
    if event == 'recipe.output.split':
        if row.get('reason') == 'INPUT_CONTEXT_LIMIT':
            return '입력 문맥 한도 · 검수 페이지 묶음을 줄여 다시 확인'
        if row['unit'] == 'pages':
            return '출력 잘림 복구 · 검수 페이지 묶음을 줄여 다시 확인'
        if row['unit'] == 'families':
            return f'출력 잘림 복구 · 전체 원문 유지 · 번호 체계 {row["batch_size"]}개씩 규칙 생성'
        return '출력 잘림 복구 · 전체 원문 유지 · 구간 목록을 나누어 생성'
    if event == 'recipe.resume':
        return f'중간 결과 재개 · 기존 승인 {row["approved_windows"]}창 · 미완료 검수 계속'
    if event == 'recipe.review.reused':
        return '기존 검수 승인 재사용 · '+','.join(map(str,row['pages']))+'쪽'
    if event == 'recipe.review.warning':
        return '경고 포함 계속 · '+','.join(map(str,row['pages']))+'쪽 · '+row['code']
    if event == 'recipe.review.pending':
        return '검수 대기 · 중간 결과 저장 완료 · 같은 실행 명령으로 재개 가능'
    if event == 'recipe.sampling':
        return f'문서 {row["total_pages"]}쪽 · 검수 후보 {row["selected_pages"]}쪽'
    if event == 'recipe.regions.start':
        return '형식 구간 재감지' if row['replan'] else '본문·부칙·별표 형식 구간 감지'
    if event == 'recipe.regions.ready':
        return f'형식 구간 {row["region_count"]}개 · 구조화 틀 {row["template_count"]}개'
    if event == 'recipe.template.start':
        return f'구조화 틀 생성 {row["template_number"]}/{row["template_count"]}'
    if event == 'recipe.rebuild':
        return f'틀 적용·구조화 {row["revision"]}회차 · 수정 {row["corrections"]}회'
    if event == 'recipe.review.start':
        pages = ','.join(map(str, row['pages']))
        return f'bbox 검수 {row["window_number"]}/{row["window_count"]}창 · {pages}쪽 · 수정 {row["corrections"]}회'
    if event == 'recipe.review.result':
        verdict = {'approve':'통과', 'revise':'틀 수정', 'resegment':'구간 재감지',
                   'hold':'보류', 'source_error':'원문 확인 필요', 'missing_rules':'문법 확장 필요'}.get(row['verdict'], '판정 확인 필요')
        return f'검수 {row["window_number"]}/{row["window_count"]}창 {verdict} · 지적 {row["issue_count"]}건'
    if event == 'recipe.correction':
        return f'틀·구간 수정 {row["corrections"]}회 · 이전 승인 해제 후 재검수'
    if event == 'run.needs_review':
        return f'구조 검수 보류 · {row["reason"]} · 실행 {row["run_id"]}'
    if event == 'run.complete':
        if row.get('status') == 'accepted_with_warnings':
            return f'경고 포함 저장 · 미해결 {row.get("warning_count",0)}건 · 모델 호출 {row["model_calls"]}회'
        if row['reused']:
            return '구조화 틀 재사용 · 모델 호출 0회'
        scope = '전체 페이지' if row['visual_scope'] == 'full' else '샘플 페이지'
        return f'{scope} 검수 완료 · 모델 호출 {row["model_calls"]}회'
    return None


def clip(value, width):
    text, used = '', 0
    for ch in clean(value):
        cells = 0 if unicodedata.combining(ch) else (2 if unicodedata.east_asian_width(ch) in 'WF' else 1)
        if used + cells > width - 1:
            return text + '…'
        text += ch
        used += cells
    return text


VLM_SLOTS = {'recipe.sampling':'샘플링', 'recipe.regions.start':'구간',
             'recipe.review.budget':'호출 예산', 'recipe.review.budget_exhausted':'호출 예산',
             'recipe.basic.ready':'basic',
             'recipe.output.split':'출력 복구',
             'recipe.regions.ready':'구간', 'recipe.template.start':'틀',
             'recipe.rebuild':'구조화', 'recipe.review.start':'검수',
             'recipe.review.result':'검수', 'recipe.correction':'수정',
             'run.complete':'검수', 'run.needs_review':'검수'}


class Progress:
    def __init__(self, directory, terminal):
        self.directory, self.terminal = Path(directory), terminal
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log = (self.directory / 'progress.log').open('a', encoding='utf-8', buffering=1)
        self.detail = (self.directory / 'detail.log').open('a', encoding='utf-8', buffering=1)
        self.lock = threading.RLock()
        self.state, self.previous, self.open_line = {}, None, False
        self.documents, self.recent, self.drawn_lines = {}, [], 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def _heartbeat(self):
        while not self.stop.wait(5):
            with self.lock:
                if self.open_line:
                    self._show(heartbeat=True)

    def document(self, number, total, name, stage):
        with self.lock:
            key = clean(name)
            entry = self.documents.setdefault(key, {'number': number, 'stages': {}})
            entry['stages'][stage] = 'RUNNING'
            self.state = {'number': number, 'total': total, 'document': clean(name),
                          'stage': stage, 'phase': stage, 'detail': '시작', 'started': time.monotonic(),
                          'status': 'RUNNING', 'milestones': {}, 'stages': dict(entry['stages'])}
            self.previous = None
            self.open_line = True
            self._show()
            if not self.terminal.isatty():
                self.terminal.write(self._board()[1] + '\n')
                self.terminal.flush()

    def _newline(self):
        if self.drawn_lines and self.terminal.isatty():
            self.terminal.write('\n')
            self.terminal.flush()
            self.drawn_lines = 0
        self.open_line = False

    def _board(self):
        s = self.state
        totals = []
        for phase in ('구조화', 'LLM 추출', '임베딩'):
            states = [d['stages'].get(phase) for d in self.documents.values()]
            totals.append(f'{phase} 완료 {states.count("COMPLETED")} / 실패 {states.count("FAILED")}')
        elapsed = s.get('elapsed_seconds', time.monotonic() - s['started'])
        rows = ['누적 현황 · ' + ' | '.join(totals),
                f'[{s["number"]}/{s["total"]}] {Path(s["document"]).name} | {s["stage"]} | {elapsed:.1f}초',
                '현재: ' + s['detail']]
        labels = {'COMPLETED':'완료', 'FAILED':'실패', 'RUNNING':'진행 중', 'INTERRUPTED':'중단'}
        rows.append('문서 단계: ' + ' → '.join(f'{k} {labels.get(v, v)}' for k,v in s['stages'].items()))
        rows.extend(f'  {key}: {value}' for key,value in s['milestones'].items())
        rows.extend('최근: ' + value for value in self.recent[-2:])
        return rows

    def _draw(self):
        size = shutil.get_terminal_size((120, 24))
        # Keep the board below terminal height so cursor-up never crosses scrollback.
        height = max(1, size.lines - 2)
        rows = self._board()[:height]
        count = max(len(rows), min(self.drawn_lines, height))
        if self.drawn_lines:
            self.terminal.write('\r' + (f'\x1b[{min(self.drawn_lines, height)-1}A' if min(self.drawn_lines, height)>1 else ''))
        self.terminal.write('\n'.join('\r\x1b[2K' + clip(rows[i] if i<len(rows) else '', max(2, size.columns-1)) for i in range(count)))
        self.drawn_lines = count

    def _show(self, heartbeat=False):
        if not self.state:
            return
        s = self.state
        value = f'[{s["number"]}/{s["total"]}] {s["document"]} | {s["stage"]} | {s["detail"]}'
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if value != self.previous:
            self.log.write(now + ' ' + value + '\n')
            atomic(self.directory / 'current.json', {**s, 'updated_at': now})
        if self.terminal.isatty():
            self._draw()
        self.terminal.flush()
        self.previous = value

    def emit(self, message):
        with self.lock:
            message = str(message)
            prefix = next((p for p in ('[STRUCTURE VLM] ', '[QUEUE] ', '[TASK] ') if message.startswith(p)), None)
            if prefix:
                try:
                    # Redacting serialized JSON can replace a numeric token
                    # budget with bare [REDACTED], corrupting its syntax.
                    row = safe(json.loads(message[len(prefix):]))
                    if not isinstance(row, dict):raise ValueError('event must be an object')
                    message = prefix + json.dumps(row, ensure_ascii=False)
                except (ValueError, TypeError):
                    self.detail.write(datetime.now(timezone.utc).isoformat() +
                                      ' [PROGRESS WARNING] Invalid event JSON; display update skipped\n')
                    return
            else:
                message = safe(message)
            self.detail.write(datetime.now(timezone.utc).isoformat() + ' ' + message + '\n')
            if not self.state:
                return
            if message.startswith('[STRUCTURE VLM] '):
                row = json.loads(message[len('[STRUCTURE VLM] '):])
                detail = vlm_detail(row)
                if detail is not None:
                    self.state['vlm_step'] = detail
                else:
                    base = self.state.get('vlm_step', 'PDF 구조화')
                    if row['event'] == 'model.request':
                        phase = row.get('phase', '')
                        role = ('VLM 검토 의견 작성' if ('-vlm-opinions' in phase or '-vlm-review' in phase) else
                                'LLM 의견 검증·수정안 작성' if ('-llm-adjudicate' in phase or '-body-review' in phase) else 'LLM 틀 생성')
                        detail = f'{base} · {role} · 모델 호출 {row["call"]} · 시도 {row["attempt"]} · 응답 대기'
                    elif row['event'] == 'model.response':
                        detail = f'{base} · 응답 {row["seconds"]}초 · 입력/출력 {row.get("input_count")}/{row.get("output_count")}'
                    elif row['event'] == 'model.retry':
                        detail = f'{base} · 재시도 {row["next_attempt"]} · {row["delay_seconds"]}초 후'
                    else:
                        return
                self.state.update(stage='구조화', detail=clean(detail), vlm_run_id=row['run_id'])
                slot = VLM_SLOTS.get(row['event'], '모델')
                self.state['milestones'][slot] = clean(detail)
                if row['event'] in {'recipe.correction', 'recipe.rebuild'}:
                    self.state['milestones']['검수'] = '현재 구조 기준 재검수 대기 · 이전 승인 사용 안 함'
            elif message.startswith('[QUEUE] '):
                row = json.loads(message[8:])
                self.state['stage'] = '검증' if row.get('error') or row['state'] == 'REVIEW_PASSED_CANDIDATE' else 'LLM 추출'
                self.state['detail'] = (f'청크 검토 통과 {row["passed"]}/{row["total"]} · '
                    f'{row["stage"]} · 시도 {row["attempt"]} · ' +
                    (reason(row['error'])[:400] if row.get('error') else
                     ('현재 청크 검토 통과 (문서 전체 아님)' if row['state'] == 'REVIEW_PASSED_CANDIDATE' else '다음 단계 대기')))
                if row.get('error'):
                    self.state['detail'] += ' · ' + ('재시도 예정' if row['state'] == 'READY' else '시도 한도 소진/검토 미통과')
                if row.get('empty_collections'):
                    self.state['detail'] += ' · 해당 내용 없음: ' + ','.join(row['empty_collections'])
            elif message.startswith('[TASK] '):
                row = json.loads(message[7:])
                self.state['stage'] = '검증' if row['stage'] == 'review' else 'LLM 추출'
                self.state['detail'] = f'청크 {row["number"]}/{row["total"]} · {row["label"]} · 모델 응답 대기'
            elif message.startswith('[CACHE]'):
                self.state['detail'] = clean(message[7:])
            elif message.startswith('[STRUCTURE STEP] '):
                self.state['detail'] = clean(message[len('[STRUCTURE STEP] '):])
            elif message.startswith('[STRUCTURE WARNING] '):
                self.state['detail'] = clean(message[len('[STRUCTURE WARNING] '):])
            elif message.startswith('[3/5]'):
                self.state.update(stage='임베딩', detail=clean(message[6:]))
            elif message.startswith(('[4/5]', '[5/5]')):
                self.state.update(stage='적재 검증', detail=clean(message[6:]))
            elif message.startswith('[CONNECT]'):
                self.state['detail'] = '필요한 모델 연결 확인 중'
            else:
                return
            self._show()

    def finish(self, message, *, status='COMPLETED'):
        with self.lock:
            if not self.state:
                return
            self.state['detail'] = clean(message)
            self.state.update(status=status, elapsed_seconds=round(time.monotonic()-self.state['started'], 3))
            entry = self.documents[self.state['document']]
            entry['stages'][self.state['phase']] = status
            self.state['stages'] = dict(entry['stages'])
            self.recent.append(f'{Path(self.state["document"]).name} · {self.state["phase"]} · {clean(message)}')
            self.recent = self.recent[-2:]
            self._show()
            atomic(self.directory / 'progress-summary.json', {'documents': self.documents})
            if not self.terminal.isatty():
                self.terminal.write('\n'.join(self._board()) + '\n')
                self.terminal.flush()
            self.open_line = False

    def error(self, exc):
        self.emit(traceback.format_exc())
        self.finish('실패·후속 단계 보류: ' + reason(exc)[:500] + ' | 상세: detail.log', status='FAILED')
        # The live board clips long rows. Keep the complete cause and exact
        # response path below it so diagnosis never requires guessing a run ID.
        with self.lock:
            self._newline()
            self.terminal.write('실패 원인: ' + reason(exc) + '\n')
            self.terminal.flush()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=6)
        with self.lock:
            self._newline()
            self.log.close(); self.detail.close()


class DetailStream:
    def __init__(self, progress):
        self.progress, self.pending = progress, ''
    def write(self, value):
        self.pending += value
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.progress.emit(line)
        return len(value)
    def flush(self):
        if self.pending:
            self.progress.emit(self.pending); self.pending = ''
    def isatty(self):
        return False
