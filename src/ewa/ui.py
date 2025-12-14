from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from typing import Any

from sqlmodel import SQLModel

console = Console()


def print_table(title: str, columns: list[str], rows: list[list]):
    """Prints a styled table."""
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*map(str, row))
    console.print(table)


def print_table_from_dicts(title: str, dicts: list[dict[str, Any]]):
    columns = list(dicts[0].keys())
    rows = []
    for row in dicts:
        assert list(row.keys()) == columns, "Not all keys present in dict"
        rows.append(list(row.values()))
    print_table(title, columns, rows)


def print_table_from_models(title: str, models: list[SQLModel]):
    def func(row: SQLModel) -> dict:
        if hasattr(row, "as_dict"):
            return row.as_dict()
        else:
            return row.model_dump()

    print_table_from_dicts(title, list(map(func, models)))


def ask_user(question: str, default: str = None) -> str:
    """Asks the user for input."""
    return Prompt.ask(question, default=default)


def confirm_user(question: str, default: bool = True) -> bool:
    """Asks the user for confirmation."""
    return Confirm.ask(question, default=default)


def print_success(message: str):
    console.print(f"[bold green]Success:[/bold green] {message}")


def print_error(message: str):
    console.print(f"[bold red]Error:[/bold red] {message}")
