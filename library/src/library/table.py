from typing import Any
from rich.console import Console
from rich.table import Table
import shutil


def print_table(
    data: list[dict[str, Any]], title: str | None = None, enum: bool = True
) -> None:
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

    console = Console()
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
            other_cols_avg = sum(
                w for c, w in col_widths.items() if c != widest_col[0]
            ) // (len(columns) - 1)
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
