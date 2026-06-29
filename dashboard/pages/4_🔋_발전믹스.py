"""발전믹스 페이지 — 원자력·LNG·석탄·신재생 발전비율 시계열 + 파이차트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.storage import database  # noqa: E402

st.set_page_config(page_title="발전믹스", page_icon="🔋", layout="wide")
st.title("🔋 발전믹스 (발전원별 발전량)")
st.caption("원자력·LNG·석탄·신재생·수력 등 발전원별 비중을 제조 설비 가동 포트폴리오처럼 시각화합니다.")

SOURCE_COLORS = {
    "원자력": "#4e79a7",
    "LNG": "#f28e2b",
    "석탄": "#59a14f",
    "신재생": "#76b7b2",
    "수력": "#edc948",
    "양수": "#b07aa1",
    "유류": "#ff9da7",
}


@st.cache_data(ttl=300)
def load_gen():
    return database.load_generation_df()


gen = load_gen()

if gen.empty:
    st.info("발전믹스 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

# ── 사이드바 ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("표시 범위")
    window_h = st.slider("표시 범위 (시간)", 6, 72, 24)

latest_ts = gen["ts"].max()
cutoff = gen["ts"].max() - __import__("pandas").Timedelta(hours=window_h)
plot_gen = gen[gen["ts"] >= cutoff]

# ── 최신 스냅샷 파이차트 ──────────────────────────────────────────────
snap = gen[gen["ts"] == latest_ts].set_index("source")["generation_mw"]
total = snap.sum()

col_pie, col_bar = st.columns([1, 2])

with col_pie:
    st.subheader(f"현재 발전믹스 ({latest_ts:%m-%d %H:%M})")
    fig_pie = px.pie(
        values=snap.values,
        names=snap.index,
        color=snap.index,
        color_discrete_map=SOURCE_COLORS,
        hole=0.4,
    )
    fig_pie.update_traces(textinfo="percent+label", textposition="outside")
    fig_pie.update_layout(
        showlegend=False, height=350, margin=dict(l=10, r=10, t=10, b=10)
    )
    st.plotly_chart(fig_pie, use_container_width=True)
    st.caption(f"총 발전량: {total:,.0f} MW")

with col_bar:
    st.subheader("발전원별 발전량 (현재)")
    snap_sorted = snap.sort_values(ascending=True)
    colors = [SOURCE_COLORS.get(s, "#cccccc") for s in snap_sorted.index]
    fig_bar = go.Figure(go.Bar(
        x=snap_sorted.values,
        y=snap_sorted.index,
        orientation="h",
        marker_color=colors,
        text=[f"{v:,.0f} MW" for v in snap_sorted.values],
        textposition="outside",
    ))
    fig_bar.update_layout(
        xaxis_title="MW", height=350,
        margin=dict(l=0, r=60, t=10, b=0),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── 시계열 스택 영역차트 ──────────────────────────────────────────────
st.subheader(f"발전믹스 추이 (최근 {window_h}시간)")

pivot = (
    plot_gen
    .pivot_table(index="ts", columns="source", values="generation_mw", aggfunc="sum")
    .fillna(0)
    .sort_index()
)

fig_area = go.Figure()
for src in pivot.columns:
    fig_area.add_trace(go.Scatter(
        x=pivot.index, y=pivot[src],
        name=src,
        stackgroup="one",
        line=dict(width=0.5),
        fillcolor=SOURCE_COLORS.get(src, "#cccccc"),
        mode="lines",
    ))

fig_area.update_layout(
    xaxis_title="시각", yaxis_title="MW",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=380, margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_area, use_container_width=True)

# ── 발전원별 비중 추이 (100% 스택) ────────────────────────────────────
st.subheader("발전원별 비중 추이 (%)")
pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

fig_pct = go.Figure()
for src in pct.columns:
    fig_pct.add_trace(go.Scatter(
        x=pct.index, y=pct[src],
        name=src,
        stackgroup="one",
        groupnorm="percent",
        mode="lines",
        fillcolor=SOURCE_COLORS.get(src, "#cccccc"),
        line=dict(width=0),
    ))
fig_pct.update_layout(
    xaxis_title="시각", yaxis_title="%",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=300, margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_pct, use_container_width=True)
