"""매일 자율 개발 루프 — 회귀 테스트·누적 통계·탐지 요약·마일스톤 리포트.

GitHub Actions가 매일 한 번 호출. Claude API 호출 없이 다음을 수행:
  1. pytest 회귀 테스트
  2. 누적 데이터 통계 (총량·시간범위·수집 성공률)
  3. 분석 플로우 실행 → 다층 이상탐지 요약
  4. 데이터 마일스톤 진행률 (L3 활성화·예측평가 등 게이트)
  5. 결과를 reports/daily/YYYY-MM-DD.md 로 저장

실행:
    .venv/Scripts/python.exe scripts/daily_dev_loop.py
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402

from flows.analysis_flow import L3_MIN_ROWS, detection_summary, run_analysis  # noqa: E402
from src.storage import database  # noqa: E402

KST = timezone(timedelta(hours=9))
REPORTS_DIR = _PROJECT_ROOT / "reports" / "daily"

# 데이터 마일스톤 (게이트)
MILESTONES = [
    ("L3_LSTM_ACTIVATION", L3_MIN_ROWS, "LSTM-AE 딥러닝 탐지 활성화"),
    ("FORECAST_EVAL", 60, "수요예측 성능평가(MAE/RMSE) 활성화"),
    ("ONE_DAY", 288, "1일치(288건) 일주기 분석"),
    ("ONE_WEEK", 288 * 7, "1주치 주간주기 분석"),
]


def run_pytest() -> Tuple[bool, str]:
    """pytest 실행. (성공여부, 마지막 라인)."""
    py = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    py = py if py.exists() else Path(sys.executable)
    try:
        result = subprocess.run(
            [str(py), "-m", "pytest", "-q", "--no-header"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=600,
        )
        last = (result.stdout.strip().splitlines() or ["(no output)"])[-1]
        return result.returncode == 0, last
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, f"pytest 실행 실패: {exc}"


def accumulation_stats(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"total": 0}
    ts = pd.to_datetime(df["ts"])
    return {
        "total": len(df),
        "first": ts.min(),
        "last": ts.max(),
        "unique_times": ts.nunique(),
        "duration_h": (ts.max() - ts.min()).total_seconds() / 3600,
    }


def health_recent(df: pd.DataFrame, hours: int = 24) -> Dict[str, Any]:
    """최근 N시간 수집 성공률 (5분 간격 기준 기대치 대비)."""
    expected = hours * 12  # 5분×12 = 1시간
    if df.empty:
        return {"received": 0, "expected": expected, "rate": 0.0}
    ts = pd.to_datetime(df["ts"])
    now = ts.max()
    received = int((ts >= now - timedelta(hours=hours)).sum())
    return {
        "received": received,
        "expected": expected,
        "rate": min(received / expected, 1.0) if expected else 0.0,
    }


def milestone_progress(df: pd.DataFrame) -> List[Dict[str, Any]]:
    total = 0 if df.empty else len(df)
    out = []
    for name, target, desc in MILESTONES:
        pct = min(total / target * 100, 100) if target else 0
        out.append({
            "name": name, "desc": desc,
            "progress": f"{total}/{target}", "pct": pct,
            "met": total >= target,
        })
    return out


def render_report(
    *, today: datetime, tests_ok: bool, tests_summary: str,
    acc: Dict[str, Any], health: Dict[str, Any],
    detection: str, milestones: List[Dict[str, Any]],
) -> str:
    L: List[str] = []
    L.append(f"# 📅 데일리 리포트 — {today:%Y-%m-%d} (KST)")
    L.append("")
    L.append(f"> 자동 생성: {today:%Y-%m-%d %H:%M KST} · GitHub Actions `daily_loop.yml`")
    L.append("")

    L.append("## ✅ 회귀 테스트")
    L.append(f"- {'🟢' if tests_ok else '🔴'} `{tests_summary}`")
    L.append("")

    L.append("## 📦 누적 데이터")
    if acc["total"] == 0:
        L.append("- _수집된 데이터 없음 — KPX API 키 등록 후 수집 시작_")
    else:
        L.append(f"- 총 누적: **{acc['total']:,} 건** ({acc['duration_h']:.1f}시간 분량)")
        L.append(f"- 시각 범위: {acc['first']:%Y-%m-%d %H:%M} ~ {acc['last']:%Y-%m-%d %H:%M}")
        L.append(f"- unique 시각: {acc['unique_times']:,}개")
    L.append("")

    L.append("## ⏱️ 최근 24시간 수집 성공률")
    L.append(f"- {health['received']} / {health['expected']}건 = **{health['rate']*100:.1f}%**")
    L.append("")

    L.append("## 🚨 다층 이상탐지 요약")
    L.append(f"- {detection}")
    L.append("")

    L.append("## 🎯 데이터 마일스톤")
    for m in milestones:
        bar = "█" * int(m["pct"] / 10) + "░" * (10 - int(m["pct"] / 10))
        icon = "✅" if m["met"] else "⏳"
        L.append(f"- {icon} `{m['name']}` ({m['desc']}): {m['progress']} {bar} {m['pct']:.0f}%")
    L.append("")

    L.append("---")
    L.append("🤖 *매일 자동 생성. Claude 세션에서 다음 작업 결정 시 참조.*")
    return "\n".join(L)


def main() -> int:
    today = datetime.now(KST)
    print(f"=== Daily Dev Loop @ {today:%Y-%m-%d %H:%M KST} ===")

    df = database.load_df()
    print(f"📦 누적 데이터: {len(df)}건")

    print("✅ pytest 실행...")
    tests_ok, tests_summary = run_pytest()
    print(f"   {tests_summary}")

    acc = accumulation_stats(df)
    health = health_recent(df)
    milestones = milestone_progress(df)

    if df.empty:
        detection = "데이터 없음 — 분석 생략"
    else:
        print("🚨 분석 플로우 실행...")
        result = run_analysis(df)
        detection = detection_summary(result)
    print(f"   탐지 요약: {detection}")

    report = render_report(
        today=today, tests_ok=tests_ok, tests_summary=tests_summary,
        acc=acc, health=health, detection=detection, milestones=milestones,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(report, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(report, encoding="utf-8")
    print(f"📝 리포트 저장: {out.relative_to(_PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
