import time
from collections.abc import Iterable
from itertools import batched
from typing import Self, get_args, Literal, TypeVar
from threading import Thread
import pandas as pd

from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text

from ewa.main import settings
from library.database.sqlite_utils import initialize_db
from library.database.sqlmodel_statements import (
    bulk_insert_statement,
    bulk_upsert_statement,
    bulk_update_statement,
    select_query,
    most_common_query,
)

TERMINATOR = object()  # Queue terminator
TableType = TypeVar("TableType", bound=SQLModel)


class SQLiteModelTable[TableType]:
    """Class is Parent class only, not meant for initialization of Objects, needs to be inherited from."""

    def __init__(self, url: str | None = None, **kwargs):
        url = url or settings.database_url
        self.engine = create_engine(url, **kwargs)

        initialize_db(self.engine)

        self.session: Session | None = None
        self.write_thread: Thread | None = None

        # Получаем генерик TableType SQLModel класса
        model: type[TableType] = get_args(self.__orig_bases__[0])[0]
        self.model = model
        self.table = self.model.__table__

        self.bulk_insert_statement = bulk_insert_statement(model)
        self.bulk_upsert_statement = bulk_upsert_statement(model)
        self.bulk_update_statement = bulk_update_statement(model)

        self.columns = [column.name for column in self.table.columns]
        self.primary_keys = [column.name for column in self.table.primary_key.columns]
        self.relationships = [getattr(model, key) for key in model.__sqlmodel_relationships__.keys()]

        self.create_all()

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
        self.model.metadata.create_all(self.engine)

    def count_rows(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(text(f"SELECT COUNT(*) FROM {self.model.__tablename__}")).fetchone()[0]

    def get_one(self, *args, lazy: bool = True, **kwargs) -> TableType | None:
        query = select_query(self.model, *args, lazy=lazy, relationships=self.relationships, **kwargs)
        return self.session.exec(query).first()

    def get_many(self, *args, lazy: bool = True, limit: int = 100, offset: int = 0, **kwargs) -> list[TableType]:
        query = select_query(
            self.model, *args, lazy=lazy, limit=limit, offset=offset, relationships=self.relationships, **kwargs
        )
        return list(self.session.exec(query).all())

    def get_df(
        self, *args, lazy: bool = True, limit: int | None = None, offset: int | None = None, **kwargs
    ) -> pd.DataFrame:
        query = select_query(
            self.model, *args, lazy=lazy, limit=limit, offset=offset, relationships=self.relationships, **kwargs
        )
        return pd.read_sql(query, self.engine)

    def df_to_models(self, df: pd.DataFrame) -> list[TableType]:
        return [self.model(**row) for row in df.to_dict(orient="records")]

    def get_most_common(
        self,
        group_fields: list,
        *args,
        more_then: int | None = None,
        less_than: int | None = None,
        equal_to: int | None = None,
    ):
        for i in range(len(group_fields)):
            if isinstance(group_fields[i], str):
                group_fields[i] = getattr(self.model, group_fields[i])
        query = most_common_query(group_fields, *args, more_then=more_then, less_than=less_than, equal_to=equal_to)
        return list(self.session.exec(query).all())

    def insert_one(self, row: TableType) -> None:
        self.session.add(row)
        self.session.commit()

    def insert_many(self, rows: list[TableType]) -> None:
        self.session.add_all(rows)
        self.session.commit()

    def upsert_many(self, rows: list[TableType]) -> None:
        self.upsert_many_dicts(rows)

    def insert_df(self, df: pd.DataFrame, batch_size: int = 1000) -> None:
        records = df.to_dict(orient="records")
        self.insert_many_dicts(batched(records, batch_size))

    def upsert_df(self, df: pd.DataFrame, batch_size: int = 1000) -> None:
        records = df.to_dict(orient="records")
        self.upsert_many_dicts(batched(records, batch_size))

    def insert_many_dicts(self, batcher: Iterable[tuple[dict]]) -> None:
        for batch in batcher:
            self.session.exec(self.bulk_insert_statement, params=batch)
            self.session.commit()

    def upsert_many_dicts(self, batcher: Iterable[tuple[dict]]) -> None:
        for batch in batcher:
            self.session.exec(self.bulk_upsert_statement, params=batch)
            self.session.commit()

    def update_many_dicts(self, batcher: Iterable[tuple[dict]]) -> None:
        for batch in batcher:
            self.session.bulk_update_mappings(self.model, batch)
            self.session.commit()

    def delete_one(self, row: TableType) -> None:
        self.session.delete(row)
        self.session.commit()

    def write_from_queue_in_thread(
        self, batcher: Iterable[tuple[dict, ...]], method: Literal["insert", "upsert", "update"] = "upsert"
    ) -> None:
        func = self.insert_many_dicts
        match method:
            case "insert":
                func = self.insert_many_dicts
            case "upsert":
                func = self.upsert_many_dicts
            case "update":
                func = self.update_many_dicts

        self.write_thread = Thread(target=func, args=(batcher,))
        self.write_thread.start()

    def await_write_completion(self):
        if self.write_thread is None:
            return
        while self.write_thread.is_alive():
            time.sleep(1)
        self.write_thread = None


def models_to_df(models: Iterable[TableType]) -> pd.DataFrame:
    return pd.DataFrame([model.model_dump() for model in models])
