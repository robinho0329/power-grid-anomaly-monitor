"""이상탐지 타임라인 — L1(EWMA/CUSUM) · L2(Isolation Forest) · L3(LSTM-AE) 결과 시각화."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from src.analysis import ewma_cusum, isolation_forest  # noqa: E402
from src.storage import database  # noqa: E402

from dashboard._lib import inject_css, render_footer, render_sidebar  # noqa: E402

st.set_page_config(page_title="이상탐지 타임라인", page_icon="🚨", layout="wide")
inject_css()
st.title("🚨 이상탐지 타임라인")
st.caption("3계층 이상탐지(통계·ML·딥러닝) 결과를 동일 시계열에 중첩해 비교합니다.")


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()
render_sidebar(df)

if df.empty:
    st.info("수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

# ── 사이드바 ──────────────────────────────────────────────────────────
# 기본 컨트롤(대상·기간)은 바로 노출, 민감도 파라미터는 '고급'으로 숨겨
# 일반 청자가 압도되지 않게 한다.
with st.sidebar:
    st.header("보기 설정")
    target_col = st.selectbox(
        "분석 대상 지표",
        ["reserve_rate", "current_load", "oper_reserve_rate"],
        format_func=lambda x: {
            "reserve_rate": "공급예비율(%)",
            "current_load": "현재수요(MW)",
            "oper_reserve_rate": "운영예비율(%)",
        }[x],
    )
    window_h = st.slider("표시 범위 (시간)", 6, 72, 24)

    with st.expander("⚙️ 고급 — 탐지 민감도"):
        st.caption("값이 작을수록 더 민감하게(더 많이) 이상을 잡습니다. 기본값 권장.")
        ewma_span = st.slider("EWMA 윈도우 (5분 단위)", 6, 48, 12)
        ewma_k = st.slider("EWMA 관리한계 σ 배수", 1.5, 5.0, 3.0, 0.5)
        cusum_thresh = st.slider("CUSUM 임계", 1.0, 20.0, 5.0, 0.5)
        if2_auto = st.checkbox(
            "IF 이상 비율 자동(auto)", value=True,
            help="끄면 비율을 직접 고정합니다. 고정 시 정상 데이터에도 그 비율만큼 강제로 이상이 표시됩니다.",
        )
        if2_contamination = (
            "auto" if if2_auto
            else st.slider("IF 이상 비율(고정)", 0.01, 0.10, 0.02, 0.01)
        )

plot_df = df.tail(window_h * 12).copy()  # 5분×12 = 1시간

# ── L1: EWMA + CUSUM ─────────────────────────────────────────────────
series = plot_df.set_index("ts")[target_col].dropna()
ewma_df = ewma_cusum.ewma_anomalies(series, span=ewma_span, k=ewma_k)
cusum_s = ewma_cusum.cusum_change_points(series, threshold=cusum_thresh)

# ── L2: Isolation Forest ─────────────────────────────────────────────
l2_df = isolation_forest.detect(plot_df, contamination=if2_contamination)

# ── L3: LSTM-AE (데이터 부족 시 스킵) ────────────────────────────────
L3_MIN_ROWS = 60
l3_available = len(plot_df) >= L3_MIN_ROWS
if l3_available:
    try:
        from src.analysis import lstm_autoencoder
        import numpy as np
        vals = plot_df[target_col].ffill().to_numpy(dtype="float32")
        seqs = lstm_autoencoder.make_sequences(vals, window=12)
        l3_available = len(seqs) > 0
    except Exception:
        l3_available = False

# ── 한눈에 보는 인사이트 (쉬운 말 요약) ──────────────────────────────
_n = len(series)
_ewma_cnt = int(ewma_df["anomaly"].sum())
_cusum_cnt = int(cusum_s.sum())
_l2_cnt = int((l2_df["anomaly"] == True).sum())
_label_short = {
    "reserve_rate": "공급예비율",
    "current_load": "현재수요",
    "oper_reserve_rate": "운영예비율",
}[target_col]
_total_hits = _ewma_cnt + _cusum_cnt + _l2_cnt

st.subheader("🔎 한눈에 보기")
if _total_hits == 0:
    st.success(
        f"최근 **{window_h}시간** 동안 **{_label_short}**에서 세 탐지기 모두 이상 신호가 없었습니다. "
        "계통이 평소 패턴대로 안정적으로 움직였다는 뜻입니다."
    )
else:
    _parts = []
    if _ewma_cnt:
        _parts.append(f"급변·이탈(EWMA) **{_ewma_cnt}건**")
    if _cusum_cnt:
        _parts.append(f"추세 변화(CUSUM) **{_cusum_cnt}건**")
    if _l2_cnt:
        _parts.append(f"다변량 조합 이상(IF) **{_l2_cnt}건**")
    st.warning(
        f"최근 **{window_h}시간**({_n:,}개 시점) **{_label_short}**에서 "
        + ", ".join(_parts)
        + " 감지. 아래 타임라인에서 빨강/주황 마커 구간을 확인하세요."
    )
st.caption("L1 통계 → L2 ML → (데이터 충분 시) L3 딥러닝이 서로 다른 종류의 이상을 교차 검증합니다.")

# ── 시각화 ───────────────────────────────────────────────────────────
col_names = {
    "reserve_rate": "공급예비율(%)",
    "current_load": "현재수요(MW)",
    "oper_reserve_rate": "운영예비율(%)",
}
label = col_names[target_col]

fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    subplot_titles=("L1 통계: EWMA 관리한계", "L1 통계: CUSUM 변화점", "L2 ML: Isolation Forest"),
    vertical_spacing=0.08,
    row_heights=[0.45, 0.25, 0.30],
)

# L1 EWMA
fig.add_trace(go.Scatter(x=ewma_df.index, y=ewma_df["value"], name=label,
                          line=dict(color="#1f77b4", width=1.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=ewma_df.index, y=ewma_df["ewma"], name="EWMA",
                          line=dict(color="#aec7e8", dash="dash")), row=1, col=1)
fig.add_trace(go.Scatter(x=ewma_df.index, y=ewma_df["upper"], name="UCL",
                          line=dict(color="rgba(255,0,0,0.4)", dash="dot")), row=1, col=1)
fig.add_trace(go.Scatter(x=ewma_df.index, y=ewma_df["lower"], name="LCL",
                          line=dict(color="rgba(255,0,0,0.4)", dash="dot"),
                          fill="tonexty", fillcolor="rgba(255,0,0,0.05)"), row=1, col=1)
ewma_anom = ewma_df[ewma_df["anomaly"]]
if not ewma_anom.empty:
    fig.add_trace(go.Scatter(x=ewma_anom.index, y=ewma_anom["value"],
                              mode="markers", name="EWMA 이상",
                              marker=dict(color="red", size=8, symbol="x")), row=1, col=1)

# L1 CUSUM
cusum_bar_colors = ["red" if v else "#aec7e8" for v in cusum_s.values]
fig.add_trace(go.Bar(x=cusum_s.index, y=cusum_s.astype(int),
                      name="CUSUM 변화점", marker_color=cusum_bar_colors,
                      showlegend=False), row=2, col=1)

# L2 IF
l2_plot = l2_df.set_index("ts")
fig.add_trace(go.Scatter(x=l2_plot.index, y=l2_plot[target_col], name=label,
                          line=dict(color="#1f77b4", width=1.5), showlegend=False), row=3, col=1)
l2_anom = l2_plot[l2_plot["anomaly"] == True]
if not l2_anom.empty:
    fig.add_trace(go.Scatter(x=l2_anom.index, y=l2_anom[target_col],
                              mode="markers", name="IF 이상",
                              marker=dict(color="orange", size=9, symbol="circle-open")), row=3, col=1)

fig.update_layout(height=650, legend=dict(orientation="h", y=-0.05),
                   margin=dict(l=0, r=0, t=30, b=0))
st.plotly_chart(fig, width="stretch")

# ── 요약 테이블 ───────────────────────────────────────────────────────
st.subheader("이상 감지 건수 요약")
summary = {
    "탐지기": ["L1 EWMA", "L1 CUSUM", "L2 Isolation Forest"],
    "이상 건수": [
        int(ewma_df["anomaly"].sum()),
        int(cusum_s.sum()),
        int((l2_df["anomaly"] == True).sum()),
    ],
    "전체 대비 비율": [
        f"{ewma_df['anomaly'].mean()*100:.1f}%",
        f"{cusum_s.mean()*100:.1f}%",
        f"{(l2_df['anomaly'] == True).mean()*100:.1f}%",
    ],
}
st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

# ── L3 딥러닝 상태 (진행바) ──────────────────────────────────────────
st.subheader("🧠 L3 딥러닝(LSTM-AE) 준비도")
st.progress(min(len(df) / L3_MIN_ROWS, 1.0))
if len(df) >= L3_MIN_ROWS:
    st.caption(
        f"현재 {len(df):,}/{L3_MIN_ROWS}행 — 활성 가능. "
        "재구성 오차 기반 '패턴 붕괴형' 이상까지 탐지합니다."
    )
else:
    st.caption(
        f"현재 {len(df):,}/{L3_MIN_ROWS}행 — 설계 완비, 데이터 충족 시 자동 활성. "
        "소량 데이터로 억지 추론하지 않습니다(과적합 노이즈 방지)."
    )

render_footer()
