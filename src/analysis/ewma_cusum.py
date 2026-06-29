"""L1 통계 이상탐지 — EWMA 관리한계 + CUSUM 변화점.

단변량(예: 공급예비율) 시계열에서 점진적 변화·레벨 이동을 잡는다.
학습이 필요 없고 가벼워 CI에서 즉시 실행 가능.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ewma_anomalies(
    series: pd.Series, span: int = 12, k: float = 3.0
) -> pd.DataFrame:
    """EWMA ± k·표준편차 관리한계를 벗어난 점을 이상으로 표시.

    Parameters
    ----------
    series : 값 시계열 (index = 시각)
    span   : EWMA 윈도우 (5분 데이터 기준 12 ≈ 1시간)
    k      : 관리한계 폭 (시그마 배수)
    """
    s = series.astype(float)
    ewma = s.ewm(span=span, adjust=False).mean()
    sigma = s.ewm(span=span, adjust=False).std(bias=False).bfill()
    # 관리한계는 '직전까지'의 추정치로 계산(shift) — 현재 점이 자기 한계를
    # 넓히지 못하게 해, 스파이크가 묻히는 문제를 막는다.
    center = ewma.shift(1).bfill()
    spread = sigma.shift(1).bfill()
    upper = center + k * spread
    lower = center - k * spread
    flag = (s > upper) | (s < lower)
    return pd.DataFrame(
        {"value": s, "ewma": center, "upper": upper, "lower": lower, "anomaly": flag}
    )


def cusum_change_points(
    series: pd.Series, threshold: float = 5.0, drift: float = 0.5
) -> pd.Series:
    """양/음방향 CUSUM 누적합이 threshold를 넘는 변화점을 bool로 반환."""
    x = series.astype(float).to_numpy()
    mean = np.nanmean(x)
    sp = sn = 0.0
    flags = np.zeros(len(x), dtype=bool)
    for i, v in enumerate(x):
        d = (v - mean) if not np.isnan(v) else 0.0
        sp = max(0.0, sp + d - drift)
        sn = min(0.0, sn + d + drift)
        if sp > threshold or sn < -threshold:
            flags[i] = True
            sp = sn = 0.0  # 감지 후 리셋
    return pd.Series(flags, index=series.index, name="change_point")
