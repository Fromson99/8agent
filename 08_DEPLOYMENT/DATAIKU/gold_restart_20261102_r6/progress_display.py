"""Read-only notebook observer. Never writes the loader's checkpoint or database."""
import hashlib
import json
import time
from pathlib import Path


def duration(seconds):
    if seconds is None:
        return '계산 중'
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return (f'{hours}시간 ' if hours else '') + f'{minutes}분 {seconds:02d}초'


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(32 * 1024**2 + 1)
    if len(raw) > 32 * 1024**2:
        raise ValueError('표시용 메타데이터 크기 초과')
    return json.loads(raw)


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class Display:
    def __init__(self, old_job, contract, action, clock=time.monotonic):
        self.old_job, self.action, self.clock = Path(old_job), action, clock
        self.state_path = self.old_job.parent / ('gold-shape-' + contract[:12]) / 'state.json'
        self.started = clock()
        self.baselines = {}
        self.last_rows = {}
        self.last_seen = {}
        self.totals = None
        self.reset_id = None

    def planned_totals(self, state):
        if self.totals is not None:
            return self.totals
        binding = state['binding']
        descriptor = read_json(self.old_job / 'projection-descriptor-r7.json')
        body = {k: v for k, v in descriptor.items() if k != 'checksum'}
        if (digest(body) != descriptor['checksum'] or
                body['binding']['source'] != binding['source_release'] or
                body['binding']['files'] != binding['files']):
            raise ValueError('준비 명세와 현재 작업 불일치')
        manifest_path = Path(binding['generation']) / 'manifest.json'
        with manifest_path.open('rb') as stream:
            raw = stream.read(32 * 1024**2 + 1)
        if len(raw) > 32 * 1024**2 or hashlib.sha256(raw).hexdigest() != binding['files']['manifest.json']:
            raise ValueError('원문 명세와 현재 작업 불일치')
        manifest = json.loads(raw)
        counts = [manifest['counts'][name] for name in ('document', 'source_unit', 'source_block')]
        if any(type(n) is not int or n < 0 for n in counts):
            raise ValueError('원문 행 수 명세 오류')
        source_total = sum(counts)
        self.totals = {'source': source_total,
                       'query': sum(t['rows'] for t in body['tables'].values())}
        return self.totals

    def render(self):
        now = self.clock()
        lines = [f'이번 실행 경과: {duration(now - self.started)}']
        try:
            state = read_json(self.state_path)
            if state.get('reset_id') != self.reset_id:
                self.baselines.clear();self.last_rows.clear();self.last_seen.clear()
                self.reset_id=state.get('reset_id')
            totals = self.planned_totals(state)
            stopped = state.get('status') in {'FAILED','WRITE_UNCONFIRMED','VERIFY_FAILED'}
            prefix = 'verify_' if self.action == 'verify_publish' else ''
            for group, label in [('source', '원문'), ('query', '검색 자료')]:
                key = prefix + group
                done = sum(v.get('rows', 0) for v in state.get(key, {}).values())
                total = totals[group]
                # A later stage must not inherit the time spent loading earlier stages.
                previous = self.last_rows.get(key, done)
                if done == previous and key not in self.baselines:
                    self.last_rows[key] = done
                if key not in self.baselines and done != previous:
                    self.baselines[key] = (self.last_seen.get(key, now), previous)
                self.last_rows[key] = done
                self.last_seen[key] = now
                baseline = self.baselines.get(key, (now, done))
                elapsed, added = now - baseline[0], done - baseline[1]
                rate = added / elapsed if elapsed >= 5 and added > 0 else None
                if total is not None and done > total:
                    raise ValueError('처리 행 수가 계획 행 수를 초과함')
                remaining = None if total is None else total - done
                eta = remaining / rate if rate and remaining is not None else None
                if remaining == 0:
                    eta = 0
                ratio = f' / {total:,}행 ({done/total:.2%})' if total else '행'
                left = f'{remaining:,}행' if remaining is not None else '미확인'
                speed = f'{rate:,.1f}행/초' if rate else '계산 중'
                eta_text = '중단됨 — 예상 시간 계산 안 함' if stopped else duration(eta)
                if stopped: speed = '중단됨'
                lines.append(f'{label} {"검증" if prefix else "적재"}: {done:,}{ratio} | 남은 {left} | {speed} | 예상 잔여 {eta_text}')
            lines.append('예상 잔여는 각 단계의 관측 평균 기준이며 다음 단계·임베딩 시간은 포함하지 않습니다.')
            lines.append('행 수는 저장된 완료 기록 기준입니다. 실행 중인 묶음은 완료 후 반영됩니다.')
            lines.append('상태: ' + str(state.get('status', '준비 중')))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            lines.append('행 수·예상 시간 확인 중 (' + type(exc).__name__ + ')')
        return '\n'.join(lines)
