"""L2 ML 이상탐지 — Isolation Forest (다변량).

수요·예비율·발전믹스·기온을 동시에 보고 '조합의 이상'을 잡는다.
(각 지표는 정상범위인데 함께 보면 비정상인 경우)
"""
from __future__ import annotations

import pandas as pd
from sklearn.ensemble import IsolationForest


def detect(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    contamination: float = 0.02,
    random_state: int = 42,
) -> pd.DataFrame:
    """다변량 이상탐지. 입력 df에 anomaly(bool), score(float) 컬럼을 붙여 반환.

    score는 낮을수록 이상(IsolationForest.decision_function 기준).
    """
    feature_cols = feature_cols or [
        c for c in ("current_load", "reserve_rate", "temperature") if c in df.columns
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
    pred = model.fit_predict(X)            # -1 = 이상
    score = model.decision_function(X)     # 낮을수록 이상

    out = df.copy()
    out["anomaly"] = False
    out["score"] = pd.NA
    out.loc[work.index, "anomaly"] = pred == -1
    out.loc[work.index, "score"] = score
    return out
