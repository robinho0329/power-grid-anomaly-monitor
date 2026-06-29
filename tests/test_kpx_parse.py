"""KPX 응답 파싱 단위 테스트 — 네트워크 없이 순수 함수 검증."""
from datetime import datetime

from src.collectors.kpx import parse_sukub


def _payload(items):
    return {"response": {"body": {"items": {"item": items}}}}


def test_parse_basic():
    rec = parse_sukub(
        _payload(
            [
                {
                    "baseDatetime": "20260629143000",
                    "supplyCapacity": "95,000",
                    "currentLoad": "78,500",
                    "supplyReserve": "16,500",
                    "supplyReserveRate": "21.0",
                    "temperature": "28.4",
                }
            ]
        )
    )
    assert len(rec) == 1
    r = rec[0]
    assert r["ts"] == datetime(2026, 6, 29, 14, 30, 0)
    assert r["current_load"] == 78500.0   # 콤마 제거
    assert r["reserve_rate"] == 21.0


def test_parse_single_dict_item():
    # 단일 건이 dict로 와도 처리
    rec = parse_sukub(_payload({"baseDatetime": "20260629000000", "currentLoad": "60000"}))
    assert len(rec) == 1


def test_parse_drops_invalid_ts():
    rec = parse_sukub(_payload([{"currentLoad": "1"}]))  # ts 없음 → 제외
    assert rec == []
