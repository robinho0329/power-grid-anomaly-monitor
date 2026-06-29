"""L2 다변량 이상탐지 테스트 — 조합 이상 주입."""
import numpy as np
import pandas as pd

from src.analysis.isolation_forest import detect


def test_detects_combination_outlier():
    rng = np.random.default_rng(42)
    n = 300
    df = pd.DataFrame(
        {
            "current_load": 70000 + rng.normal(0, 1500, n),
            "reserve_rate": 20 + rng.normal(0, 1.0, n),
            "temperature": 25 + rng.normal(0, 2.0, n),
        }
    )
    # 조합 이상: 더운데 수요는 낮고 예비율 비정상 (단변량으론 정상범위)
    df.loc[150] = {"current_load": 60000, "reserve_rate": 3.0, "temperature": 35.0}

    out = detect(df, contamination=0.02)
    assert "anomaly" in out.columns
    assert bool(out.loc[150, "anomaly"]) is True


def test_handles_all_nan_gracefully():
    df = pd.DataFrame({"current_load": [np.nan, np.nan], "reserve_rate": [np.nan, np.nan]})
    out = detect(df)
    assert out["anomaly"].eq(False).all()
