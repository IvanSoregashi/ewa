from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import JSON, Dialect, TypeDecorator


class TypedJSON[T](TypeDecorator[T]):
    """Keep a typed Python value while storing its JSON representation."""

    impl = JSON(none_as_null=True)
    cache_ok = True

    def __init__(self, model: type[T]):
        super().__init__()
        self.model = model
        self.adapter = TypeAdapter(model)

    def process_bind_param(self, value: T | None, dialect: Dialect) -> Any:
        return None if value is None else self.adapter.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: Dialect) -> T | None:
        return None if value is None else self.adapter.validate_python(value)
