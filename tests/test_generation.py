"""발전믹스 파싱 + 저장 테스트 (long/wide 응답 형태 모두)."""
from datetime import datetime

from src.collectors.kpx import parse_generation
from src.storage.database import get_engine, load_generation_df, upsert_generation


def _payload(items):
    return {"response": {"body": {"items": {"item": items}}}}


def test_parse_long_form():
    recs = parse_generation(
        _payload(
            [
                {"baseDatetime": "20260629143000", "발전원": "원자력", "발전량": "23,000"},
                {"baseDatetime": "20260629143000", "fuel": "LNG", "generation": "18000"},
            ]
        )
    )
    assert len(recs) == 2
    by_src = {r["source"]: r["generation_mw"] for r in recs}
    assert by_src["원자력"] == 23000.0
    assert by_src["LNG"] == 18000.0


def test_parse_wide_form_and_alias():
    recs = parse_generation(
        _payload([{"baseDatetime": "20260629143000", "nuclear": "23000", "유연탄": "30000"}])
    )
    by_src = {r["source"]: r["generation_mw"] for r in recs}
    assert by_src["원자력"] == 23000.0
    assert by_src["석탄"] == 30000.0   # 유연탄 → 석탄 정규화


def test_upsert_generation_idempotent():
    eng = get_engine("sqlite:///:memory:")
    recs = [{"ts": datetime(2026, 6, 29, 14, 30), "source": "원자력", "generation_mw": 23000.0}]
    assert upsert_generation(recs, eng) == 1
    assert upsert_generation(recs, eng) == 0
    assert len(load_generation_df(eng)) == 1
