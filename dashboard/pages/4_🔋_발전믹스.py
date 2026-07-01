"""발전믹스 페이지 — 원자력·LNG·석탄·신재생 발전비율 시계열 + 파이차트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.storage import database  # noqa: E402

from dashboard._lib import (  # noqa: E402
    dash_header,
    inject_css,
    load_supply,
    render_footer,
    render_sidebar,
    style_fig,
)

st.set_page_config(page_title="발전믹스", page_icon="🔋", layout="wide")
inject_css()
dash_header(
    "🔋 발전믹스 — 무엇으로 전기를 만들고 있나",
    "원자력·LNG·석탄·신재생 등 어떤 발전원 조합으로 공급되는지 · 제조의 '설비 가동 포트폴리오'",
)

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
render_sidebar(load_supply())

if gen.empty:
    st.warning(
        "🔌 **발전믹스 데이터 대기 중** — 수집기는 정상 동작하나, 연료원별 발전량 API"
        "(`sumperfuel5m`)가 아직 `SERVICE ACCESS DENIED` 상태입니다.\n\n"
        "data.go.kr에서 **'한국전력거래소_계통 연료원별 발전량'**([15142651](https://www.data.go.kr/data/15142651)) "
        "활용신청이 승인되면, 코드 수정 없이 다음 수집 회차부터 자동으로 채워집니다. "
        "(수급 데이터는 정상 수집 중)"
    )
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
    fig_pie.update_layout(showlegend=False)
    st.plotly_chart(style_fig(fig_pie, height=350), width="stretch")
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
    fig_bar.update_layout(xaxis_title="MW")
    st.plotly_chart(style_fig(fig_bar, height=350), width="stretch")

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

fig_area.update_layout(xaxis_title="시각", yaxis_title="MW")
st.plotly_chart(style_fig(fig_area, height=380), width="stretch")

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
fig_pct.update_layout(xaxis_title="시각", yaxis_title="%")
st.plotly_chart(style_fig(fig_pct, height=300), width="stretch")

render_footer()
