"""분석 플로우 통합 테스트 — L1/L2/잔차 탐지 오케스트레이션.

L3(LSTM-AE)는 TensorFlow 의존성이 무거우므로 이 테스트에서는 검증하지 않는다
(데이터 부족으로 자동 스킵되는 경로만 확인).
"""
import numpy as np
import pandas as pd

from flows import analysis_flow


def make_raw(n: int = 50) -> pd.DataFrame:
    idx = pd.date_range("2026-06-29 00:00", periods=n, freq="5min")
    rng = np.random.default_rng(42)
    load = 60000 + 5000 * np.sin(np.arange(n) / 10) + rng.normal(0, 300, n)
    # 이상 스파이크 1회
    load[n // 2] += 20000
    supply = load + rng.uniform(8000, 12000, n)
    return pd.DataFrame({
        "ts": idx,
        "supply_capacity": supply,
        "current_load": load,
        "forecast_load": load + rng.normal(0, 500, n),
        "reserve_power": supply - load,
        "reserve_rate": (supply - load) / load * 100,
        "oper_reserve_power": (supply - load) * 0.7,
        "oper_reserve_rate": (supply - load) / load * 100 * 0.7,
    })


def test_run_analysis_empty():
    result = analysis_flow.run_analysis(pd.DataFrame(columns=["ts"]))
    assert result["empty"] is True


def test_run_analysis_structure():
    df = make_raw(50)
    result = analysis_flow.run_analysis(df)
    assert result["empty"] is False
    assert result["n_rows"] == 50
    assert "clean_df" in result
    assert "eda" in result
    det = result["detections"]
    assert "L1_ewma" in det
    assert "L1_cusum" in det
    assert "L2_iforest" in det
    assert "residual" in det


def test_l3_skipped_when_insufficient_data():
    """50행(<60)이면 L3는 데이터 부족으로 스킵되어야 한다."""
    df = make_raw(50)
    result = analysis_flow.run_analysis(df)
    assert result["detections"]["L3_lstm"]["skipped"] is True


def test_detection_summary_string():
    df = make_raw(50)
    result = analysis_flow.run_analysis(df)
    summary = analysis_flow.detection_summary(result)
    assert isinstance(summary, str)
    assert "EWMA" in summary


def test_detection_summary_empty():
    result = {"empty": True}
    assert "데이터 없음" in analysis_flow.detection_summary(result)
