"""수요 예측 + 잔차 기반 이상탐지.

전력수요는 강한 일주기·주기주기 패턴을 가지므로,
단순 임계값 대신 '예측값 대비 잔차'에 이상탐지를 적용해 거짓경보를 줄인다.

접근 방식:
  1. 주기성 제거: 동일 요일·시간대 평균을 기준 예측치로 사용 (훈련 불필요)
  2. 잔차 = 실제값 - 기준 예측치
  3. 잔차에 EWMA 관리한계 적용 → 예상 외 급변만 이상으로 표시
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.analysis.ewma_cusum import ewma_anomalies


def _fit_baseline_map(series: pd.Series) -> Tuple[pd.Series, float]:
    """요일·시간대 평균 룩업맵과 전체 평균(폴백)을 적합.

    이 맵을 별도로 분리한 이유: 학습/평가 분할 시 train 구간으로만 적합한 뒤
    test 구간에 매핑해야 데이터 누수가 없기 때문(evaluate_forecast 참고).
    """
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    idx = s.index
    keys = pd.DataFrame({"value": s.values, "dow": idx.dayofweek, "hm": idx.strftime("%H:%M")})
    baseline_map = keys.groupby(["dow", "hm"])["value"].mean()
    return baseline_map, float(s.mean())


def _apply_baseline_map(
    index: pd.Index,
    baseline_map: pd.Series,
    fallback: float,
) -> pd.Series:
    """적합된 룩업맵을 임의 인덱스(요일·시간대)에 매핑. 미존재 키는 폴백 평균."""
    idx = pd.to_datetime(pd.Index(index))
    vals = [
        baseline_map.get((d, h), np.nan)
        for d, h in zip(idx.dayofweek, idx.strftime("%H:%M"))
    ]
    return pd.Series(vals, index=index, dtype=float).fillna(fallback)


def build_seasonal_baseline(
    series: pd.Series,
    freq: str = "5min",
) -> pd.Series:
    """요일·시간대 평균으로 계절 기준선 구성.

    Parameters
    ----------
    series : DatetimeIndex를 가진 수요 시계열
    freq   : 원본 데이터 주기 (기본 5분)
    """
    baseline_map, fallback = _fit_baseline_map(series)
    return _apply_baseline_map(series.index, baseline_map, fallback)


def residual_anomalies(
    series: pd.Series,
    ewma_span: int = 12,
    k: float = 3.0,
) -> pd.DataFrame:
    """잔차(실제 - 계절 기준선)에 EWMA 관리한계를 적용해 이상탐지.

    Returns
    -------
    DataFrame with columns:
        value      : 원본 값
        baseline   : 계절 기준선
        residual   : 잔차 (value - baseline)
        ewma       : 잔차 EWMA
        upper/lower: 관리한계
        anomaly    : 이상 여부 (bool)
    """
    baseline = build_seasonal_baseline(series)
    residual = series - baseline

    ewma_df = ewma_anomalies(residual, span=ewma_span, k=k)
    ewma_df.rename(columns={"value": "residual"}, inplace=True)
    ewma_df.insert(0, "value", series.values)
    ewma_df.insert(1, "baseline", baseline.values)
    return ewma_df


def forecast_next_n(
    series: pd.Series,
    n: int = 12,
) -> pd.Series:
    """계절 기준선 기반 단기 예측 (n 스텝 선행).

    학습 없이 '같은 요일·시간대 평균'으로 예측.
    데이터 누적이 적을 때도 즉시 사용 가능.
    """
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    freq = pd.infer_freq(s.index) or "5min"

    future_idx = pd.date_range(
        start=s.index[-1] + pd.tseries.frequencies.to_offset(freq),
        periods=n,
        freq=freq,
    )
    future_series = pd.Series(index=future_idx, dtype=float)
    baseline = build_seasonal_baseline(pd.concat([s, future_series]))
    return baseline.loc[future_idx]


def evaluate_forecast(
    series: pd.Series,
    test_ratio: float = 0.2,
) -> Tuple[pd.DataFrame, dict]:
    """예측 성능 평가 — MAE·RMSE·MAPE 반환.

    hold-out 방식: 마지막 test_ratio 구간을 테스트로 사용.
    """
    n = len(series)
    split = int(n * (1 - test_ratio))
    train = series.iloc[:split]
    test = series.iloc[split:]

    # 데이터 누수 방지: 기준선은 train 구간으로만 적합한 뒤 test에 매핑한다.
    # (전체 series로 적합하면 test 정보가 기준선에 새어 MAE/MAPE가 낙관 편향됨)
    baseline_map, fallback = _fit_baseline_map(train)
    baseline_test = _apply_baseline_map(test.index, baseline_map, fallback)
    residuals = test - baseline_test

    mae = float(np.abs(residuals).mean())
    rmse = float(np.sqrt((residuals ** 2).mean()))
    mape = float((np.abs(residuals / test.replace(0, np.nan))).mean() * 100)

    result_df = pd.DataFrame({
        "actual": test,
        "forecast": baseline_test,
        "residual": residuals,
    })
    metrics = {"MAE": mae, "RMSE": rmse, "MAPE(%)": mape, "n_test": len(test)}
    return result_df, metrics
