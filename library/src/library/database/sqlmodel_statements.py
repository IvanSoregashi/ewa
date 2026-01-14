from typing import Literal, Any, TypeVar, Sequence
import importlib
from sqlalchemy import BinaryExpression, Insert, Update, bindparam
from sqlmodel import SQLModel, select, insert, update
from sqlalchemy.orm import lazyload, selectinload
from sqlmodel.sql.expression import Select, SelectOfScalar

SQL_DIALECT = Literal["postgresql", "sqlite"]
ModelClass = TypeVar("ModelClass", bound=SQLModel)


def import_insert(dialect: SQL_DIALECT) -> type[insert]:
    insert = importlib.import_module(f"sqlalchemy.dialects.{dialect}").insert
    return insert


def select_query(
    model: type[ModelClass],
    *args: list[BinaryExpression],
    strategy: Literal["lazy", "selectin"] | None = None,
    relationships: list[str] | None = None,
    offset: int | None = None,
    limit: int | None = None,
    **kwargs: dict[str, Any],
) -> Select | SelectOfScalar:
    statement = select(model).filter(*args).filter_by(**kwargs).offset(offset).limit(limit)

    if not strategy:
        return statement

    if relationships is None:
        relationships = list(model.__sqlmodel_relationships__.keys())

    rels = [getattr(model, key) for key in relationships]
    load_strategy = selectinload if strategy == "selectin" else lazyload

    return statement.options(*map(load_strategy, rels))


def insert_statement(
    model: type[ModelClass],
    dialect: SQL_DIALECT,
    rows: Sequence[dict],
    ignore_conflict: bool = False,
    primary_keys: list[str] | None = None,
) -> Insert:
    insert = import_insert(dialect)
    statement = insert(model).values(rows)

    if ignore_conflict:
        primary_keys = primary_keys or [column.name for column in model.__table__.primary_key.columns]
        statement = statement.on_conflict_do_nothing(index_elements=primary_keys)

    return statement


def bulk_insert_statement(
    model: type[ModelClass],
    dialect: SQL_DIALECT,
    ignore_conflict: bool = False,
    primary_keys: list[str] | None = None,
) -> Insert:
    insert = import_insert(dialect)
    table = model.__table__
    columns = [column.name for column in table.columns]

    statement = insert(model).values({column: bindparam(column) for column in columns})

    if ignore_conflict:
        primary_keys = primary_keys or [column.name for column in table.primary_key.columns]
        statement = statement.on_conflict_do_nothing(index_elements=primary_keys)

    return statement


def upsert_statement(
    model: type[ModelClass],
    dialect: SQL_DIALECT,
    rows: Sequence[dict],
    primary_keys: list[str] | None = None,
    update_mapping: dict[str, Any] | None = None,
) -> Insert:
    insert = import_insert(dialect)
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


def update_statement(
    model: type[ModelClass],
    *args: list[BinaryExpression],
    **kwargs: dict[str, Any],
) -> Update:
    return update(model).where(*args).values(**kwargs)


def bulk_update_statement(model: type[ModelClass]) -> Update:
    table = model.__table__
    primary_keys = [column.name for column in table.primary_key.columns]
    statement = update(model)
    for primary_key in primary_keys:
        statement = statement.where(getattr(model, primary_key) == bindparam(primary_key))
    return statement
