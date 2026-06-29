"""발전소 시드 데이터 로더 테스트."""
from src.geo.plants import SOURCE_COLORS, load_plants


def test_load_plants_schema_and_colors():
    df = load_plants()
    assert {"name", "source", "capacity_mw", "lat", "lon", "color"} <= set(df.columns)
    assert len(df) >= 10
    # 좌표가 한반도 범위 안
    assert df["lat"].between(33, 39).all()
    assert df["lon"].between(124, 132).all()
    # 모든 발전원이 색상 매핑됨
    assert df["source"].isin(SOURCE_COLORS).all()
