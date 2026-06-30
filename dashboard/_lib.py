"""대시보드 공통 헬퍼.

여러 페이지가 재사용하는 데이터 로드·캐싱·경보 판정·사이드바·푸터·인사이트 유틸.
(자매 프로젝트 chungbuk-air-quality-monitor의 _lib 패턴을 전력 도메인에 맞게 이식)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# streamlit은 실행 파일 디렉토리만 sys.path에 추가하므로 프로젝트 루트를 명시 추가
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.storage import database  # noqa: E402

# ----------------------------------------------------------------------
# 상수 — 시간대 / 링크 / 색상
# ----------------------------------------------------------------------
KST = timezone(timedelta(hours=9))
GITHUB_URL = "https://github.com/robinho0329/power-grid-anomaly-monitor"

# 로컬 수집 스케줄러 주기(분) — scripts/local_collect.ps1 / 작업스케줄러 PowerGridCollect
_COLLECT_INTERVAL_MIN = 10

# 경보 등급별 색상 (예비율이 낮을수록 위험)
ALERT_COLORS: dict[str, str] = {
    "정상": "#2ca02c",   # 초록
    "주의": "#f4c20d",   # 노랑
    "경계": "#ff7f0e",   # 주황
    "심각": "#d62728",   # 빨강
}
ALERT_ICONS: dict[str, str] = {"정상": "🟢", "주의": "🟡", "경계": "🟠", "심각": "🔴"}


# ----------------------------------------------------------------------
# 시간 포맷
# ----------------------------------------------------------------------
def now_kst() -> datetime:
    """현재 KST 시각."""
    return datetime.now(tz=KST)


def fmt_kst(dt: datetime | pd.Timestamp | None, with_tz: bool = True) -> str:
    """datetime을 KST 문자열로 변환 (tzinfo 없으면 KST 라벨만 부착)."""
    if dt is None or (isinstance(dt, float) and pd.isna(dt)):
        return "—"
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    s = dt.strftime("%Y-%m-%d %H:%M")
    return f"{s} KST" if with_tz else s


def next_collect_eta_kst() -> str:
    """다음 로컬 수집 예정 시각 (KST). 10분 간격 슬롯의 다음 발생."""
    now = now_kst()
    minute_slot = ((now.minute // _COLLECT_INTERVAL_MIN) + 1) * _COLLECT_INTERVAL_MIN
    eta = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_slot)
    return eta.strftime("%H:%M KST")


# ----------------------------------------------------------------------
# 데이터 로드 (캐시)
# ----------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_supply() -> pd.DataFrame:
    """수급(power_supply) 전체를 DataFrame으로 로드 (5분 캐시).

    배포본 시드/빈 DB로 테이블이 없을 수도 있으므로 graceful 하게 빈 DF 반환.
    """
    try:
        return database.load_df()
    except Exception:  # noqa: BLE001 — 테이블 부재 등 배포 환경 방어
        return pd.DataFrame()


# ----------------------------------------------------------------------
# 경보 등급 판정 — 예비율(%) 기준 (app/페이지 공통 단일 진실원천)
# ----------------------------------------------------------------------
def reserve_alert(rate: float) -> dict:
    """공급예비율 → 경보 등급. 색·아이콘·메시지·streamlit 배너 종류를 함께 반환."""
    th = config.RESERVE_RATE_THRESHOLDS
    if rate < th["심각"]:
        level, kind, msg = "심각", "error", "공급 여유가 매우 부족합니다. 즉시 수급 대책이 필요한 수준입니다."
    elif rate < th["경계"]:
        level, kind, msg = "경계", "warning", "공급 여유가 빠르게 줄고 있습니다. 예비 자원 점검이 필요합니다."
    elif rate < th["주의"]:
        level, kind, msg = "주의", "warning", "여유가 평소보다 낮습니다. 추이를 주의 깊게 지켜볼 구간입니다."
    else:
        level, kind, msg = "정상", "success", "공급 여유가 충분합니다. 계통은 안정적으로 운영되고 있습니다."
    return {
        "level": level,
        "kind": kind,
        "icon": ALERT_ICONS[level],
        "color": ALERT_COLORS[level],
        "msg": msg,
    }


def render_alert_banner(rate: float) -> dict:
    """경보 배너를 그리고 판정 결과 dict를 반환."""
    a = reserve_alert(rate)
    banner = getattr(st, a["kind"])
    banner(f"{a['icon']} **{a['level']}** — 공급예비율 {rate:.1f}%. {a['msg']}")
    return a


# ----------------------------------------------------------------------
# 공통 컴포넌트 — 헤더 / 인사이트 / 데이터 현황 / 사이드바 / 푸터
# ----------------------------------------------------------------------
def page_header(emoji: str, title: str, description: str = "") -> None:
    """페이지 상단 헤더 일관 적용."""
    st.title(f"{emoji} {title}")
    if description:
        st.caption(description)


def render_insight(body: str) -> None:
    """데이터 분석 결과를 평문으로 전달하는 인사이트 콜아웃 (마크다운 별표 노출 방지)."""
    st.info(f"💡 {body}")


def render_data_status(df: pd.DataFrame, *, l3_target: int = 60) -> None:
    """페이지 상단 누적 데이터 현황 KPI + L3 준비도."""
    if df.empty:
        st.warning(
            "⚡ 누적 데이터가 없습니다. 로컬 수집(`python -m scripts.collect_once`) 후 표시됩니다. "
            "(배포본에는 데모용 시드 데이터가 포함됩니다.)"
        )
        return
    ts = pd.to_datetime(df["ts"])
    dur_h = (ts.max() - ts.min()).total_seconds() / 3600
    c = st.columns(4)
    c[0].metric("누적 데이터", f"{len(df):,} 건")
    c[1].metric("시간 커버리지", f"{dur_h:.1f} 시간")
    c[2].metric("최신 수집", fmt_kst(ts.max(), with_tz=False), help="KST 기준")
    c[3].metric(
        "L3 딥러닝 준비",
        f"{int(min(len(df) / l3_target, 1.0) * 100)}%",
        help=f"LSTM-AE 활성 기준 {len(df)}/{l3_target}행",
    )


def render_sidebar(df: pd.DataFrame | None = None) -> None:
    """모든 페이지가 공유하는 사이드바 — 수집 상태·링크."""
    with st.sidebar:
        st.markdown("### ⚡ 전력수급 이상탐지")
        st.caption("KPX 실시간 수급 · 다층 이상탐지")
        st.divider()

        if df is not None and not df.empty:
            last_ts = pd.to_datetime(df["ts"]).max()
            st.markdown("**📡 자동 수집 상태**")
            st.write(f"마지막 수집: `{fmt_kst(last_ts)}`")
            st.write(f"누적: `{len(df):,}건`")
            st.write(f"다음 수집(로컬): `{next_collect_eta_kst()}`")
            st.divider()

        st.markdown("**🔗 링크**")
        st.markdown(f"[📂 GitHub 레포]({GITHUB_URL})")
        st.markdown(f"[🤖 Actions]({GITHUB_URL}/actions)")
        st.divider()
        st.caption(
            "수집: 로컬 PC가 10분마다 자동 수집·푸시(KPX는 한국 IP 전용).\n"
            "분석·리포트: 클라우드가 자동 갱신."
        )


def render_footer() -> None:
    """모든 페이지 하단 공통 푸터 — 포트폴리오 프레이밍."""
    st.divider()
    st.caption(
        f"⚙️ 로컬 10분 자동 수집(다음 {next_collect_eta_kst()}) · 클라우드 자동 분석 · "
        f"[코드]({GITHUB_URL}) · "
        "제조 AI/예지보전 직무 포트폴리오 (다층 이상탐지 L1·L2·L3 + 잔차)"
    )


# ======================================================================
# BI/Tableau 스타일 — 커스텀 CSS · KPI BAN 타일 · 게이지 · 차트 테마
# (Tableau Public 에너지 대시보드 관례: BAN 타일, 게이지, 정돈된 차트, 강한 액센트)
# ======================================================================
# 데이터 잉크 위주의 차트 팔레트 (범주형 — 발전원/지표)
CHART_COLORS = [
    "#2E86DE", "#F39C12", "#27AE60", "#8E44AD",
    "#E74C3C", "#16A085", "#D35400", "#2C3E50",
]
INK = "#1c2733"       # 본문 텍스트
MUTED = "#7b8a9a"     # 보조 텍스트
GRID = "rgba(120,140,160,0.18)"  # 옅은 그리드


def inject_css() -> None:
    """기본 Streamlit 크롬을 숨기고 BI 대시보드 톤을 입히는 전역 CSS.

    각 페이지 상단에서 1회 호출. (set_page_config 직후 권장)
    """
    st.markdown(
        """
        <style>
        /* 기본 크롬 제거 — '앱' 느낌 */
        #MainMenu, footer, header [data-testid="stToolbar"] {visibility: hidden;}
        [data-testid="stDecoration"] {display:none;}
        /* 상단 여백 축소 (대시보드 밀도↑) */
        .block-container {padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1400px;}
        /* 헤더 밴드 */
        .dash-header {
            background: linear-gradient(110deg, #142233 0%, #1f3b54 60%, #2a5168 100%);
            color: #fff; padding: 18px 24px; border-radius: 12px; margin-bottom: 18px;
            box-shadow: 0 4px 18px rgba(20,34,51,0.18);
        }
        .dash-header h1 {color:#fff; font-size: 1.5rem; margin:0; font-weight:800;}
        .dash-header p {color: #cfe0ee; margin: 6px 0 0; font-size: 0.9rem;}
        /* KPI BAN 타일 */
        .kpi-card {
            background:#fff; border-radius:12px; padding:16px 18px;
            border:1px solid #e6ebf0; border-top:4px solid var(--accent,#F39C12);
            box-shadow:0 2px 10px rgba(28,39,51,0.06); height:100%;
        }
        .kpi-label {font-size:0.82rem; color:#7b8a9a; font-weight:600; margin:0;}
        .kpi-value {font-size:1.9rem; font-weight:800; color:#1c2733; line-height:1.15; margin:2px 0 0;}
        .kpi-unit  {font-size:0.95rem; font-weight:600; color:#7b8a9a;}
        .kpi-delta {font-size:0.82rem; font-weight:700; margin-top:4px;}
        .kpi-sub   {font-size:0.72rem; color:#9aa7b4; margin-top:6px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def dash_header(title: str, subtitle: str = "") -> None:
    """Tableau식 헤더 밴드 (그라데이션 배너)."""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="dash-header"><h1>{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def kpi_tile(
    label: str,
    value: str,
    *,
    unit: str = "",
    delta: str | None = None,
    delta_good: bool | None = None,
    accent: str = "#F39C12",
    sub: str = "",
) -> None:
    """BAN(Big Aggregate Number) 타일 — 큰 숫자 + 라벨 + 증감 + 보조설명.

    delta_good: True=초록, False=빨강, None=회색.
    """
    if delta is None:
        delta_html = ""
    else:
        color = {True: "#27AE60", False: "#E74C3C", None: "#7b8a9a"}[delta_good]
        delta_html = f'<div class="kpi-delta" style="color:{color}">{delta}</div>'
    unit_html = f'<span class="kpi-unit"> {unit}</span>' if unit else ""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    st.markdown(
        f"""
        <div class="kpi-card" style="--accent:{accent}">
            <p class="kpi-label">{label}</p>
            <div class="kpi-value">{value}{unit_html}</div>
            {delta_html}{sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_fig(fig: go.Figure, *, height: int | None = None) -> go.Figure:
    """plotly figure에 BI 공통 테마 적용 (투명 배경·정돈된 그리드·일관 폰트)."""
    fig.update_layout(
        template="plotly_white",
        font=dict(family="sans-serif", size=12, color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=30, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        colorway=CHART_COLORS,
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    if height:
        fig.update_layout(height=height)
    return fig


def reserve_gauge(rate: float, *, height: int = 260) -> go.Figure:
    """공급예비율 게이지 (관제실 스타일). 임계 구간을 색 띠로 표시."""
    th = config.RESERVE_RATE_THRESHOLDS
    a = reserve_alert(rate)
    axis_max = max(25.0, rate * 1.2)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=rate,
            number={"suffix": " %", "font": {"size": 30, "color": INK}},
            gauge={
                "axis": {"range": [0, axis_max], "tickwidth": 1, "tickcolor": MUTED},
                "bar": {"color": a["color"], "thickness": 0.28},
                "borderwidth": 0,
                "steps": [
                    {"range": [0, th["심각"]], "color": "rgba(231,76,60,0.25)"},
                    {"range": [th["심각"], th["경계"]], "color": "rgba(211,84,0,0.20)"},
                    {"range": [th["경계"], th["주의"]], "color": "rgba(243,201,13,0.22)"},
                    {"range": [th["주의"], axis_max], "color": "rgba(39,174,96,0.18)"},
                ],
                "threshold": {
                    "line": {"color": a["color"], "width": 4},
                    "thickness": 0.85,
                    "value": rate,
                },
            },
        )
    )
    fig.update_layout(
        height=height,
        margin=dict(l=16, r=16, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color=INK),
    )
    return fig
