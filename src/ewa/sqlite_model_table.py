import time
from collections.abc import Iterable, Sequence, Collection, Callable
from enum import StrEnum
from queue import Queue
from itertools import batched
from typing import Self, get_args
from threading import Thread

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

    def __init__(self, url: str | None = None, on_conflict: OnConflict = OnConflict.UPDATE, **kwargs):
        self.engine = create_engine(url or settings.database_url, **kwargs)
        with self.engine.connect() as connection:
            connection.execute(text("PRAGMA journal_mode=WAL;"))
            connection.execute(text("PRAGMA synchronous=NORMAL;"))
            connection.execute(text("PRAGMA cache_size=-64000;"))
            connection.commit()
        self.session: Session | None = None
        self.table_model: type[TableType] = get_args(self.__orig_bases__[0])[0]
        self.table = self.table_model.__table__
        self.create()
        self.primary_keys = [column.name for column in self.table.primary_key.columns]
        self.columns = [column.name for column in self.table.columns]
        self.on_conflict = on_conflict
        self.write_thread: Thread | None = None

    def __enter__(self) -> Self:
        self.session = Session(self.engine)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.session.close()

    def drop(self) -> Self:
        self.table.drop(self.engine)
        return self

    def create(self, checkfirst: bool = True) -> Self:
        self.table.create(self.engine, checkfirst=checkfirst)
        return self

    def create_all(self) -> Self:
        self.table_model.metadata.create_all(self.engine)

    def read_row(self, **kwargs) -> TableType | None:
        filter_clauses = []
        for key, value in kwargs.items():
            column = getattr(self.table_model, key, None)
            if column is not None:
                filter_clauses.append(column == value)
            else:
                print_error(f"Warning: '{key}' is not a valid column in {self.table_model.__name__}")
        query = select(self.table_model).where(*filter_clauses)
        return self.session.exec(query).one_or_none()

    def count_rows(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(text(f"SELECT COUNT(*) FROM {self.table_model.__tablename__}")).fetchone()[0]

    def read_rows(self, limit: int = 100) -> list[TableType]:
        statement = select(self.table_model).limit(limit)
        return list(self.session.exec(statement).all())

    def bulk_insert_statement(self, records: Sequence[dict]) -> Insert:
        insert_stmt = sqlite_insert(self.table).values(records)
        match self.on_conflict:
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
                raise ValueError(f"Unrecognized on_conflict value {self.on_conflict}")

    def insert_row(self, row: TableType) -> None:
        insert_stmt = self.bulk_insert_statement((row.model_dump(),))
        self.session.exec(insert_stmt)
        self.session.commit()

    def bulk_insert_dicts(
        self,
        batcher: Iterable[tuple[dict]],
        total_func: Callable[[], int],
        current_func: Callable[[], int],
        increment: Callable[[int], None],
    ) -> None:
        task_name = f"[cyan]writing {self.table_model.__tablename__}"
        start_time = time.time()
        print(f"[cyan] Starting {self.table_model.__tablename__} bulk insert task")
        for batch in batcher:
            increment(len(batch))
            print(task_name, current_func(), total_func())
            batch_insert_stmt = self.bulk_insert_statement(batch)
            self.session.exec(batch_insert_stmt)
            self.session.commit()
        print(f"[cyan] Finished {self.table_model.__tablename__} bulk insert task in [{time.time() - start_time:>7.2f}s]")

    def bulk_insert_models(
        self,
        records: Collection[TableType] | None = None,
    ) -> None:
        current = 0

        def increment(count: int) -> None:
            nonlocal current
            current += count

        total = len(records)
        self.bulk_insert_dicts(
            batcher=batched(map(lambda x: x.model_dump(), records), 1000),
            total_func=lambda: total,
            current_func=lambda: current,
            increment=increment,
        )

    def write_from_queue(self, queue: Queue[dict]) -> None:
        current = 0

        def increment(count: int) -> None:
            nonlocal current
            current += count

        self.bulk_insert_dicts(
            batcher=batched(iter(queue.get, TERMINATOR), 1000),
            total_func=lambda: current + queue.qsize(),
            current_func=lambda: current,
            increment=increment,
        )

    def write_from_queue_in_thread(self, queue: Queue[dict]) -> None:
        self.write_thread = Thread(target=self.write_from_queue, args=(queue,))
        self.write_thread.start()

    def await_write_completion(self):
        if self.write_thread is None:
            return
        while self.write_thread.is_alive():
            time.sleep(1)
        self.write_thread = None
