"""탐지 비교 페이지 — 단순 임계값 vs 다층(L1·L2) 탐지를 합성 시나리오로 정직 비교.

합성 이벤트는 '정답 위치'를 알기 때문에, 거짓경보/정탐을 정직하게 정량화할 수 있다.
실측 데이터는 정답 라벨이 없어 탐색용으로만 표시한다(성과 주장 금지).
"""
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
st.title("📈 단순 임계값 vs 다층 탐지 비교")
st.caption(
    "단순 ±3σ 임계값과 다층 탐지(L1 통계·L2 ML)를 같은 시계열에 적용해 반응을 비교합니다. "
    "정직한 정량 비교는 정답을 아는 **합성 시나리오**에서 수행합니다(실측은 라벨이 없어 탐색용)."
)


@st.cache_data(ttl=300)
def load():
    return database.load_df()


df = load()

if df.empty:
    st.info("수집된 데이터가 없습니다. `python -m scripts.collect_once` 로 수집을 시작하세요.")
    st.stop()

# ── 사이드바 (기본 컨트롤) ────────────────────────────────────────────
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
    with st.expander("⚙️ 고급 — 탐지 파라미터"):
        st.caption("기본값 권장. 값이 작을수록 더 민감하게 잡습니다.")
        ewma_k = st.slider("EWMA 관리한계 σ 배수", 1.5, 5.0, 3.0, 0.5)
        cusum_thresh = st.slider("CUSUM 임계", 1.0, 20.0, 5.0, 0.5)

# ── 데모 시나리오 프리셋 (메인 상단, 기본=없음) ──────────────────────
st.markdown(
    "**데모 시나리오** — 합성 이상을 주입해 탐지기 반응을 비교합니다. "
    "주입 위치를 알기에 거짓경보·정탐을 정직하게 셀 수 있습니다."
)
scenario = st.radio(
    "데모 시나리오",
    ["없음 (실측)", "스파이크 (급등)", "드리프트 (점진 변화)", "레벨 이동"],
    horizontal=True,
    label_visibility="collapsed",
)
is_demo = scenario != "없음 (실측)"
if is_demo:
    st.warning(
        f"🧪 **데모 데이터** — '{scenario}' 합성 이벤트가 주입되었습니다. "
        "아래 수치는 **합성 시나리오 기준**이며 실제 운영 탐지 성과가 아닙니다."
    )

plot_df = df.tail(window_h * 12).copy().reset_index(drop=True)
series = plot_df.set_index("ts")[target_col].dropna().copy()

# ── 합성 이벤트 주입 + 정답(truth) 마스크 구성 ───────────────────────
truth_mask = pd.Series(False, index=series.index)
if is_demo and len(series) > 20:
    half = len(series) // 2
    if scenario.startswith("스파이크"):
        idx = series.index[half]
        series[idx] = series.mean() + series.std() * 5
        truth_mask.loc[idx] = True
    elif scenario.startswith("드리프트"):
        vals = series.values.copy()
        vals[half:] += np.linspace(0, series.std() * 3, len(series) - half)
        series = pd.Series(vals, index=series.index)
        truth_mask.iloc[half:] = True
    elif scenario.startswith("레벨"):
        vals = series.values.copy()
        vals[half:] -= series.std() * 4
        series = pd.Series(vals, index=series.index)
        truth_mask.iloc[half:] = True
elif is_demo:
    st.info("합성 주입에는 최소 21개 시점이 필요합니다. 분석 범위를 늘려주세요.")

# ── 각 탐지기 실행 ────────────────────────────────────────────────────
ewma_df = ewma_cusum.ewma_anomalies(series, span=12, k=ewma_k)
cusum_s = ewma_cusum.cusum_change_points(series, threshold=cusum_thresh)

# 단순 임계값 탐지 (비교 기준선) — 주기성 무시
mean_val = series.mean()
std_val = series.std()
simple_thresh = (series < mean_val - 3 * std_val) | (series > mean_val + 3 * std_val)

