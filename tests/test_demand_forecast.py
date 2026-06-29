"""수요 예측 + 잔차 이상탐지 단위 테스트."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.demand_forecast import (
    build_seasonal_baseline,
    evaluate_forecast,
    forecast_next_n,
    residual_anomalies,
)


def make_periodic_series(n: int = 288, spike_idx: int = None) -> pd.Series:
    """5분 단위 주기성 있는 합성 수요 시계열 생성."""
    idx = pd.date_range("2026-06-23 00:00", periods=n, freq="5min")
    # 일주기 사인파 (평균 60000 MW, 진폭 10000 MW)
    t = np.arange(n)
    vals = 60000 + 10000 * np.sin(2 * np.pi * t / 288)
    if spike_idx is not None and spike_idx < n:
        vals[spike_idx] += 50000  # 극단 스파이크
    return pd.Series(vals, index=idx)


def test_build_seasonal_baseline_same_shape():
    s = make_periodic_series(288)
    baseline = build_seasonal_baseline(s)
    assert len(baseline) == len(s)
    assert not baseline.isna().all()


def test_residual_anomalies_detects_spike():
    """2주 데이터에서 스파이크 주입 시 이상으로 감지되어야 한다.

    (요일+시간대) 그룹당 최소 2개 관측치가 있어야 스파이크가
    기준선 평균에 묻히지 않고 잔차로 드러남.
    """
    n = 288 * 14  # 2주
    spike_idx = 288 * 7 + 144  # 2주차 같은 요일 12:00
    s = make_periodic_series(n, spike_idx=spike_idx)
    res_df = residual_anomalies(s, ewma_span=12, k=2.0)
    assert "anomaly" in res_df.columns
    assert res_df["anomaly"].any(), "스파이크가 이상으로 감지되어야 함"


def test_residual_anomalies_clean_series_low_fp():
    """이상 없는 시계열에서 거짓경보가 5% 미만이어야 한다."""
    s = make_periodic_series(288)
    res_df = residual_anomalies(s, ewma_span=12, k=3.0)
    fp_rate = res_df["anomaly"].mean()
    assert fp_rate < 0.05, f"거짓경보율 {fp_rate:.2%} 초과"


def test_forecast_next_n_length():
    s = make_periodic_series(288)
    forecast = forecast_next_n(s, n=12)
    assert len(forecast) == 12
    assert not forecast.isna().all()


def test_evaluate_forecast_metrics_shape():
    s = make_periodic_series(576)  # 48시간
    result_df, metrics = evaluate_forecast(s, test_ratio=0.2)
    assert "MAE" in metrics and "RMSE" in metrics and "MAPE(%)" in metrics
    assert metrics["MAE"] >= 0
    assert len(result_df) > 0
