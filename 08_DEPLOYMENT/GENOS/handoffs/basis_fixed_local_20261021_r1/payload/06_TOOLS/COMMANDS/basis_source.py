"""Explicit selection receipts for an existing SQLite/NFS operator binding."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path

import basis_quick as q


def verify(generation, *, local_validation=False):
    from lawrag.pipeline.term_serving_bundle import verify_assets
    from semantic_runtime.state_sqlite import network_storage
    from semantic_runtime.storage import Store
    generation = q.plain(generation)
    q.require(generation.is_absolute() and generation.is_dir(), '새 generation 절대 경로가 필요합니다.')
    q.require(local_validation or network_storage(generation), '기존 SQLite 현장의 외부 공유 데이터 경로를 사용하세요.')
    q.resources(generation)
    verify_assets(generation)
    with closing(Store(generation, verify=False)) as store:
        store.selection.require_latest()
    return q.sha(generation / 'manifest.json')


def main(argv, root):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['source-plan', 'source-apply', 'source-rollback'])
    p.add_argument('--generation', type=Path)
    p.add_argument('--plan', type=Path)
    p.add_argument('--receipt', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--local-validation', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    q.require(os.environ.get('DP', '').strip().lower() not in ('oracle', '1', 'true'),
              'Oracle 운영은 Dataiku/Oracle 게시 경로를 사용하세요. 이 명령은 기존 SQLite 선택 전용입니다.')
    config = q.plain(root / '00_SYSTEM/GENOS_SERVING_PATHS.json')
    output = q.plain(a.output)
    q.require(output != config, '계획/영수증을 원래 설정 경로에 쓸 수 없습니다.')
    before = q.read(config)
    q.require(before.get('schema_version') == 'genos-serving-paths-v1' and
              before.get('selection') == 'operator-fixed' and before.get('state') is None,
              '기존 GENOS SQLite 경로 계약이 필요합니다.')
    runtime = q.plain(before['runtime'])
    q.require(runtime.is_dir(), '기존 외부 공유 runtime이 없습니다.')
    # Both selection and discovery use the same coordinator lock.
    with q.lock(runtime / 'basis-batch/basis-quick.lock'):
        expected = q.sha(config)
        saved = (q.checked(output, 'plan_sha256' if a.action == 'source-plan' else 'receipt_sha256')
                 if output.exists() else None)
        if a.action == 'source-plan':
            q.require(a.generation is not None and a.generation.is_absolute(), '--generation 절대경로가 필요합니다.')
            fingerprint = verify(a.generation, local_validation=a.local_validation)
            after = {**before, 'generation': str(a.generation), 'generation_manifest_sha256': fingerprint}
            value = {'schema': 'basis-source-selection-v1', 'code_root': str(root),
                     'before': before, 'before_sha256': expected, 'after': after,
                     'runtime_preserved': True, 'field_verified': False}
            q.require(q.sha(config) == expected, '검증 중 기존 선택 설정이 바뀌었습니다.')
            q.require(saved is None or {k: v for k, v in saved.items() if k != 'plan_sha256'} == value,
                      '기존 계획과 다릅니다. 기존 기록을 보존하고 새 출력 이름을 사용하세요.')
            q.atomic(output, value, 'plan_sha256')
            print('SOURCE_PLAN=' + str(output), flush=True)
            return 0
        if a.action == 'source-apply':
            q.require(a.plan is not None, '--plan이 필요합니다.')
            plan = q.checked(a.plan, 'plan_sha256')
            q.require(plan.get('schema') == 'basis-source-selection-v1' and plan['code_root'] == str(root),
                      '다른 checkout 또는 지원하지 않는 선택 계획입니다.')
            original, selected = plan['before'], plan['after']
            q.require(saved is None or saved.get('plan') == plan, '다른 선택 계획의 영수증입니다.')
            if saved and saved.get('status') == 'APPLIED':
                q.require(before == selected and expected == saved['after_sha256'], '적용 이후 선택 설정이 변경되었습니다.')
                print('SOURCE_ALREADY_APPLIED=' + str(output), flush=True)
                return 0
            q.require({k: v for k, v in original.items() if k not in ('generation', 'generation_manifest_sha256')} ==
                      {k: v for k, v in selected.items() if k not in ('generation', 'generation_manifest_sha256')},
                      '원문 선택 외의 설정을 변경할 수 없습니다.')
            q.require(before == original or before == selected, '계획 이후 기존 선택 설정이 달라졌습니다.')
            if before == original:
                q.require(expected == plan['before_sha256'], '계획 이후 설정 파일이 달라졌습니다.')
            generation = Path(selected['generation'])
            q.require(verify(generation, local_validation=a.local_validation) == selected['generation_manifest_sha256'],
                      '계획 후 새 세대가 변경되었습니다.')
            q.require(q.sha(config) == expected, '적용 전 선택 설정이 변경되었습니다.')
            # Persist intent first; interrupted publication can be inspected/retried.
            value = {'schema': 'basis-source-selection-receipt-v1', 'plan': plan,
                     'status': 'PREPARED', 'before_sha256': expected}
            q.atomic(output, value, 'receipt_sha256')
            q.atomic(config, selected)
            value.update(status='APPLIED', after_sha256=q.sha(config))
            q.atomic(output, value, 'receipt_sha256')
        else:
            q.require(a.receipt is not None, '--receipt가 필요합니다.')
            receipt = q.checked(a.receipt, 'receipt_sha256')
            q.require(receipt.get('schema') == 'basis-source-selection-receipt-v1', '지원하지 않는 원복 영수증입니다.')
            plan = receipt['plan']
            q.require(plan['plan_sha256'] == q.digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) and
                      plan['code_root'] == str(root), '원복 계획/checkout이 다릅니다.')
            q.require(saved is None or saved.get('receipt') == str(a.receipt), '다른 적용의 원복 영수증입니다.')
            if saved and saved.get('status') == 'ROLLED_BACK':
                q.require(before == plan['before'] and expected == saved['config_sha256'], '원복 이후 선택 설정이 변경되었습니다.')
                print('SOURCE_ALREADY_ROLLED_BACK=' + str(output), flush=True)
                return 0
            q.require(before == plan['after'], '선택 이후 다른 변경이 있습니다. 자동 원복하지 않습니다.')
            old = plan['before']
            q.require(verify(Path(old['generation']), local_validation=a.local_validation) == old['generation_manifest_sha256'],
                      '이전 원문 세대가 변경되었습니다.')
            q.require(q.sha(config) == expected, '원복 전 선택 설정이 변경되었습니다.')
            value = {'schema': 'basis-source-rollback-v1', 'receipt': str(a.receipt), 'status': 'PREPARED'}
            q.atomic(output, value, 'receipt_sha256')
            q.atomic(config, old)
            value.update(status='ROLLED_BACK', config_sha256=q.sha(config))
            q.atomic(output, value, 'receipt_sha256')
        print('SOURCE_RECEIPT=' + str(output), flush=True)
        print('기존 원문·관계·조사 기록은 보존했습니다. 실행 중인 서비스의 선택은 새 프로세스/리비전에서 확인하세요.', flush=True)
    return 0
