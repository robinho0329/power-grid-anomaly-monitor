"""수요 예측 + 잔차 기반 이상탐지 페이지."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.analysis.demand_forecast import (  # noqa: E402
    evaluate_forecast,
    forecast_next_n,
    residual_anomalies,
)
from src.storage import database  # noqa: E402

from dashboard._lib import (  # noqa: E402
    dash_header,
    inject_css,
    render_footer,
    render_sidebar,
    style_fig,
)

st.set_page_config(page_title="수요 예측", page_icon="🔮", layout="wide")
inject_css()
dash_header(
    "🔮 수요 예측 + 잔차 기반 이상탐지",
    "일주기·주간주기 패턴을 기준선으로 제거한 뒤 잔차에 이상탐지 · 단순 임계값의 주기성 거짓경보를 줄이도록 설계",
)


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()
render_sidebar(df)

if df.empty:
    st.info("수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

# ── 사이드바 ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("예측 설정")
    target_col = st.selectbox(
        "예측 대상",
        ["current_load", "reserve_rate"],
        format_func=lambda x: {
            "current_load": "현재수요(MW)",
            "reserve_rate": "공급예비율(%)",
        }[x],
    )
    window_h = st.slider("분석 범위 (시간)", 6, 168, 48)
    with st.expander("⚙️ 고급 — 예측 파라미터"):
        st.caption("기본값 권장.")
        forecast_steps = st.slider("선행 예측 스텝 (5분 단위)", 6, 72, 12)
        ewma_k = st.slider("잔차 관리한계 σ 배수", 1.5, 5.0, 3.0, 0.5)

plot_df = df.tail(window_h * 12).copy()
series = plot_df.set_index("ts")[target_col].dropna()

# ── 잔차 기반 이상탐지 ────────────────────────────────────────────────
if len(series) < 12:
    st.warning("데이터가 12행 미만입니다. 더 많은 데이터 수집 후 재시도하세요.")
    st.stop()

res_df = residual_anomalies(series, ewma_span=12, k=ewma_k)

# ── 예측 (선행) ───────────────────────────────────────────────────────
future_forecast = forecast_next_n(series, n=forecast_steps)

col_label = {"current_load": "현재수요(MW)", "reserve_rate": "공급예비율(%)"}[target_col]

# ── 한눈에 보기 (쉬운 말 요약) ───────────────────────────────────────
n_anom = int(res_df["anomaly"].sum())
total = len(res_df)
metrics = None
if len(series) >= 60:
    _, metrics = evaluate_forecast(series, test_ratio=0.2)

_unit = "MW" if target_col == "current_load" else "%"
_msg_perf = (
    f"예측이 실제와 평균 **{metrics['MAE']:.0f}{_unit}** 어긋남"
    f"(실제의 약 {metrics['MAPE(%)']:.1f}%, hold-out 20%·데이터 누수 제거)."
    if metrics else
    f"예측 성능평가(MAE)는 60행 이상부터 활성(현재 {len(series)}행)."
)

st.subheader("🔎 한눈에 보기")
if n_anom == 0:
    st.success(
        f"최근 **{window_h}시간 {col_label}** — 잔차 기반 이상 **0건**(평소 주기 패턴 내). {_msg_perf}"
    )
else:
    st.warning(
        f"최근 **{window_h}시간 {col_label}** — 잔차 기반 이상 "
        f"**{n_anom}건**({n_anom/total*100:.1f}%) 감지. {_msg_perf}"
    )
st.caption(
    "주기성(요일·시간대)을 기준선으로 제거한 '잔차'에 관리한계를 적용 — "
    "주기성을 무시하는 단순 임계값의 거짓경보를 줄입니다."
)

# ── 예측 vs 실제 차트 ─────────────────────────────────────────────────
st.subheader("실측 vs 계절 기준선 예측")
fig1 = go.Figure()
fig1.add_trace(go.Scatter(
    x=res_df.index, y=res_df["value"],
    name="실측값", line=dict(color="#1f77b4", width=2),
))
fig1.add_trace(go.Scatter(
    x=res_df.index, y=res_df["baseline"],
    name="계절 기준선", line=dict(color="#aec7e8", dash="dash", width=1.5),
))
# 미래 예측
fig1.add_trace(go.Scatter(
    x=future_forecast.index, y=future_forecast.values,
    name=f"선행 예측 ({forecast_steps}스텝)",
    line=dict(color="#2ca02c", dash="dot", width=2),
))
# 이상 마킹
anom = res_df[res_df["anomaly"]]
if not anom.empty:
    fig1.add_trace(go.Scatter(
        x=anom.index, y=anom["value"],
        mode="markers", name="이상",
        marker=dict(color="red", size=9, symbol="x"),
    ))
fig1.update_layout(xaxis_title="시각", yaxis_title=col_label)
st.plotly_chart(style_fig(fig1, height=360), width="stretch")

# ── 잔차 차트 ─────────────────────────────────────────────────────────
st.subheader("잔차 (실측 − 기준선) + 관리한계")
fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=res_df.index, y=res_df["residual"],
    name="잔차", line=dict(color="#ff7f0e", width=1.5),
    fill="tozeroy", fillcolor="rgba(255,127,14,0.08)",
))
fig2.add_trace(go.Scatter(
    x=res_df.index, y=res_df["upper"],
    name="UCL", line=dict(color="rgba(255,0,0,0.5)", dash="dot"),
))
fig2.add_trace(go.Scatter(
    x=res_df.index, y=res_df["lower"],
    name="LCL", line=dict(color="rgba(255,0,0,0.5)", dash="dot"),
    fill="tonexty", fillcolor="rgba(255,0,0,0.04)",
))
if not anom.empty:
    fig2.add_trace(go.Scatter(
        x=anom.index, y=anom["residual"],
        mode="markers", name="이상",
        marker=dict(color="red", size=9, symbol="x"),
        showlegend=False,
    ))
fig2.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1)
fig2.update_layout(xaxis_title="시각", yaxis_title=f"잔차 ({col_label})")
st.plotly_chart(style_fig(fig2, height=280), width="stretch")

# ── 부하 패턴 히트맵 (시간대 × 요일) ─────────────────────────────────
if target_col == "current_load":
    st.subheader("🗓️ 부하 패턴 — 시간대 × 요일 히트맵")
    st.caption(
        "언제 전력을 가장 많이 쓰는지(피크)를 한눈에 — 색이 진할수록 평균 수요가 높습니다. "
        "이 주기 패턴이 위 '계절 기준선'의 근거입니다."
    )
    _hm = df[["ts", "current_load"]].dropna().copy()
    _hm["hour"] = _hm["ts"].dt.hour
    _dow = _hm["ts"].dt.dayofweek  # 0=월
    _dow_ko = ["월", "화", "수", "목", "금", "토", "일"]
    _hm["요일"] = _dow.map(dict(enumerate(_dow_ko)))
    pivot_hm = (
        _hm.pivot_table(index="요일", columns="hour", values="current_load", aggfunc="mean")
        .reindex(_dow_ko)
    )
    if pivot_hm.notna().sum().sum() >= 4:
        fig_hm = go.Figure(go.Heatmap(
            z=pivot_hm.values,
            x=[f"{h:02d}시" for h in pivot_hm.columns],
            y=pivot_hm.index,
            colorscale="YlOrRd",
            colorbar=dict(title="MW"),
            hovertemplate="%{y} %{x}<br>평균수요 %{z:,.0f} MW<extra></extra>",
        ))
        fig_hm.update_layout(xaxis_title="시간대", yaxis_title="요일")
        st.plotly_chart(style_fig(fig_hm, height=300), width="stretch")
    else:
        st.info("히트맵은 요일·시간대가 어느 정도 채워지면 표시됩니다(현재 데이터 누적 중).")

# ── 예측 성능 지표 ────────────────────────────────────────────────────
st.subheader("예측 성능 (Hold-out 20%)")
if metrics is not None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("MAE", f"{metrics['MAE']:.2f}")
    m2.metric("RMSE", f"{metrics['RMSE']:.2f}")
    m3.metric("MAPE", f"{metrics['MAPE(%)']:.2f}%")
    m4.metric("테스트 건수", f"{metrics['n_test']}행")
    st.caption("기준선을 train 구간만으로 적합해 test에 적용(데이터 누수 제거된 정직한 수치).")
else:
    st.info(f"현재 {len(series)}행 — 60행 이상 수집 후 예측 성능 평가가 활성화됩니다.")

# ── 이상 요약 ─────────────────────────────────────────────────────────
st.subheader("잔차 기반 이상 요약")
st.write(f"분석 기간 **{total}** 포인트 중 **{n_anom}** 건 이상 감지 ({n_anom/total*100:.1f}%)")

if n_anom > 0:
    st.dataframe(
        anom[["value", "baseline", "residual"]].rename(columns={
            "value": col_label,
            "baseline": "기준선",
            "residual": "잔차",
        }).style.format("{:.2f}"),
        width="stretch",
    )

render_footer()
