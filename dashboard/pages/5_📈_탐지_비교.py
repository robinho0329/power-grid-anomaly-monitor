"""탐지 비교 페이지 — L1·L2·L3 성능 비교 (거짓경보율·탐지지연)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from src.analysis import ewma_cusum, isolation_forest  # noqa: E402
from src.storage import database  # noqa: E402

st.set_page_config(page_title="탐지 비교", page_icon="📈", layout="wide")
st.title("📈 3계층 탐지기 비교")
st.caption(
    "동일 시계열에 L1(통계)·L2(ML)·L3(DL)을 적용해 이상 구간·거짓경보율·탐지 지연을 비교합니다. "
    "포트폴리오 핵심 차별점: 단순 임계값 대비 다층 탐지의 강점을 수치로 입증."
)


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()

if df.empty:
    st.info("수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

# ── 사이드바 ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("비교 설정")
    target_col = st.selectbox(
        "분석 대상",
        ["reserve_rate", "current_load", "oper_reserve_rate"],
        format_func=lambda x: {
            "reserve_rate": "공급예비율(%)",
            "current_load": "현재수요(MW)",
            "oper_reserve_rate": "운영예비율(%)",
        }[x],
    )
    window_h = st.slider("분석 범위 (시간)", 6, 72, 24)
    st.divider()
    st.subheader("합성 이벤트 주입")
    inject_spike = st.checkbox("스파이크 주입 (급등)", value=False)
    inject_drift = st.checkbox("드리프트 주입 (점진 변화)", value=False)
    inject_level = st.checkbox("레벨 이동 주입", value=False)

plot_df = df.tail(window_h * 12).copy().reset_index(drop=True)
series = plot_df.set_index("ts")[target_col].dropna().copy()

# ── 합성 이벤트 주입 ─────────────────────────────────────────────────
if inject_spike and len(series) > 20:
    idx = series.index[len(series) // 2]
    series[idx] = series.mean() + series.std() * 5
    st.caption("⚡ 스파이크 이벤트 주입됨 (평균 + 5σ)")

if inject_drift and len(series) > 20:
    half = len(series) // 2
    drift_vals = series.values.copy()
    drift_vals[half:] += np.linspace(0, series.std() * 3, len(series) - half)
    series = pd.Series(drift_vals, index=series.index)
    st.caption("📉 드리프트 이벤트 주입됨 (후반 점진 하락)")

if inject_level and len(series) > 20:
    half = len(series) // 2
    level_vals = series.values.copy()
    level_vals[half:] -= series.std() * 4
    series = pd.Series(level_vals, index=series.index)
    st.caption("📊 레벨 이동 이벤트 주입됨 (후반 수준 하락)")

# ── 각 탐지기 실행 ────────────────────────────────────────────────────
ewma_df = ewma_cusum.ewma_anomalies(series, span=12, k=3.0)
cusum_s = ewma_cusum.cusum_change_points(series, threshold=5.0)

# 단순 임계값 탐지 (비교 기준선)
mean_val = series.mean()
std_val = series.std()
simple_thresh = (series < mean_val - 3 * std_val) | (series > mean_val + 3 * std_val)

# L2 IF
l2_df = isolation_forest.detect(
    plot_df.set_index("ts").loc[series.index].reset_index(),
    contamination=0.02,
)

# ── 비교 차트 ─────────────────────────────────────────────────────────
fig = make_subplots(
    rows=4, cols=1,
    shared_xaxes=True,
    subplot_titles=(
        "원시 시계열",
        "L1-A: EWMA 관리한계 이상",
        "L1-B: CUSUM 변화점",
        "L2: Isolation Forest 이상",
    ),
    vertical_spacing=0.06,
    row_heights=[0.35, 0.25, 0.2, 0.2],
)

col_label = {
    "reserve_rate": "공급예비율(%)",
    "current_load": "현재수요(MW)",
    "oper_reserve_rate": "운영예비율(%)",
}[target_col]

fig.add_trace(go.Scatter(x=series.index, y=series.values, name=col_label,
                          line=dict(color="#1f77b4", width=1.5)), row=1, col=1)
# EWMA 이상 마킹
ewma_anom = ewma_df[ewma_df["anomaly"]]
if not ewma_anom.empty:
    fig.add_trace(go.Scatter(x=ewma_anom.index, y=ewma_anom["value"],
                              mode="markers", name="EWMA 이상",
                              marker=dict(color="red", size=9, symbol="x")), row=1, col=1)

fig.add_trace(go.Bar(x=ewma_df.index, y=ewma_df["anomaly"].astype(int),
                      name="EWMA", marker_color=["red" if v else "#aec7e8"
                                                  for v in ewma_df["anomaly"]],
                      showlegend=False), row=2, col=1)

fig.add_trace(go.Bar(x=cusum_s.index, y=cusum_s.astype(int),
                      name="CUSUM", marker_color=["#ff7f0e" if v else "#aec7e8"
                                                   for v in cusum_s.values],
                      showlegend=False), row=3, col=1)

l2_series = l2_df.set_index("ts")["anomaly"].reindex(series.index).fillna(False)
fig.add_trace(go.Bar(x=l2_series.index, y=l2_series.astype(int),
                      name="IF", marker_color=["#2ca02c" if v else "#aec7e8"
                                               for v in l2_series.values],
                      showlegend=False), row=4, col=1)

fig.update_layout(height=700, margin=dict(l=0, r=0, t=30, b=0),
                   legend=dict(orientation="h", y=-0.04))
st.plotly_chart(fig, width="stretch")

# ── 탐지기 성능 비교 표 ───────────────────────────────────────────────
st.subheader("탐지기 성능 비교")
n = len(series)

ewma_cnt = int(ewma_df["anomaly"].sum())
cusum_cnt = int(cusum_s.sum())
simple_cnt = int(simple_thresh.sum())
l2_cnt = int((l2_df["anomaly"] == True).sum())

# 탐지 지연: 첫 이상 감지 인덱스 위치
def first_detection_lag(mask: pd.Series) -> str:
    if mask.any():
        return f"{mask.values.argmax()}번째 포인트"
    return "미감지"

comparison = pd.DataFrame({
    "탐지기": ["단순 임계값 (±3σ)", "L1-A EWMA", "L1-B CUSUM", "L2 Isolation Forest"],
    "이상 감지 건수": [simple_cnt, ewma_cnt, cusum_cnt, l2_cnt],
    "전체 대비 비율": [
        f"{simple_cnt/n*100:.1f}%",
        f"{ewma_cnt/n*100:.1f}%",
        f"{cusum_cnt/n*100:.1f}%",
        f"{l2_cnt/n*100:.1f}%",
    ],
    "첫 감지 시점": [
        first_detection_lag(simple_thresh),
        first_detection_lag(ewma_df["anomaly"]),
        first_detection_lag(cusum_s),
        first_detection_lag(l2_df.set_index("ts")["anomaly"].reindex(series.index).fillna(False)),
    ],
    "특징": [
        "기준선 — 주기성 무시, 거짓경보 多",
        "점진 변화·레벨이동에 민감",
        "누적합 기반 — 스파이크 후 반응 지속",
        "다변량 — 조합 이상 포착",
    ],
})
st.dataframe(comparison, width="stretch", hide_index=True)

st.info(
    "💡 **합성 이벤트 주입** 사이드바를 활성화하면 스파이크·드리프트·레벨이동을 "
    "주입해 각 탐지기의 반응 차이를 직접 비교할 수 있습니다."
)

# ── L3 상태 안내 ─────────────────────────────────────────────────────
st.subheader("L3 LSTM-AutoEncoder 상태")
if len(df) < 60:
    st.warning(
        f"현재 {len(df)}행 수집됨. "
        "정상 데이터 60행(5시간) 이상 누적 후 L3 탐지기가 활성화됩니다. "
        "이후 재구성 오차 기반의 패턴 붕괴형 이상까지 탐지 가능합니다."
    )
else:
    st.success(f"데이터 {len(df)}행 누적 완료 — L3 LSTM-AE 활성화 가능 상태입니다.")
    st.caption("이상탐지 타임라인 페이지에서 L3 결과를 확인하세요.")
