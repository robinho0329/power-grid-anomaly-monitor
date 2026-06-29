"""발전소 위치 시드 데이터 로더 (GIS 맥락 레이어).

⚠️ data/plants.csv는 주요 발전소 **근사 좌표 시드**다. 정확한 좌표/설비용량은
   공식 데이터셋(공공데이터포털 발전설비 현황 등)으로 교체 가능하도록 분리했다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config

PLANTS_CSV = config.BASE_DIR / "data" / "plants.csv"

# 발전원별 색상 (대시보드 지도/범례 공용)
SOURCE_COLORS = {
    "원자력": "#e45756",
    "석탄": "#4c4c4c",
    "LNG": "#f58518",
    "유류": "#b279a2",
    "수력": "#4c78a8",
    "양수": "#72b7b2",
    "신재생": "#54a24b",
}


def load_plants(path: Path | None = None) -> pd.DataFrame:
    """발전소 시드 데이터를 DataFrame으로 로드. 컬럼 검증 포함."""
    df = pd.read_csv(path or PLANTS_CSV)
    required = {"name", "source", "capacity_mw", "lat", "lon"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"plants.csv 필수 컬럼 누락: {missing}")
    df["color"] = df["source"].map(SOURCE_COLORS).fillna("#999999")
    return df
