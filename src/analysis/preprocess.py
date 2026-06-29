"""EDA & 전처리 — 수집된 전력수급 시계열을 분석 가능한 형태로 정제.

수집 원본(power_supply)은 5분 단위 스냅샷이지만 누락·중복·이상값이 섞일 수 있다.
이 모듈은 ① 시계열 정렬·중복 제거 ② 결측 보간 ③ 파생 변수(시간·요일·수요변화율)
④ EDA 요약 통계 산출을 담당해, 이상탐지·대시보드·PPT가 공통으로 쓰는 정제 데이터를 만든다.

제조 메타포: '원자재 입고 검사 → 전처리 → 라인 투입'에 해당하는 단계.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

# 분석 대상 수치 컬럼 (수급 지표)
NUMERIC_COLS = [
    "supply_capacity",
    "current_load",
    "forecast_load",
    "reserve_power",
    "reserve_rate",
    "oper_reserve_power",
    "oper_reserve_rate",
]


def clean_timeseries(df: pd.DataFrame, freq: str = "5min") -> pd.DataFrame:
    """시계열 정렬·중복 제거·균일 그리드 리샘플링.

    Parameters
    ----------
    df   : load_df() 결과 (ts 컬럼 보유)
    freq : 목표 주기 (KPX 5분)
    """
    if df.empty:
        return df.copy()

    work = df.copy()
    work["ts"] = pd.to_datetime(work["ts"])
    work = work.drop_duplicates(subset="ts").sort_values("ts").set_index("ts")

    # 균일 5분 그리드로 재색인 (누락 슬롯은 NaN으로 드러남)
    full_idx = pd.date_range(work.index.min(), work.index.max(), freq=freq)
    work = work.reindex(full_idx)
    work.index.name = "ts"
    return work.reset_index()


def fill_missing(df: pd.DataFrame, max_gap: int = 6) -> pd.DataFrame:
    """결측 보간 — 짧은 갭(기본 30분=6스텝)은 시간 보간, 긴 갭은 NaN 유지.

    긴 정전·수집 중단을 보간으로 메우면 이상탐지가 왜곡되므로 max_gap으로 제한한다.
    """
    if df.empty:
        return df.copy()

    work = df.copy().set_index("ts")
    for col in NUMERIC_COLS:
        if col in work.columns:
            work[col] = work[col].interpolate(
                method="time", limit=max_gap, limit_area="inside"
            )
    return work.reset_index()


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """파생 변수 추가 — 시간/요일/주말, 수요 변화율, 예비율 마진, 예측오차.

    이상탐지(L2 다변량)와 대시보드 분석에 활용되는 피처들.
    """
    if df.empty:
        return df.copy()

    work = df.copy()
    work["ts"] = pd.to_datetime(work["ts"])

    # 시간 피처
    work["hour"] = work["ts"].dt.hour
    work["dayofweek"] = work["ts"].dt.dayofweek          # 0=월, 6=일
    work["is_weekend"] = work["dayofweek"].isin([5, 6]).astype(int)

    # 수요 변화율 (직전 대비 % 변화) — 스파이크 탐지용
    if "current_load" in work.columns:
        work["load_change_pct"] = work["current_load"].pct_change() * 100
        # 수요 가속도 (변화율의 변화) — 급변 탐지용
        work["load_accel"] = work["load_change_pct"].diff()

    # 예측 오차 (실제 - 예측) — 잔차 기반 탐지용
    if "current_load" in work.columns and "forecast_load" in work.columns:
        work["forecast_error"] = work["current_load"] - work["forecast_load"]
        work["forecast_error_pct"] = (
            work["forecast_error"] / work["forecast_load"] * 100
        )

    # 공급 마진 (공급능력 - 현재수요) — 절대 여유
    if "supply_capacity" in work.columns and "current_load" in work.columns:
        work["supply_margin"] = work["supply_capacity"] - work["current_load"]

    return work


def eda_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """EDA 요약 통계 — 데이터 개요, 결측률, 기술통계, 상관, 피크 정보.

    PPT·데일리 리포트·대시보드 헤더에서 공통으로 사용.
    """
    if df.empty:
        return {"empty": True, "n_rows": 0}

    work = df.copy()
    work["ts"] = pd.to_datetime(work["ts"])

    present_numeric = [c for c in NUMERIC_COLS if c in work.columns]

    summary: Dict[str, Any] = {
        "empty": False,
        "n_rows": len(work),
        "time_range": (work["ts"].min(), work["ts"].max()),
        "duration_hours": (work["ts"].max() - work["ts"].min()).total_seconds() / 3600,
        "missing_rate": {
            c: float(work[c].isna().mean()) for c in present_numeric
        },
        "describe": work[present_numeric].describe().to_dict(),
    }

    # 수요 피크/저점
    if "current_load" in work.columns and work["current_load"].notna().any():
        peak_idx = work["current_load"].idxmax()
        trough_idx = work["current_load"].idxmin()
        summary["load_peak"] = {
            "ts": work.loc[peak_idx, "ts"],
            "value": float(work.loc[peak_idx, "current_load"]),
        }
        summary["load_trough"] = {
            "ts": work.loc[trough_idx, "ts"],
            "value": float(work.loc[trough_idx, "current_load"]),
        }

    # 최저 예비율 (위험 시점)
    if "reserve_rate" in work.columns and work["reserve_rate"].notna().any():
        min_idx = work["reserve_rate"].idxmin()
        summary["min_reserve"] = {
            "ts": work.loc[min_idx, "ts"],
            "value": float(work.loc[min_idx, "reserve_rate"]),
        }

    # 수치 컬럼 간 상관 (수요-예비율 등 관계 확인)
    if len(present_numeric) >= 2:
        corr = work[present_numeric].corr()
        summary["correlation"] = corr.to_dict()

    return summary


def preprocess_pipeline(
    df: pd.DataFrame, freq: str = "5min", max_gap: int = 6
) -> pd.DataFrame:
    """전처리 풀 파이프라인: 정렬·리샘플 → 결측보간 → 파생변수.

    수집 원본을 받아 이상탐지·대시보드·PPT가 바로 쓸 수 있는 정제 DataFrame 반환.
    """
    df = clean_timeseries(df, freq=freq)
    df = fill_missing(df, max_gap=max_gap)
    df = add_features(df)
    return df
