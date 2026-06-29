"""L2 ML 이상탐지 — Isolation Forest (다변량).

수요·예비율·발전믹스·기온을 동시에 보고 '조합의 이상'을 잡는다.
(각 지표는 정상범위인데 함께 보면 비정상인 경우)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def detect(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    contamination: float | str = "auto",
    random_state: int = 42,
) -> pd.DataFrame:
    """다변량 이상탐지. 입력 df에 anomaly(bool), score(float) 컬럼을 붙여 반환.

    score는 낮을수록 이상(IsolationForest.decision_function 기준).

    contamination
        "auto"(기본): 강제 비율 없이 이상점수(score_samples)에 robust(MAD) 임계를
        적용 → 정상 데이터엔 이상이 거의 0건. 정직한 기본값.
        float(예: 0.02): 항상 그 비율을 이상으로 강제 라벨링(sklearn predict) →
        정상 데이터에도 2%가 찍히므로 '데모로 비율을 고정'할 때만 명시적으로 사용.
    """
    feature_cols = feature_cols or [
        c
        for c in ("current_load", "reserve_rate", "oper_reserve_rate", "forecast_load")
        if c in df.columns
    ]
    work = df.dropna(subset=feature_cols)
    if work.empty:
        out = df.copy()
        out["anomaly"] = False
        out["score"] = pd.NA
        return out

    model = IsolationForest(
        contamination=contamination, random_state=random_state, n_estimators=200
    )
    X = work[feature_cols].to_numpy()
    model.fit(X)
    score = model.score_samples(X)  # 낮을수록 이상

    if contamination == "auto":
        # 강제 비율 대신 robust(중앙값±MAD) 임계 — 정상 분포엔 거의 0건,
        # 진짜 동떨어진 점수만 이상으로 표시한다.
        # k=6: 정상(노이즈) 분포에선 0건, 뚜렷이 동떨어진 점만 이상으로.
        # (경험적으로 정상 최저점수는 ~5.3 MAD, 명백한 outlier는 >11 MAD)
        med = float(np.median(score))
        mad = float(np.median(np.abs(score - med))) * 1.4826
        thr = med - 6.0 * mad if mad > 0 else float(np.min(score)) - 1.0
        anomaly = score < thr
    else:
        anomaly = model.predict(X) == -1  # float이면 그 비율을 강제 라벨링

    out = df.copy()
    out["anomaly"] = False
    out["score"] = pd.NA
    out.loc[work.index, "anomaly"] = anomaly
    out.loc[work.index, "score"] = score
    return out