# L2 IF
l2_df = isolation_forest.detect(
    plot_df.set_index("ts").loc[series.index].reset_index(),
    contamination="auto",  # 정상 구간엔 강제 라벨 없이 정직하게
)
l2_series = l2_df.set_index("ts")["anomaly"].reindex(series.index).fillna(False)

# ── 정직한 정량 요약 (합성 시나리오 한정) ────────────────────────────
if is_demo and truth_mask.any():
    ewma_mask = ewma_df["anomaly"].reindex(series.index).fillna(False)
    multi_mask = ewma_mask | cusum_s.reindex(series.index).fillna(False) | l2_series

    def _fp(mask: pd.Series) -> int:
        return int((mask & ~truth_mask).sum())

    def _tp(mask: pd.Series) -> bool:
        return bool((mask & truth_mask).any())

    s_fp, s_tp = _fp(simple_thresh), _tp(simple_thresh)
    m_fp, m_tp = _fp(multi_mask), _tp(multi_mask)
    st.success(
        f"**{scenario.split()[0]} 주입 비교** — "
        f"단순 ±3σ: 정탐 {'✅' if s_tp else '❌'} · 거짓경보 **{s_fp}건**  /  "
        f"다층(EWMA∪CUSUM∪IF): 정탐 {'✅' if m_tp else '❌'} · 거짓경보 **{m_fp}건**. "
        "_*합성 시나리오 기준 — 운영 성과 아님._"
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
# 정답(주입) 구간 음영 표시
if is_demo and truth_mask.any():
    truth_idx = series.index[truth_mask.values]
    fig.add_vrect(
        x0=truth_idx.min(), x1=truth_idx.max(),
        fillcolor="rgba(214,39,40,0.08)", line_width=0,
        annotation_text="주입 구간(정답)", annotation_position="top left",
        row=1, col=1,
    )
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

fig.add_trace(go.Bar(x=l2_series.index, y=l2_series.astype(int),
                      name="IF", marker_color=["#2ca02c" if v else "#aec7e8"
                                               for v in l2_series.values],
                      showlegend=False), row=4, col=1)

fig.update_layout(height=700, margin=dict(l=0, r=0, t=30, b=0),
                   legend=dict(orientation="h", y=-0.04))
st.plotly_chart(fig, width="stretch")

# ── 탐지기 성능 비교 표 ───────────────────────────────────────────────
_table_title = (
    f"탐지기 비교 — 🧪 데모 시나리오({scenario.split()[0]})"
    if is_demo else "탐지기 비교 — 실측 데이터(탐색용)"
)
st.subheader(_table_title)
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
        first_detection_lag(l2_series),
    ],
    "특징": [
        "기준선 — 주기성 무시, 거짓경보 多",
        "점진 변화·레벨이동에 민감",
        "누적합 기반 — 스파이크 후 반응 지속",
        "다변량 — 조합 이상 포착",
    ],
})
st.dataframe(comparison, width="stretch", hide_index=True)
st.caption(
    "출처: "
    + ("🧪 합성 데모 시나리오(정답 라벨 보유)" if is_demo
       else "실측 시드 데이터 — 정답 라벨 없음, 탐색용")
    + f" · 분석 {n:,}개 시점"
)

# ── L3 딥러닝 상태 (진행바) ──────────────────────────────────────────
L3_MIN_ROWS = 60
st.subheader("🧠 L3 딥러닝(LSTM-AE) 준비도")
st.progress(min(len(df) / L3_MIN_ROWS, 1.0))
if len(df) >= L3_MIN_ROWS:
    st.caption(
        f"현재 {len(df):,}/{L3_MIN_ROWS}행 — 활성 가능. "
        "이상탐지 타임라인 페이지에서 L3 결과를 확인하세요."
    )
else:
    st.caption(
        f"현재 {len(df):,}/{L3_MIN_ROWS}행 — 설계 완비, 데이터 충족 시 자동 활성. "
        "소량 데이터로 억지 추론하지 않습니다(과적합 노이즈 방지)."
    )
