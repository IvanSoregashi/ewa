import logging
from typing import Literal, Any, TypeVar

from sqlalchemy import BinaryExpression, Sequence
from sqlmodel import Session, SQLModel
from library.database.sqlmodel_statements import (
    SQL_DIALECT,
    select_query,
    insert_statement,
    upsert_statement,
    update_statement,
    bulk_update_statement,
)

logger = logging.getLogger(__name__)
ModelClass = TypeVar("ModelClass", bound=SQLModel)


def get_one(
    session: Session,
    model: type[ModelClass],
    *args: list[BinaryExpression],
    strategy: Literal["lazy", "selectin"] | None = None,
    relationships: list[str] | None = None,
    **kwargs: dict[str, Any],
) -> ModelClass | None:
    """

    :param session:
    :param model:
    :param args:
    :param strategy:
    :param relationships:
    :return:
    """
    query = select_query(model, *args, strategy=strategy, relationships=relationships, **kwargs)
    return session.exec(query).first()


def get_many(
    session: Session,
    model: type[ModelClass],
    *args: list[BinaryExpression],
    strategy: Literal["lazy", "selectin"] | None = None,
    relationships: list[str] | None = None,
    offset: int = 0,
    limit: int = 100,
    **kwargs: dict[str, Any],
) -> Sequence[ModelClass]:
    """

    :param session:
    :param model:
    :param strategy:
    :param relationships:
    :param offset:
    :param limit:
    :param kwargs:
    :return:
    """
    query = select_query(
        model, *args, strategy=strategy, relationships=relationships, offset=offset, limit=limit, **kwargs
    )
    return session.exec(query).all()


def delete_one(session: Session, instance: ModelClass):
    """

    :param session: Session
    :param instance: ModelClass
    """
    session.delete(instance)
    session.commit()


def insert_one(session: Session, row: ModelClass):
    """
    Writes a new instance of an SQLModel ORM model to the database, with an
    exception catch that rolls back the session in the event of failure.

    :param session: Session
    :param row: SQLModel
    :return: ScalarResult
    """
    session.add(row)
    session.commit()


def insert_many(
    session: Session,
    rows: tuple[ModelClass],
):
    """

    :param session: Session
    :param rows: Sequence[SQLModel]
    :return:
    """
    session.add_all(rows)
    session.commit()


def insert_dicts(
    session: Session,
    model: type[ModelClass],
    rows: Sequence[dict],
    ignore_conflicts: bool = False,
):
    """

    :param session:
    :param model:
    :param rows:
    :param ignore_conflicts:
    """
    statement = insert_statement(model, rows, ignore_conflicts)
    session.exec(statement)
    session.commit()


def upsert_dicts(
    session: Session,
    model: type[ModelClass],
    rows: Sequence[dict],
):
    """

    :param session:
    :param model:
    :param rows:
    """
    statement = upsert_statement(model, rows)
    session.exec(statement)
    session.commit()


def update_one(
    session: Session,
    model: type[ModelClass],
    *args: list[BinaryExpression],
    **kwargs: dict[str, Any],
):
    """

    :param session:
    :param model:
    :param args:
    :param kwargs:
    """
    statement = update_statement(model, *args, **kwargs)
    session.exec(statement)
    session.commit()


def update_many(
    session: Session,
    model: type[ModelClass],
    update_dicts: list[dict[str, Any]],
):
    """

    :param session:
    :param model:
    :param update_dicts:
    """
    statement = bulk_update_statement(model)
    session.exec(statement, params=update_dicts)
    session.commit()
