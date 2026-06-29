"""L1 통계 이상탐지 테스트 — 합성 시계열에 스파이크/계단변화 주입."""
import numpy as np
import pandas as pd

from src.analysis.ewma_cusum import cusum_change_points, ewma_anomalies


def test_ewma_flags_spike():
    rng = np.random.default_rng(42)
    base = pd.Series(20 + rng.normal(0, 0.3, 200))
    base.iloc[120] = 35.0  # 명백한 스파이크
    res = ewma_anomalies(base, span=12, k=3.0)
    assert bool(res["anomaly"].iloc[120]) is True
    assert res["anomaly"].sum() < 10  # 거짓경보 과다 아님


def test_cusum_detects_level_shift():
    rng = np.random.default_rng(0)
    shifted = pd.Series(
        np.concatenate([20 + rng.normal(0, 0.3, 100), 25 + rng.normal(0, 0.3, 100)])
    )
    cp = cusum_change_points(shifted, threshold=5.0, drift=0.5)
    # 레벨이 바뀐 직후 구간에서 변화점이 잡혀야 함
    assert cp.iloc[100:140].any()
