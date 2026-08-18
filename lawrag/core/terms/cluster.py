"""임베딩 디듀프 — greedy cosine 군집 (ontology_kg §3.4 깔때기의 가운데 단).

모델을 모른다 — 벡터를 받아 군집만 한다(시험이 가짜 벡터로 돌 수 있어야
한다). 빈도 내림차순으로 훑으며, 기존 군집 대표와의 코사인이 임계 이상이면
합류, 아니면 새 군집. 대표는 첫(최빈) 항목 — 군집의 이름은 LLM 판정이
다시 정하므로 여기서 공들이지 않는다.
"""

from __future__ import annotations

THRESHOLD = 0.85          # 실측 조정 대상 — 낮으면 과병합(§2.3 괴물)


def cluster(vectors, order: list[int], threshold: float = THRESHOLD) -> list[list[int]]:
    """order(빈도 내림차순 인덱스) 순서로 greedy 군집. 반환은 인덱스 묶음."""
    import numpy as np

    reps: list[int] = []
    groups: list[list[int]] = []
    if len(order) == 0:
        return groups
    rep_mat = None
    for i in order:
        v = vectors[i]
        if rep_mat is not None and len(reps):
            sims = rep_mat @ v
            j = int(np.argmax(sims))
            if sims[j] >= threshold:
                groups[j].append(i)
                continue
        reps.append(i)
        groups.append([i])
        rep_mat = vectors[np.array(reps)]
    return groups
