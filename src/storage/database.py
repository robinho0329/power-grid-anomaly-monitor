"""DB 엔진/세션 + 멱등 저장 유틸."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src import config
from src.storage.models import Base, PowerSupply


def get_engine(url: str | None = None):
    return create_engine(url or config.DATABASE_URL, future=True)


def init_db(engine=None) -> None:
    engine = engine or get_engine()
    Base.metadata.create_all(engine)


def upsert_records(records: list[dict], engine=None) -> int:
    """ts 기준 멱등 저장. 이미 있는 ts는 건너뛴다. 신규 저장 건수 반환."""
    engine = engine or get_engine()
    init_db(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    inserted = 0
    with SessionLocal() as session:  # type: Session
        existing = {
            ts for (ts,) in session.execute(select(PowerSupply.ts)).all()
        }
        for r in records:
            if r["ts"] in existing:
                continue
            session.add(PowerSupply(**r))
            inserted += 1
        session.commit()
    return inserted


def load_df(engine=None) -> pd.DataFrame:
    """전체 수급 시계열을 DataFrame으로 로드 (ts 오름차순)."""
    engine = engine or get_engine()
    init_db(engine)
    return pd.read_sql_table("power_supply", engine).sort_values("ts").reset_index(drop=True)
