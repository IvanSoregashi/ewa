import shutil
import pandas as pd

from typing import Any
from rich.table import Table
from sqlmodel import SQLModel
from ewa.ui import console


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


def print_df(
    df: pd.DataFrame,
    title: str = "",
    truncate: bool = False,
    columns: list[str] | None = None,
):
    if columns:
        df = df[columns]

    table = Table(title=title)

    for col in df.columns:
        if truncate:
            table.add_column(str(col), no_wrap=True, overflow="ellipsis", max_width=50)
        else:
            table.add_column(str(col))

    for row in df.itertuples(index=False, name=None):
        table.add_row(*map(str, row))

    console.print(table)


def print_table_old(data: list[dict[str, Any]], title: str | None = None, enum: bool = True) -> None:
    """
    Print a list of dictionaries as a pretty table.

    Args:
        data: List of dictionaries where each dict represents a row
        title: Optional title for the table
        enum: Optional boolean to enable enumeration of the table
    """
    if not data:
        return
    if enum:
        data = [{"N": i, **dt} for i, dt in enumerate(data)]

    table = Table(
        title=title,
        show_header=True,
        header_style="bold magenta",
    )

    term_width = shutil.get_terminal_size().columns
    columns = list(data[0].keys())
    col_widths = {col: len(str(col)) for col in columns}

    for row in data:
        for col in columns:
            value = str(row.get(col, ""))
            col_widths[col] = max(col_widths[col], len(value))

    total_width = sum(col_widths.values()) + len(columns) * 3 + 1

    if total_width > term_width:
        excess = total_width - term_width

        widest_col = max(col_widths.items(), key=lambda x: x[1])
        if len(columns) > 1:
            other_cols_avg = sum(w for c, w in col_widths.items() if c != widest_col[0]) // (len(columns) - 1)
        else:
            other_cols_avg = 0

        if widest_col[1] > other_cols_avg * 3:
            new_width = max(widest_col[1] - excess, 3)
            if new_width >= other_cols_avg:
                col_widths[widest_col[0]] = new_width
            else:
                col_widths[widest_col[0]] = other_cols_avg

    total_width = sum(col_widths.values()) + len(columns) * 3
    if total_width > term_width:
        excess = total_width - term_width
        for col in columns:
            reduction = int((col_widths[col] / total_width) * excess)
            col_widths[col] = max(col_widths[col] - reduction, 3)

    for col in columns:
        table.add_column(str(col), width=col_widths[col], no_wrap=True)

    for row in data:
        table.add_row(*[str(row.get(col, "")) for col in columns])

    console.print(table)
