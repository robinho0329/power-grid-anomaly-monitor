"""실시간 전력수급 모니터링 — 부하 곡선·예비율 게이지·경보 상태."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.storage import database  # noqa: E402

st.set_page_config(page_title="실시간 모니터링", page_icon="📊", layout="wide")
st.title("📊 실시간 모니터링 — 지금 계통은 안전한가")
st.caption(
    "현재 수요·공급능력·예비율을 추적합니다. 예비율은 제조의 '안전재고 여유율'과 같아 "
    "낮을수록 위험 — 한눈에 경보 등급으로 보여줍니다."
)


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()

if df.empty:
    st.info("수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

# ── 상단 경보 한 줄 요약 ──────────────────────────────────────────────
_rate = float(latest["reserve_rate"])
_th = config.RESERVE_RATE_THRESHOLDS
if _rate < _th["심각"]:
    st.error(f"🔴 **심각** — 공급예비율 {_rate:.1f}%. 즉시 수급 대책이 필요한 수준입니다.")
elif _rate < _th["경계"]:
    st.warning(f"🟠 **경계** — 공급예비율 {_rate:.1f}%. 예비 자원 점검이 필요합니다.")
elif _rate < _th["주의"]:
    st.warning(f"🟡 **주의** — 공급예비율 {_rate:.1f}%. 평소보다 여유가 낮습니다.")
else:
    st.success(f"🟢 **정상** — 공급예비율 {_rate:.1f}%. 공급 여유가 충분합니다.")
st.caption(f"기준 시각: {latest['ts']}")

# ── 상단 KPI 카드 ─────────────────────────────────────────────────────
st.subheader("현재 상태")
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "현재 수요 (부하)",
    f"{latest['current_load']:,.0f} MW",
    delta=f"{latest['current_load'] - prev['current_load']:+.0f} MW",
)
c2.metric(
    "공급능력",
    f"{latest['supply_capacity']:,.0f} MW",
    delta=f"{latest['supply_capacity'] - prev['supply_capacity']:+.0f} MW",
)
c3.metric(
    "공급예비율",
    f"{latest['reserve_rate']:.1f} %",
    delta=f"{latest['reserve_rate'] - prev['reserve_rate']:+.1f} %",
)
c4.metric(
    "운영예비율",
    f"{latest['oper_reserve_rate']:.1f} %",
    delta=f"{latest['oper_reserve_rate'] - prev['oper_reserve_rate']:+.1f} %",
)

st.divider()

# ── 예비율 게이지 ────────────────────────────────────────────────────
st.subheader("공급예비율 게이지 (제조 안전재고 유사)")
g1, g2 = st.columns(2)

def make_gauge(value: float, title: str) -> go.Figure:
    thresholds = config.RESERVE_RATE_THRESHOLDS
    color = (
        "red" if value < thresholds["심각"]
        else "orange" if value < thresholds["경계"]
        else "gold" if value < thresholds["주의"]
        else "green"
    )
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        title={"text": title, "font": {"size": 14}},
        number={"suffix": "%", "font": {"size": 28}},
        delta={"reference": thresholds["주의"], "suffix": "%"},
        gauge={
            "axis": {"range": [0, 50], "ticksuffix": "%"},
            "bar": {"color": color},
            "steps": [
                {"range": [0, thresholds["심각"]], "color": "#ffcccc"},
                {"range": [thresholds["심각"], thresholds["경계"]], "color": "#ffe5cc"},
                {"range": [thresholds["경계"], thresholds["주의"]], "color": "#fff5cc"},
                {"range": [thresholds["주의"], 50], "color": "#e8f5e9"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": thresholds["심각"],
            },
        },
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
    return fig

with g1:
    st.plotly_chart(make_gauge(latest["reserve_rate"], "공급예비율"), width="stretch")
with g2:
    st.plotly_chart(make_gauge(latest["oper_reserve_rate"], "운영예비율"), width="stretch")

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
fig_load.update_layout(
    xaxis_title="시각", yaxis_title="MW",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=350, margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_load, width="stretch")

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
fig_res.update_layout(
    xaxis_title="시각", yaxis_title="%",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=300, margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_res, width="stretch")

# ── 경보 상태 ────────────────────────────────────────────────────────
st.subheader("경보 상태")
rate = latest["reserve_rate"]
thresholds = config.RESERVE_RATE_THRESHOLDS
if rate < thresholds["심각"]:
    st.error(f"🔴 **심각** — 공급예비율 {rate:.1f}% (기준: {thresholds['심각']}% 미만)")
elif rate < thresholds["경계"]:
    st.warning(f"🟠 **경계** — 공급예비율 {rate:.1f}% (기준: {thresholds['경계']}% 미만)")
elif rate < thresholds["주의"]:
    st.warning(f"🟡 **주의** — 공급예비율 {rate:.1f}% (기준: {thresholds['주의']}% 미만)")
else:
    st.success(f"🟢 **정상** — 공급예비율 {rate:.1f}% (여유 충분)")

st.caption(f"마지막 수집: {latest['ts']}")
