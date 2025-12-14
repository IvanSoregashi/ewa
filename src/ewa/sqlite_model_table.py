from collections.abc import Iterable, Sequence
from enum import StrEnum
from queue import Queue
from itertools import batched
from typing import Self, get_args

from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert, Insert
from sqlalchemy import text

from ewa.main import settings
from ewa.ui import print_error

TERMINATOR = object()  # Queue terminator


class SQLiteModelTable[TableType: SQLModel]:
    """Class is Parent class only, not meant for initialization of Objects, needs to be inherited from."""

    class OnConflict(StrEnum):
        CONFLICT = "CONFLICT"
        UPDATE = "UPDATE"
        IGNORE = "IGNORE"

    def __init__(self, url: str | None = None, **kwargs):
        self.engine = create_engine(url or settings.database_url, **kwargs)
        with self.engine.connect() as connection:
            connection.execute(text("PRAGMA journal_mode=WAL;"))
            connection.execute(text("PRAGMA synchronous=NORMAL;"))
            connection.execute(text("PRAGMA cache_size=-64000;"))
            connection.commit()
        self.table_model: type[TableType] = get_args(self.__orig_bases__[0])[0]
        self.table = self.table_model.__table__
        self.create()
        self.primary_keys = [column.name for column in self.table.primary_key.columns]
        self.columns = [column.name for column in self.table.columns]

    def drop(self) -> Self:
        self.table.drop(self.engine)
        return self

    def create(self, checkfirst: bool = True) -> Self:
        self.table.create(self.engine, checkfirst=checkfirst)
        return self

    def insert_row(self, row: TableType, on_conflict: OnConflict = OnConflict.UPDATE) -> None:
        insert_stmt = self.bulk_insert_statement((row.model_dump(),), on_conflict=on_conflict)
        with Session(self.engine) as session:
            session.exec(insert_stmt)

    def insert_rows(self, rows: Iterable[TableType], on_conflict: OnConflict = OnConflict.UPDATE) -> None:
        with Session(self.engine) as session:
            self.bulk_insert_models(session, rows, on_conflict=on_conflict)

    def insert_dicts(self, rows: Iterable[dict], on_conflict: OnConflict = OnConflict.UPDATE) -> None:
        with Session(self.engine) as session:
            self.bulk_insert_dicts(session, rows, on_conflict=on_conflict)

    def read_row(self, **kwargs) -> TableType | None:
        filter_clauses = []
        for key, value in kwargs.items():
            column = getattr(self.table_model, key, None)
            if column is not None:
                filter_clauses.append(column == value)
            else:
                print_error(f"Warning: '{key}' is not a valid column in {self.table_model.__name__}")
        query = select(self.table_model).where(*filter_clauses)
        with Session(self.engine) as session:
            result = session.exec(query)
            return result.one_or_none()

    def count_rows(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(text(f"SELECT COUNT(*) FROM {self.table_model.__tablename__}")).fetchone()[0]

    def read_rows(self, limit: int = 100) -> list[TableType]:
        with Session(self.engine) as session:
            statement = select(self.table_model).limit(limit)
            return list(session.exec(statement).all())

    def bulk_insert_statement(self, records: Sequence[dict], on_conflict: OnConflict) -> Insert:
        insert_stmt = sqlite_insert(self.table).values(records)
        match on_conflict:
            case self.OnConflict.CONFLICT:
                return insert_stmt
            case self.OnConflict.IGNORE:
                return insert_stmt.on_conflict_do_nothing(index_elements=self.primary_keys)
            case self.OnConflict.UPDATE:
                update_mapping = {
                    column.name: getattr(insert_stmt.excluded, column.name)
                    for column in self.table.columns
                    if not column.primary_key
                }
                return insert_stmt.on_conflict_do_update(index_elements=self.primary_keys, set_=update_mapping)
            case _:
                raise ValueError(f"Unrecognized on_conflict value {on_conflict}")

    def bulk_insert_dicts(
        self,
        session: Session,
        records: Iterable[dict],
        batch_size: int = 1000,
        on_conflict: OnConflict = OnConflict.UPDATE,
    ) -> None:
        if isinstance(records, Queue):
            records = iter(records.get, TERMINATOR)
        for i, batch in enumerate(batched(records, batch_size)):
            print(i, len(batch))
            batch_insert_stmt = self.bulk_insert_statement(batch, on_conflict=on_conflict)
            session.exec(batch_insert_stmt)
            session.commit()

    def bulk_insert_models(
        self,
        session: Session,
        records: Iterable[TableType] | None = None,
        on_conflict: OnConflict = OnConflict.UPDATE,
    ) -> None:
        if isinstance(records, Queue):
            records = iter(records.get, TERMINATOR)
        records = map(lambda x: x.model_dump(), records)
        self.bulk_insert_dicts(session, records, on_conflict=on_conflict)
