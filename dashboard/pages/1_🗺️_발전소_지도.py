"""발전소 분포 지도 + 실시간 발전믹스 (GIS 맥락 레이어).

지도는 발전소 '위치'(정적)를 보여주는 탐색·맥락 레이어이며,
이상탐지는 전국 시계열에서 별도로 수행된다(공간 이상탐지 아님).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from src.geo.plants import SOURCE_COLORS, load_plants  # noqa: E402
from src.storage import database  # noqa: E402

st.set_page_config(page_title="발전소 지도", page_icon="🗺️", layout="wide")
st.title("🗺️ 발전소 분포 + 실시간 발전믹스")
st.caption(
    "점 = 발전소 위치(시드·근사 좌표), 크기 = 설비용량, 색 = 발전원. "
    "지도는 맥락용이며 이상탐지는 전국 시계열에서 수행됩니다."
)

plants = load_plants()

col_map, col_mix = st.columns([3, 1])

with col_map:
    fig = px.scatter_map(
        plants,
        lat="lat",
        lon="lon",
        size="capacity_mw",
        color="source",
        color_discrete_map=SOURCE_COLORS,
        hover_name="name",
        hover_data={"capacity_mw": True, "lat": False, "lon": False},
        size_max=30,
        zoom=5.5,
        center={"lat": 36.3, "lon": 127.8},
        height=620,
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width="stretch")

with col_mix:
    st.subheader("실시간 발전믹스")
    gen = database.load_generation_df()
    if gen.empty:
        st.info("발전믹스 데이터 없음.\n수집 후 표시됩니다.")
        # 시드 기준 설비용량 비중으로 대체 표시
        cap = plants.groupby("source")["capacity_mw"].sum().sort_values(ascending=False)
        st.caption("· 설비용량 비중(시드)")
        st.bar_chart(cap)
    else:
        latest_ts = gen["ts"].max()
        snap = gen[gen["ts"] == latest_ts].set_index("source")["generation_mw"]
        st.caption(f"· 기준 {latest_ts:%m-%d %H:%M}")
        st.bar_chart(snap.sort_values(ascending=False))
