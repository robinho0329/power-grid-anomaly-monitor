"""실시간 전력수급 모니터링 대시보드 (Streamlit) — Phase 1 골격."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.storage import database  # noqa: E402

st.set_page_config(page_title="전력수급 이상탐지 모니터", page_icon="⚡", layout="wide")
st.title("⚡ 실시간 전력수급 이상탐지 모니터링")
st.caption("한국 전력계통을 제조 생산라인에 빗댄 다층 이상탐지 (통계 · ML · 딥러닝)")


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()
if df.empty:
    st.info("아직 수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
else:
    latest = df.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric(config.METRICS["current_load"], f"{latest['current_load']:,.0f}")
    c2.metric(config.METRICS["reserve_rate"], f"{latest['reserve_rate']:.1f}%")
    c3.metric(config.METRICS["oper_reserve_rate"], f"{latest['oper_reserve_rate']:.1f}%")
    st.line_chart(df.set_index("ts")[["current_load", "forecast_load"]])
    st.line_chart(df.set_index("ts")[["reserve_rate", "oper_reserve_rate"]])
