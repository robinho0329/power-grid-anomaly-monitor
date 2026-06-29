"""EDA & 전처리 모듈 단위 테스트."""
import numpy as np
import pandas as pd

from src.analysis import preprocess


def make_raw(n: int = 100, with_gap: bool = False, with_dup: bool = False) -> pd.DataFrame:
    """5분 단위 합성 수급 원본 생성."""
    idx = pd.date_range("2026-06-29 00:00", periods=n, freq="5min")
    rng = np.random.default_rng(42)
    load = 60000 + 5000 * np.sin(np.arange(n) / 10) + rng.normal(0, 300, n)
    supply = load + rng.uniform(8000, 12000, n)
    df = pd.DataFrame({
        "ts": idx,
        "supply_capacity": supply,
        "current_load": load,
        "forecast_load": load + rng.normal(0, 500, n),
        "reserve_power": supply - load,
        "reserve_rate": (supply - load) / load * 100,
        "oper_reserve_power": (supply - load) * 0.7,
        "oper_reserve_rate": (supply - load) / load * 100 * 0.7,
    })
    if with_dup:
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    if with_gap:
        df = df.drop(index=[10, 11, 12]).reset_index(drop=True)  # 15분 갭
    return df


def test_clean_removes_duplicates():
    df = make_raw(50, with_dup=True)
    clean = preprocess.clean_timeseries(df)
    assert clean["ts"].is_unique


def test_clean_creates_uniform_grid():
    """갭이 있어도 균일 5분 그리드로 재색인되어야 한다."""
    df = make_raw(50, with_gap=True)
    clean = preprocess.clean_timeseries(df)
    diffs = clean["ts"].diff().dropna().dt.total_seconds()
    assert (diffs == 300).all(), "모든 간격이 5분(300초)이어야 함"


def test_fill_missing_short_gap():
    """짧은 갭은 보간되어야 한다."""
    df = make_raw(50, with_gap=True)
    clean = preprocess.clean_timeseries(df)
    filled = preprocess.fill_missing(clean, max_gap=6)
    # 15분(3스텝) 갭은 max_gap=6 이내 → 보간됨
    assert filled["current_load"].isna().sum() < clean["current_load"].isna().sum()


def test_add_features_columns():
    df = make_raw(50)
    feat = preprocess.add_features(df)
    for col in ["hour", "dayofweek", "is_weekend", "load_change_pct",
                "forecast_error", "supply_margin"]:
        assert col in feat.columns, f"{col} 누락"


def test_eda_summary_structure():
    df = make_raw(100)
    summary = preprocess.eda_summary(df)
    assert summary["empty"] is False
    assert summary["n_rows"] == 100
    assert "load_peak" in summary
    assert "min_reserve" in summary
    assert "correlation" in summary


def test_pipeline_empty_input():
    """빈 입력에 graceful 처리."""
    empty = pd.DataFrame(columns=["ts"] + preprocess.NUMERIC_COLS)
    result = preprocess.preprocess_pipeline(empty)
    assert result.empty


def test_pipeline_end_to_end():
    df = make_raw(200)
    clean = preprocess.preprocess_pipeline(df)
    assert len(clean) == 200
    assert "load_change_pct" in clean.columns
