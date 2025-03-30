import logging

from sqlalchemy import (
    Column,
    Connection,
    create_engine,
    Engine,
    func,
    Integer,
    MetaData,
    String,
    Table,
    text,
    TIMESTAMP,
)
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.sql.ddl import CreateTable

from monotome import MigrationPage, Page

logger = logging.getLogger(__name__)


METADATA = MetaData()

TrackingTable = Table(
    "monotome_migrations",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("stack", String),
    Column("feature", String),
    Column("page", String),
    Column("checksum", String),
    Column("applied_at", TIMESTAMP, server_default=func.now()),
)


def get_engine(url: str) -> Engine:
    return create_engine(url=url, echo=False)


def create_tracking_table(engine: Engine):
    with engine.connect() as conn:
        conn.execute(CreateTable(TrackingTable, if_not_exists=True))
        conn.commit()


def get_tracked_migrations(engine: Engine) -> list[Page]:
    create_tracking_table(engine=engine)
    records = []
    with engine.connect() as conn:
        stmt = TrackingTable.select()
        cursor = conn.execute(stmt)

        for row in cursor:
            records.append(
                Page(
                    id=row.t.page,
                    feature=row.t.feature,
                    checksum=row.t.checksum,
                    stack=row.t.stack,
                )
            )
    return records


def apply_schema(sql: str, target_schema: str):
    return sql.replace("__SCHEMA__", target_schema)


def apply_migration_content(
    conn: Connection,
    page: MigrationPage,
    target_schema: str,
) -> bool:
    sql = apply_schema(sql=page.content, target_schema=target_schema)
    try:
        conn.execute(text(sql))
    except ProgrammingError as e:
        logger.error(f"Failed to apply migration in {page.id}")
        e.page = page
        raise e
    stmt = TrackingTable.insert().values(
        stack=page.stack,
        feature=page.feature,
        page=page.id,
        checksum=page.checksum,
    )
    conn.execute(stmt)
    return True
