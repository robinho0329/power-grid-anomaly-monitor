"""저장소 멱등성 테스트 — 인메모리 SQLite."""
from datetime import datetime

from src.storage.database import get_engine, load_df, upsert_records


def _engine():
    return get_engine("sqlite:///:memory:")


def test_upsert_is_idempotent():
    eng = _engine()
    recs = [
        {"ts": datetime(2026, 6, 29, 0, 0), "current_load": 60000.0,
         "supply_capacity": 90000.0, "reserve_power": 30000.0,
         "reserve_rate": 50.0, "temperature": 20.0},
    ]
    assert upsert_records(recs, eng) == 1
    assert upsert_records(recs, eng) == 0  # 같은 ts 재삽입 안 됨
    df = load_df(eng)
    assert len(df) == 1
    assert df.iloc[0]["current_load"] == 60000.0
