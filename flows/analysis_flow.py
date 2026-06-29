"""분석 플로우 — 정제 → 다층 이상탐지 통합 오케스트레이션.

수집(collect_flow)이 쌓은 원본을 받아 다음을 순차 수행한다:
    load → preprocess(EDA/전처리) → L1 통계 → L2 ML → (L3 DL, 데이터 충분 시) → 요약

대시보드·PPT·데일리 리포트가 공통으로 호출하는 '분석 1회 실행' 진입점.
제조 메타포: 라인 투입된 자재를 다단 검사 게이트(통계→ML→DL)로 통과시키는 과정.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

from src.analysis import demand_forecast, ewma_cusum, isolation_forest, preprocess
from src.storage import database

logger = logging.getLogger(__name__)

# L3 딥러닝(LSTM-AE) 활성화 최소 행 수 (5분×60 = 5시간)
L3_MIN_ROWS = 60


def run_analysis(
    df: pd.DataFrame | None = None,
    target_col: str = "reserve_rate",
) -> Dict[str, Any]:
    """분석 1회 실행. df 미지정 시 DB에서 로드.

    Returns
    -------
    dict — 정제 데이터(clean_df) + 각 계층 탐지 결과 + EDA 요약.
    """
    # 1) 로드
    if df is None:
        df = database.load_df()

    if df.empty:
        logger.warning("분석할 데이터가 없습니다.")
        return {"empty": True, "n_rows": 0}

    # 2) EDA & 전처리
    clean = preprocess.preprocess_pipeline(df)
    eda = preprocess.eda_summary(clean)
    logger.info("전처리 완료: %d행", len(clean))

    series = clean.set_index("ts")[target_col].dropna()

    result: Dict[str, Any] = {
        "empty": False,
        "n_rows": len(clean),
        "clean_df": clean,
        "eda": eda,
        "target_col": target_col,
        "detections": {},
    }

    # 3) L1 통계 — EWMA + CUSUM
    try:
        ewma_df = ewma_cusum.ewma_anomalies(series)
        cusum_s = ewma_cusum.cusum_change_points(series)
        result["detections"]["L1_ewma"] = {
            "n_anomalies": int(ewma_df["anomaly"].sum()),
            "rate": float(ewma_df["anomaly"].mean()),
            "df": ewma_df,
        }
        result["detections"]["L1_cusum"] = {
            "n_anomalies": int(cusum_s.sum()),
            "rate": float(cusum_s.mean()),
            "series": cusum_s,
        }
        logger.info("L1 통계: EWMA %d건, CUSUM %d건",
                    result["detections"]["L1_ewma"]["n_anomalies"],
                    result["detections"]["L1_cusum"]["n_anomalies"])
    except Exception as e:  # noqa: BLE001
        logger.warning("L1 탐지 실패: %s", e)

    # 4) L2 ML — Isolation Forest (다변량)
    try:
        l2 = isolation_forest.detect(clean)
        result["detections"]["L2_iforest"] = {
            "n_anomalies": int((l2["anomaly"] == True).sum()),
            "rate": float((l2["anomaly"] == True).mean()),
            "df": l2,
        }
        logger.info("L2 ML: Isolation Forest %d건",
                    result["detections"]["L2_iforest"]["n_anomalies"])
    except Exception as e:  # noqa: BLE001
        logger.warning("L2 탐지 실패: %s", e)

    # 5) 수요 예측 + 잔차 기반 탐지
    try:
        res_df = demand_forecast.residual_anomalies(series)
        result["detections"]["residual"] = {
            "n_anomalies": int(res_df["anomaly"].sum()),
            "rate": float(res_df["anomaly"].mean()),
            "df": res_df,
        }
        logger.info("잔차 기반: %d건",
                    result["detections"]["residual"]["n_anomalies"])
    except Exception as e:  # noqa: BLE001
        logger.warning("잔차 탐지 실패: %s", e)

    # 6) L3 딥러닝 — LSTM-AE (데이터 충분 시)
    if len(clean) >= L3_MIN_ROWS:
        try:
            result["detections"]["L3_lstm"] = _run_l3(clean, target_col)
            logger.info("L3 DL: LSTM-AE %d건",
                        result["detections"]["L3_lstm"]["n_anomalies"])
        except Exception as e:  # noqa: BLE001
            logger.warning("L3 탐지 스킵(TF 미설치/오류): %s", e)
            result["detections"]["L3_lstm"] = {"skipped": True, "reason": str(e)}
    else:
        result["detections"]["L3_lstm"] = {
            "skipped": True,
            "reason": f"데이터 부족 ({len(clean)}<{L3_MIN_ROWS}행)",
        }

    return result


def _run_l3(clean: pd.DataFrame, target_col: str) -> Dict[str, Any]:
    """L3 LSTM-AutoEncoder 재구성 오차 기반 탐지 (TF 지연 import)."""
    import numpy as np

    from src.analysis import lstm_autoencoder as lae

    vals = clean[target_col].ffill().bfill().to_numpy(dtype="float32")
    # 정규화 (재구성 오차 안정화)
    mu, sigma = vals.mean(), vals.std() + 1e-8
    norm = (vals - mu) / sigma

    window = 12
    seqs = lae.make_sequences(norm, window=window)
    if len(seqs) < 10:
        raise ValueError("시퀀스 부족")

    # 앞 70%로 정상 패턴 학습 → 전체 재구성 오차
    split = int(len(seqs) * 0.7)
    model = lae.build_model(window=window, n_features=1)
    model.fit(seqs[:split], seqs[:split], epochs=10, batch_size=16, verbose=0)
    errors = lae.reconstruction_error(model, seqs)

    # 임계: 학습구간 평균 + 3σ
    threshold = errors[:split].mean() + 3 * errors[:split].std()
    anomaly_flags = errors > threshold

    return {
        "n_anomalies": int(anomaly_flags.sum()),
        "rate": float(anomaly_flags.mean()),
        "threshold": float(threshold),
        "errors": errors,
        "skipped": False,
    }


def detection_summary(result: Dict[str, Any]) -> str:
    """탐지 결과를 한 줄 요약 문자열로 (알림·로그용)."""
    if result.get("empty"):
        return "데이터 없음 — 분석 생략"
    det = result.get("detections", {})
    parts = []
    for key, label in [
        ("L1_ewma", "EWMA"),
        ("L1_cusum", "CUSUM"),
        ("L2_iforest", "IForest"),
        ("residual", "잔차"),
        ("L3_lstm", "LSTM-AE"),
    ]:
        d = det.get(key, {})
        if d.get("skipped"):
            parts.append(f"{label}:스킵")
        elif "n_anomalies" in d:
            parts.append(f"{label}:{d['n_anomalies']}건")
    return " · ".join(parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    res = run_analysis()
    if res.get("empty"):
        print("분석할 데이터가 없습니다. 먼저 수집하세요: python -m scripts.collect_once")
    else:
        print(f"\n📊 분석 완료 — {res['n_rows']}행")
        print(f"   탐지 요약: {detection_summary(res)}")
