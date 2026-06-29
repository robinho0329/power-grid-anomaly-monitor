"""KPX 수급 XML 파싱 단위 테스트 — 네트워크 없이 순수 함수 검증."""
from datetime import datetime

from src.collectors.kpx import parse_sukub

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><body><items>
  <item>
    <baseDatetime>20260629000000</baseDatetime>
    <suppAbility>92158.1</suppAbility>
    <currPwrTot>57032.4</currPwrTot>
    <forecastLoad>76700.0</forecastLoad>
    <suppReservePwr>35125.6</suppReservePwr>
    <suppReserveRate>61.5889</suppReserveRate>
    <operReservePwr>10274.0</operReservePwr>
    <operReserveRate>17.6532</operReserveRate>
  </item>
  <item>
    <baseDatetime>20260629000500</baseDatetime>
    <suppAbility>93661.3</suppAbility>
    <currPwrTot>56507.0</currPwrTot>
    <forecastLoad>76700.0</forecastLoad>
    <suppReservePwr>37154.4</suppReservePwr>
    <suppReserveRate>65.7518</suppReserveRate>
    <operReservePwr>11179.0</operReservePwr>
    <operReserveRate>19.37</operReserveRate>
  </item>
</items></body></response>"""


def test_parse_sukub_fields():
    recs = parse_sukub(SAMPLE_XML)
    assert len(recs) == 2
    r = recs[0]
    assert r["ts"] == datetime(2026, 6, 29, 0, 0, 0)
    assert r["supply_capacity"] == 92158.1
    assert r["current_load"] == 57032.4
    assert r["forecast_load"] == 76700.0
    assert r["reserve_rate"] == 61.5889
    assert r["oper_reserve_rate"] == 17.6532


def test_parse_sukub_empty():
    assert parse_sukub("<response><body><items></items></body></response>") == []
