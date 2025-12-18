import builtins

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, TextColumn, TimeElapsedColumn, BarColumn, MofNCompleteColumn, TaskProgressColumn
from typing import Any, Self, Literal
from types import TracebackType
from sqlmodel import SQLModel

console = Console()


class DisplayProgress(Progress):
    def __init__(self, *args, **kwargs):
        if not args:
            args = (
                TextColumn("[progress.description]{task.description}"),
                MofNCompleteColumn(),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
            )
        self.builtin_print = builtins.print
        kwargs["console"] = console
        super().__init__(*args, **kwargs)

    def __enter__(self) -> Self:
        builtins.print = self._intercepted_print
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        builtins.print = self.builtin_print
        self.stop()

    @staticmethod
    def _expected_signature(args, kwargs) -> Literal[False] | tuple[str, int, int]:
        if kwargs:
            return False
        if len(args) != 3:
            return False
        task, current, total = args
        if isinstance(task, str) and isinstance(current, int) and isinstance(total, int):
            return task, current, total
        return False

    def _intercepted_print(self, *args, **kwargs):
        expected_signature = self._expected_signature(args, kwargs)
        if not expected_signature:
            return console.print(*args, **kwargs)

        task_name, current, total = expected_signature
        current_task = None

        for task in self.tasks:
            if task_name == task.description:
                current_task = task

        if current_task is None:
            self.add_task(task_name, completed=current, total=total)
            return None

        self.update(current_task.id, completed=current, total=total)
        return None


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
