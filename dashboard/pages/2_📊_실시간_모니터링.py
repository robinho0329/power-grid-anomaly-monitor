"""실시간 전력수급 모니터링 — 부하 곡선·예비율 게이지·경보 상태."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.storage import database  # noqa: E402

from dashboard._lib import (  # noqa: E402
    dash_header,
    inject_css,
    render_alert_banner,
    render_footer,
    render_sidebar,
    reserve_gauge,
    style_fig,
)

st.set_page_config(page_title="실시간 모니터링", page_icon="📊", layout="wide")
inject_css()
dash_header(
    "📊 실시간 모니터링 — 지금 계통은 안전한가",
    "현재 수요·공급능력·예비율 추적 · 예비율은 제조의 '안전재고 여유율'과 같아 낮을수록 위험",
)


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()
render_sidebar(df)

if df.empty:
    st.info("수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

# ── 상단 경보 한 줄 요약 (공통 배너) ─────────────────────────────────
render_alert_banner(float(latest["reserve_rate"]))
st.caption(f"기준 시각: {latest['ts']}")

# ── 상단 KPI BAN 타일 + 게이지 ────────────────────────────────────────
g_col, t_col = st.columns([1, 1.4])

with g_col:
    st.caption("공급예비율 게이지 (제조 안전재고 여유율)")
    st.plotly_chart(reserve_gauge(float(latest["reserve_rate"])), width="stretch")

with t_col:
    r1 = st.columns(2)
    with r1[0]:
        kpi_tile(
            "현재 수요 (부하)", f"{latest['current_load']:,.0f}", unit="MW",
            delta=f"{latest['current_load'] - prev['current_load']:+,.0f} MW",
            delta_good=None, accent="#2E86DE",
        )
    with r1[1]:
        kpi_tile(
            "공급능력", f"{latest['supply_capacity']:,.0f}", unit="MW",
            delta=f"{latest['supply_capacity'] - prev['supply_capacity']:+,.0f} MW",
            delta_good=None, accent="#27AE60",
        )
    st.write("")
    r2 = st.columns(2)
    _d_res = latest["reserve_rate"] - prev["reserve_rate"]
    _d_ope = latest["oper_reserve_rate"] - prev["oper_reserve_rate"]
    with r2[0]:
        kpi_tile(
            "공급예비율", f"{latest['reserve_rate']:.1f}", unit="%",
            delta=f"{_d_res:+.1f} %p", delta_good=bool(_d_res >= 0),
            accent="#F39C12",
        )
    with r2[1]:
        kpi_tile(
            "운영예비율", f"{latest['oper_reserve_rate']:.1f}", unit="%",
            delta=f"{_d_ope:+.1f} %p", delta_good=bool(_d_ope >= 0),
            accent="#8E44AD",
        )

st.divider()

# ── 부하 곡선 ────────────────────────────────────────────────────────
st.subheader("부하 곡선 (당일)")
plot_df = df.set_index("ts").tail(288)  # 최근 24시간(5분×288)

fig_load = go.Figure()
fig_load.add_trace(go.Scatter(
    x=plot_df.index, y=plot_df["current_load"],
    name="현재수요", line=dict(color="#1f77b4", width=2),
))
fig_load.add_trace(go.Scatter(
    x=plot_df.index, y=plot_df["forecast_load"],
    name="최대예측수요", line=dict(color="#aec7e8", width=1.5, dash="dash"),
))
fig_load.add_trace(go.Scatter(
    x=plot_df.index, y=plot_df["supply_capacity"],
    name="공급능력", line=dict(color="#2ca02c", width=1.5, dash="dot"),
))
fig_load.update_layout(xaxis_title="시각", yaxis_title="MW")
st.plotly_chart(style_fig(fig_load, height=350), width="stretch")

# ── 예비율 추이 ──────────────────────────────────────────────────────
st.subheader("예비율 추이")
fig_res = go.Figure()
fig_res.add_trace(go.Scatter(
    x=plot_df.index, y=plot_df["reserve_rate"],
    name="공급예비율", line=dict(color="#ff7f0e", width=2),
    fill="tozeroy", fillcolor="rgba(255,127,14,0.08)",
))
fig_res.add_trace(go.Scatter(
    x=plot_df.index, y=plot_df["oper_reserve_rate"],
    name="운영예비율", line=dict(color="#d62728", width=1.5),
))
# 경보 임계선
for level, val in config.RESERVE_RATE_THRESHOLDS.items():
    if level in ("심각", "주의"):
        fig_res.add_hline(
            y=val, line_dash="dot",
            line_color="red" if level == "심각" else "orange",
            annotation_text=f"{level} {val}%",
            annotation_position="bottom right",
        )
fig_res.update_layout(xaxis_title="시각", yaxis_title="%")
st.plotly_chart(style_fig(fig_res, height=300), width="stretch")

st.caption(f"마지막 수집: {latest['ts']}")

render_footer()
