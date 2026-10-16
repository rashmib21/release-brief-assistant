import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.sqlalchemy_url.startswith("sqlite") else {}
# pool_recycle: hosted Postgres (Neon) closes idle connections, so do not reuse old ones.
engine = create_engine(settings.sqlalchemy_url, connect_args=_connect_args, pool_pre_ping=True, pool_recycle=240)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def add_missing_columns() -> list[str]:
    """create_all never changes a table that already exists. If the database file was made by an older
    version of this app, columns added later are missing and every query fails with a 500.
    This adds any missing columns (nullable) so an old database keeps working."""
    added = []
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'
            with engine.begin() as conn:
                conn.execute(text(ddl))
            added.append(f"{table.name}.{col.name}")
    if added:
        logging.getLogger("app").warning("added missing database columns: %s", ", ".join(added))
    return added


MAX_DB_ID = 2**31 - 1


def get_by_id(db, model, row_id: int):
    """db.get that returns None for IDs the database cannot hold (a huge ID would otherwise be a 500)."""
    if not 0 < row_id <= MAX_DB_ID:
        return None
    return db.get(model, row_id)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
