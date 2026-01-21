import os
from typing import Literal, Any, TypeVar, Sequence
import importlib

from lxml.objectify import NoneElement
from sqlalchemy import BinaryExpression, Insert, Update, bindparam
from sqlalchemy.sql.functions import func
from sqlmodel import SQLModel, select, update
from sqlalchemy.orm import lazyload, selectinload
from sqlmodel.sql.expression import Select, SelectOfScalar

SQL_DIALECT = os.getenv("SQL_DIALECT", "sqlite")
insert = importlib.import_module(f"sqlalchemy.dialects.{SQL_DIALECT}").insert

ModelClass = TypeVar("ModelClass", bound=SQLModel)


def select_query(
    model: type[ModelClass],
    *args: list[BinaryExpression],
    lazy: bool = True,
    relationships: list | None = None,
    offset: int | None = None,
    limit: int | None = None,
    **kwargs: dict[str, Any],
) -> Select | SelectOfScalar:
    statement = select(model).filter(*args).filter_by(**kwargs).offset(offset).limit(limit)
    load_strategy = lazyload if lazy else selectinload

    return statement.options(*map(load_strategy, relationships))


def most_common_query(
    group_fields: list,
    *args: list[BinaryExpression],
    more_then: int | None = None,
    less_than: int | None = None,
    equal_to: int | None = None,
):
    having = None
    if equal_to is not None:
        having = func.count() == equal_to
    if less_than is not None:
        having = func.count() < less_than
    if more_then is not None:
        having = func.count() > more_then
    if having is None:
        having = func.count() > -1

    return select(*group_fields).where(*args).group_by(*group_fields).having(having)


def insert_statement(
    model: type[ModelClass],
    rows: Sequence[dict],
    ignore_conflict: bool = False,
    primary_keys: list[str] | None = None,
) -> Insert:
    statement = insert(model).values(rows)

    if ignore_conflict:
        primary_keys = primary_keys or [column.name for column in model.__table__.primary_key.columns]
        statement = statement.on_conflict_do_nothing(index_elements=primary_keys)

    return statement


def bulk_insert_statement(
    model: type[ModelClass],
    ignore_conflict: bool = False,
) -> Insert:
    table = model.__table__
    columns = [column.name for column in table.columns]

    statement = insert(model).values({column: bindparam(column) for column in columns})

    if ignore_conflict:
        primary_keys = [column.name for column in table.primary_key.columns]
        statement = statement.on_conflict_do_nothing(index_elements=primary_keys)

    return statement


def upsert_statement(
    model: type[ModelClass],
    rows: Sequence[dict],
    primary_keys: list[str] | None = None,
    update_mapping: dict[str, Any] | None = None,
) -> Insert:
    statement = insert(model).values(rows)
    return statement.on_conflict_do_update(
        index_elements=primary_keys or [column.name for column in model.__table__.primary_key.columns],
        set_=update_mapping
        or {
            column.name: getattr(statement.excluded, column.name)
            for column in model.__table__.columns
            if not column.primary_key
        },
    )


def bulk_upsert_statement(
    model: type[ModelClass],
) -> Insert:
    table = model.__table__
    columns = [c.name for c in table.columns]
    primary_keys = [column.name for column in table.primary_key.columns]
    update_mapping = {column.name: bindparam(column.name) for column in table.columns if not column.primary_key}

    statement = insert(model).values({column: bindparam(column) for column in columns})
    return statement.on_conflict_do_update(
        index_elements=primary_keys,
        set_=update_mapping,
    )


def update_statement(
    model: type[ModelClass],
    *args: list[BinaryExpression],
    **kwargs: dict[str, Any],
) -> Update:
    return update(model).where(*args).values(**kwargs)


def bulk_update_statement(model: type[ModelClass]) -> Update:
    primary_keys = [column.name for column in model.__table__.primary_key.columns]
    statement = update(model)
    for primary_key in primary_keys:
        statement = statement.where(getattr(model, primary_key) == bindparam(f"pk_{primary_key}"))
    return statement
