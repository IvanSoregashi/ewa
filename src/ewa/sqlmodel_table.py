from collections.abc import Iterable, Sequence
from enum import StrEnum
from queue import Queue
from itertools import batched
from threading import Thread
from typing import Self

from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import text

from ewa.main import settings

TERMINATOR = object()  # Queue terminator


class SQLModelTable:
    class OnConflict(StrEnum):
        CONFLICT = "CONFLICT"
        UPDATE = "UPDATE"
        IGNORE = "IGNORE"

    def __init__(self, table: type[SQLModel], url: str | None = None, **kwargs):
        self.engine = create_engine(url or settings.database_url, **kwargs)
        with self.engine.connect() as connection:
            connection.execute(text("PRAGMA journal_mode=WAL;"))
            connection.commit()
        self.table_model: type[SQLModel] = table
        self.table = table.__table__
        # self.drop()
        self.create()
        self.primary_keys = [column.name for column in self.table.primary_key.columns]
        self.columns = [column.name for column in self.table.columns]

    def drop(self) -> Self:
        self.table.drop(self.engine)
        return self

    def create(self, checkfirst: bool = True) -> Self:
        self.table.create(self.engine, checkfirst=checkfirst)
        return self

    def bulk_insert_or_ignore(
        self, session: Session, records: Iterable[SQLModel]
    ) -> None:
        list_of_dicts = [record.model_dump() for record in records]
        insert_stmt = sqlite_insert(self.table).values(list_of_dicts)
        insert_or_ignore_stmt = insert_stmt.on_conflict_do_nothing(
            index_elements=self.primary_keys
        )
        session.exec(insert_or_ignore_stmt)

    def bulk_insert_or_update(
        self, session: Session, records: Iterable[SQLModel]
    ) -> None:
        list_of_dicts = [record.model_dump() for record in records]
        insert_stmt = sqlite_insert(self.table).values(list_of_dicts)
        update_mapping = {
            column.name: getattr(insert_stmt.excluded, column.name)
            for column in self.table.columns
            if not column.primary_key
        }
        insert_or_update_stmt = insert_stmt.on_conflict_do_update(
            index_elements=self.primary_keys, set_=update_mapping
        )
        session.exec(insert_or_update_stmt)

    def write(
        self,
        records: Iterable | Queue,
        batch: int = 1000,
        on_conflict: OnConflict = OnConflict.UPDATE,
    ) -> None:
        print(f"start write {records, type(records)}")
        if isinstance(records, Queue):
            records = iter(records.get, TERMINATOR)
        batched_records = [records] if batch == 0 else batched(records, batch)

        with Session(self.engine) as session:
            for i, batch_of_records in enumerate(batched_records):
                match on_conflict:
                    case self.OnConflict.CONFLICT:
                        session.add_all(batch_of_records)
                    case self.OnConflict.UPDATE:
                        self.bulk_insert_or_update(session, batch_of_records)
                    case self.OnConflict.IGNORE:
                        self.bulk_insert_or_ignore(session, batch_of_records)
                session.commit()

    def write_in_thread(
        self,
        records: Iterable | Queue,
        batch: int = 1000,
        on_conflict: OnConflict = OnConflict.UPDATE,
    ) -> None:
        Thread(target=self.write, args=(records, batch, on_conflict)).start()

    def count_rows(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text(f"SELECT COUNT(*) FROM {self.table_model.__tablename__}")
            ).fetchone()[0]

    def read_rows(self, limit: int = 100) -> Sequence[SQLModel]:
        with Session(self.engine) as session:
            statement = select(self.table_model).limit(limit)
            return session.exec(statement).all()
