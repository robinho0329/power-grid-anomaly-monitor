"""전력수급 이상탐지 — 대시보드 홈.

청자 중심 '프로젝트 브리핑' 화면:
  1) 이 대시보드가 누구를 위해, 무엇을 답하는지
  2) 전력계통 ↔ 제조 생산라인 매핑(이 포트폴리오의 핵심 서사)
  3) 지금 계통 상태(쉬운 말 해석 + 경보 배너)
  4) 각 페이지를 '왜·언제' 보는지 안내
  5) 방법론(L1·L2·L3·잔차) 요약과 데이터 커버리지
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard._lib import (  # noqa: E402
    dash_header,
    inject_css,
    kpi_tile,
    load_supply,
    render_alert_banner,
    render_footer,
    render_sidebar,
    reserve_gauge,
)

st.set_page_config(
    page_title="전력수급 이상탐지 모니터",
    page_icon="⚡",
    layout="wide",
)
inject_css()

df = load_supply()
render_sidebar(df)

# ──────────────────────────────────────────────────────────────────────
# 헤더 밴드 — 한 줄 가치 제안
# ──────────────────────────────────────────────────────────────────────
dash_header(
    "⚡ 실시간 전력수급 이상탐지 모니터링",
    "한국 전력계통(KPX)을 제조 생산라인에 빗대어, 통계·머신러닝·딥러닝 3계층으로 "
    "평소와 다른 신호를 조기에 잡아내는 모니터링 시스템",
)

# ──────────────────────────────────────────────────────────────────────
# 누구를 위해 / 무엇을 답하나 / 핵심 차별점
# ──────────────────────────────────────────────────────────────────────
a, b, c = st.columns(3)
with a:
    with st.container(border=True):
        st.markdown("##### 👥 누구를 위한 화면인가")
        st.markdown(
            "- 전력 수급 **운영 관리자** — 현황 감시·경보\n"
            "- 제조 AI·예지보전 **기술 리뷰어** — 방법론 평가"
        )
with b:
    with st.container(border=True):
        st.markdown("##### ❓ 무엇을 답하나")
        st.markdown(
            "- 지금 계통은 **안전한가?**\n"
            "- 평소 패턴과 **다른 이상**이 있는가?\n"
            "- 단순 임계값이 **놓치는** 신호는?"
        )
with c:
    with st.container(border=True):
        st.markdown("##### 🎯 핵심 차별점")
        st.markdown(
            "- 주기성을 고려한 **잔차 기반** 탐지\n"
            "- 통계→ML→딥러닝 **다층 교차검증**\n"
            "- **도메인 전이** 가능한 설계"
        )

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 지금 계통 상태 — 쉬운 말 해석 + 경보 배너
# ──────────────────────────────────────────────────────────────────────
st.subheader("📍 지금 계통 상태")

if df.empty:
    st.info(
        "아직 수집된 데이터가 없습니다. 로컬에서는 `python -m scripts.collect_once` 로 수집을 시작하세요. "
        "(배포본에는 데모용 시드 데이터가 포함됩니다.)"
    )
else:
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    rate = float(latest["reserve_rate"])
    load_delta = latest["current_load"] - prev["current_load"]
    rate_delta = rate - float(prev["reserve_rate"])

    # 경보 등급 판정·배너 (공용 _lib — app/페이지 단일 진실원천)
    render_alert_banner(rate)

    # 게이지(예비율) + BAN 타일 — Tableau식 상단 요약
    g_col, t_col = st.columns([1, 2], gap="medium")
    with g_col:
        st.plotly_chart(reserve_gauge(rate), width="stretch")
        st.caption("공급예비율 = 제조의 '안전재고 여유율' — 낮을수록 위험")
    with t_col:
        r1 = st.columns(2)
        with r1[0]:
            kpi_tile(
                "현재 수요 (부하)", f"{latest['current_load']:,.0f}", unit="MW",
                delta=f"{load_delta:+,.0f} MW",
                delta_good=None,
                accent="#2E86DE", sub="생산라인 처리량 = 지금 계통이 감당 중인 전력",
            )
        with r1[1]:
            kpi_tile(
                "공급능력", f"{latest['supply_capacity']:,.0f}", unit="MW",
                accent="#16A085", sub="라인 최대 캐파 = 동원 가능한 총 공급량",
            )
        r2 = st.columns(2)
        with r2[0]:
            kpi_tile(
                "공급예비율", f"{rate:.1f}", unit="%",
                delta=f"{rate_delta:+.1f} %p", delta_good=(rate_delta >= 0),
                accent="#F39C12", sub="안전재고 여유율 — 경보 판정 기준",
            )
        with r2[1]:
            kpi_tile(
                "운영예비율", f"{float(latest['oper_reserve_rate']):.1f}", unit="%",
                accent="#8E44AD", sub="즉시 투입 가능한 실질 여유 마진",
            )
    st.caption(
        f"기준 시각: {pd.to_datetime(latest['ts']):%Y-%m-%d %H:%M} · "
        "자세한 추이는 좌측 **📊 실시간 모니터링** 페이지"
    )

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 핵심 서사 — 전력계통 ↔ 제조 생산라인 매핑
# ──────────────────────────────────────────────────────────────────────
st.subheader("🏭 왜 '제조 생산라인'에 빗댔나")
st.markdown(
    "전력계통의 수급 감시는 제조 현장의 **예지보전(이상감지)** 과 구조가 같습니다. "
    "이 매핑 덕분에, 여기서 검증한 다층 이상탐지 방법론은 제조 센서 데이터로 **그대로 전이**됩니다."
)
mapping = pd.DataFrame(
    {
        "전력계통 (이 프로젝트)": [
            "현재수요(부하, MW)",
            "공급능력(MW)",
            "공급예비율(%)",
            "예비율 경보 단계(관심·주의·경계·심각)",
            "5분 단위 수급 스냅샷",
            "다층 이상탐지(L1·L2·L3)",
        ],
        "제조 생산라인 (전이 대상)": [
            "생산라인 처리량(throughput)",
            "라인 최대 캐파(capacity)",
            "안전재고 여유율(buffer)",
            "설비 경보 등급(alarm tier)",
            "센서 스트림(sensor stream)",
            "예지보전 이상감지(PdM)",
        ],
    }
)
st.table(mapping)

# ──────────────────────────────────────────────────────────────────────
# 이 대시보드 읽는 법 — 페이지 가이드
# ──────────────────────────────────────────────────────────────────────
st.subheader("🧭 이 대시보드 읽는 법")
st.markdown("왼쪽 사이드바에서 페이지를 이동하세요. 각 페이지는 서로 다른 질문에 답합니다.")
g1, g2 = st.columns(2)
with g1:
    st.markdown(
        "**🗺️ 발전소 지도** · *전력이 어디서 만들어지나*\n"
        "전국 발전소 위치·설비용량·발전원을 지도 맥락으로.\n\n"
        "**📊 실시간 모니터링** · *지금 안전한가*\n"
        "부하 곡선·예비율 게이지·경보 상태를 한눈에.\n\n"
        "**🚨 이상탐지 타임라인** · *언제 이상이 있었나*\n"
        "L1·L2·L3 결과를 같은 시간축에 중첩 비교."
    )
with g2:
    st.markdown(
        "**🔋 발전믹스** · *무엇으로 만들고 있나*\n"
        "원자력·LNG·석탄·신재생 비중과 추이.\n\n"
        "**📈 탐지 비교** · *왜 다층 탐지인가*\n"
        "단순 임계값과의 차이를 합성 시나리오로 비교(정답 라벨 기반).\n\n"
        "**🔮 수요 예측** · *앞으로 어떻게 되나*\n"
        "주기성 제거 후 잔차 기반 예측·이상탐지."
    )

# ──────────────────────────────────────────────────────────────────────
# 방법론 & 데이터 커버리지
# ──────────────────────────────────────────────────────────────────────
with st.expander("🔬 방법론 요약 — 3계층 + 잔차 이상탐지"):
    st.markdown(
        "- **L1 통계 (EWMA · CUSUM)** — 관리도 기반. 가볍고 즉시 동작, 급변·누적 변화에 강함.\n"
        "- **L2 머신러닝 (Isolation Forest)** — 다변량 조합 이상 포착. 라벨 불필요.\n"
        "- **L3 딥러닝 (LSTM-AutoEncoder)** — 재구성 오차로 '패턴 붕괴형' 이상 탐지(데이터 충분 시 활성).\n"
        "- **잔차 기반 (수요예측)** — 일·주 주기성을 기준선으로 제거 → 주기성을 무시하는 단순 임계값의 거짓경보를 크게 감소.\n\n"
        "여러 계층이 **서로 다른 종류의 이상**을 교차 검증하는 것이 핵심입니다."
    )

cov1, cov2, cov3 = st.columns(3)
if df.empty:
    cov1.metric("누적 데이터", "0 건")
    cov2.metric("커버리지", "—")
    cov3.metric("상태", "수집 대기")
else:
    ts = pd.to_datetime(df["ts"])
    dur_h = (ts.max() - ts.min()).total_seconds() / 3600
    cov1.metric("누적 데이터", f"{len(df):,} 건")
    cov2.metric("시간 커버리지", f"{dur_h:.1f} 시간")
    cov3.metric("최신 수집", f"{ts.max():%m-%d %H:%M}")

    # L3 딥러닝 준비도 — 솔직한 비활성 표현(억지 렌더 대신 진행바)
    _l3_target = 60
    st.caption(f"🧠 L3 딥러닝(LSTM-AE) 준비도 — {len(df):,}/{_l3_target}행")
    st.progress(min(len(df) / _l3_target, 1.0))
    if len(df) < _l3_target:
        st.caption("설계 완비, 데이터 충족 시 자동 활성(소량 데이터 억지 추론 안 함).")

st.caption(
    "데이터: 한국전력거래소(KPX) OpenAPI · 5분 단위 수급/발전믹스. "
    "이상탐지는 전국 단위 시계열에서 수행됩니다(공간 이상탐지 아님)."
)

render_footer()
