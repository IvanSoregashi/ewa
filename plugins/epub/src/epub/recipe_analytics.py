from sqlalchemy import inspect
from sqlmodel import Session, SQLModel

from epub.processing_run import ProcessingRun
from library.database.sqlite_model_table import get_engine


def record_analytics(runs: list[ProcessingRun], db_url: str) -> None:
    """Persist runs and their operation-owned evidence in one transaction."""
    if not runs:
        return
    records = [record for run in runs for record in run.analytics]
    models = {type(record) for record in records} | {ProcessingRun}
    tables = [inspect(model).local_table for model in models]
    engine = get_engine(db_url)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        SQLModel.metadata.create_all(connection, tables=tables)
        connection.commit()
        with Session(connection, expire_on_commit=False) as session, session.begin():
            session.add_all(runs)
            session.flush()
            session.add_all(records)
