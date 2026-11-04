"""Human-readable progress using ACKed rows and this process's measured rate."""
from datetime import datetime, timedelta, timezone
from progress_display import duration


def render(value):
    phase = value.get('phase','')
    if phase == 'VECTOR_PLANNING':
        done, total = value['completed_sources'], value['total_sources']
        return ('구조 단위 준비: {:,}/{:,}개 원문 ({:.1%}) | 현재 계획 {:,}벡터 | 준비 예상 잔여 {} | 아직 임베딩 전송 전'
                .format(done,total,done/total if total else 0,value['planned_rows'],duration(value.get('remaining_seconds'))))
    if phase in ('VECTOR_PLAN_COMPLETE','VECTOR_PLAN_REUSED'):
        return '전체 적재 대상 확정: {:,}벡터 / {:,}개 원문'.format(value['total_rows'],value['total_sources'])
    if phase == 'VECTOR_PROGRESS':
        done,total,rate = value['rows'],value['total_rows'],value['rows_per_second']
        eta=value['remaining_seconds']
        when=(datetime.now(timezone(timedelta(hours=9)))+timedelta(seconds=eta)).strftime('%m-%d %H:%M:%S KST') if eta is not None else '계산 중'
        return ('벡터 적재: {:,}/{:,}행 ({:.2%}) | 남은 {:,}행 | {} | 경과 {} | 예상 잔여 {} | 예상 종료 {}'
                .format(done,total,done/total if total else 0,max(0,total-done),
                        '{:.1f}행/초'.format(rate) if rate is not None else '속도 계산 중',
                        duration(value['run_seconds']),duration(eta),when))
    return None
