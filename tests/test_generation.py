"""발전믹스 XML 파싱 + 저장 테스트."""
from datetime import datetime

from src.collectors.kpx import parse_generation
from src.storage.database import get_engine, load_generation_df, upsert_generation

GEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><body><items>
  <item>
    <baseDatetime>20260629143000</baseDatetime>
    <fuelPwr1>3000</fuelPwr1>
    <fuelPwr3>20000</fuelPwr3>
    <fuelPwr4>23000</fuelPwr4>
    <fuelPwr6>18000</fuelPwr6>
    <fuelPwr7>5000</fuelPwr7>
    <fuelPwr8>4000</fuelPwr8>
    <fuelPwr9>6000</fuelPwr9>
    <fuelPwrTot>79000</fuelPwrTot>
  </item>
</items></body></response>"""


def test_parse_generation_maps_and_aggregates():
    recs = parse_generation(GEN_XML)
    by_src = {r["source"]: r["generation_mw"] for r in recs}
    assert by_src["원자력"] == 23000.0
    assert by_src["LNG"] == 18000.0
    assert by_src["석탄"] == 25000.0    # 유연탄(20000) + 국내탄(5000)
    assert by_src["신재생"] == 10000.0  # 신재생(4000) + 태양광(6000)
    assert "fuelPwrTot" not in by_src     # 총수요는 제외


def test_upsert_generation_idempotent():
    eng = get_engine("sqlite:///:memory:")
    recs = [{"ts": datetime(2026, 6, 29, 14, 30), "source": "원자력", "generation_mw": 23000.0}]
    assert upsert_generation(recs, eng) == 1
    assert upsert_generation(recs, eng) == 0
    assert len(load_generation_df(eng)) == 1
