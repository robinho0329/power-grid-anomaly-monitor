"""SQLAlchemy ORM 모델 — 전력수급 시계열 스냅샷."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PowerSupply(Base):
    """5분 단위 전력수급 스냅샷 (전국 계통 기준)."""

    __tablename__ = "power_supply"
    __table_args__ = (UniqueConstraint("ts", name="uq_power_supply_ts"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    supply_capacity: Mapped[float | None] = mapped_column(Float)     # suppAbility
    current_load: Mapped[float | None] = mapped_column(Float)        # currPwrTot
    forecast_load: Mapped[float | None] = mapped_column(Float)       # forecastLoad
    reserve_power: Mapped[float | None] = mapped_column(Float)       # suppReservePwr
    reserve_rate: Mapped[float | None] = mapped_column(Float)        # suppReserveRate
    oper_reserve_power: Mapped[float | None] = mapped_column(Float)  # operReservePwr
    oper_reserve_rate: Mapped[float | None] = mapped_column(Float)   # operReserveRate


class PowerGeneration(Base):
    """5분 단위 발전원별 발전량 (long format: ts × source)."""

    __tablename__ = "power_generation"
    __table_args__ = (UniqueConstraint("ts", "source", name="uq_power_gen_ts_source"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    generation_mw: Mapped[float | None] = mapped_column(Float)
