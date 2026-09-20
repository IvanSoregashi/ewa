"""Console reporting for processing runs."""

from pathlib import Path
from typing import TYPE_CHECKING

from ewa.cli.print_table import print_table_from_dicts
from ewa.ui import print_success, print_error
from library.asserts import require
from epub.errors import EpubSkipReason, EpubErrorReason
from library.epub.resources import IndexInfo

if TYPE_CHECKING:
    from epub.processing_run import ProcessingRun


def byte_size_to_mb_str(size: int | None) -> str:
    if size is None:
        return "N/A"
    return f"{size / 1024 / 1024:.2f} MB"


def format_sizes(info: IndexInfo | None) -> str:
    if info is None:
        return "N/A"
    string = byte_size_to_mb_str(info.compress_size)
    if info.compress_size != info.total_size:
        string += f" ({byte_size_to_mb_str(info.total_size)})"
    return string


def percent_of(size_of: int | None, size_to: int | None) -> str:
    if size_of is None or size_of == 0 or size_to is None:
        return "N/A"
    return f"{round(size_to / size_of * 100):>03}%"


def report(run: ProcessingRun) -> None:
    original_epub = run.original_epub

    path = original_epub.path if original_epub else run.input_path
    size = byte_size_to_mb_str(original_epub.path_size) if original_epub else "unknown size"
    report = f"{path if path is not None else 'unknown input'} {size}"
    if run.success:
        report += "\nOPERATION RESULT: SUCCESS"
    if run.skip:
        report += f"\nOPERATION RESULT: SKIP {EpubSkipReason(run.skip).name}"
    if run.error:
        report += f"\nOPERATION RESULT: ERROR {EpubErrorReason(run.error).name}"

    if run.details:
        report += f"\n{run.details}"
    print_success(report)

    if run.success:
        original_epub = require(original_epub)
        new_epub = require(run.new_epub)
        o_size = original_epub.total.compress_size if original_epub.total is not None else None
        n_size = new_epub.total.compress_size if new_epub.total is not None else None
        size_reduction = o_size - n_size if o_size is not None and n_size is not None else None

        def make_dict(
            name: str,
            original_index_info: IndexInfo | None,
            new_index_info: IndexInfo | None,
        ) -> dict:
            old_count = original_index_info.count if original_index_info is not None else None
            new_count = new_index_info.count if new_index_info is not None else None
            count = str(old_count) if old_count is not None else "N/A"
            if new_count != old_count:
                count += f" -> {new_count if new_count is not None else 'N/A'}"
            old_size = original_index_info.compress_size if original_index_info is not None else None
            new_size = new_index_info.compress_size if new_index_info is not None else None
            local_size_reduction = old_size - new_size if old_size is not None and new_size is not None else None

            return {
                "name": name,
                "count": count,
                "original_size": format_sizes(original_index_info),
                "new_size": format_sizes(new_index_info),
                "reduction (%)": percent_of(old_size, new_size),
                "reduction (MB)": byte_size_to_mb_str(local_size_reduction),
                "% of total": f"{percent_of(o_size, old_size)} -> {percent_of(n_size, new_size)}",
                "% of total reduction": percent_of(size_reduction, local_size_reduction),
            }

        total = make_dict(
            name="total",
            original_index_info=original_epub.total,
            new_index_info=new_epub.total,
        )
        images = make_dict(
            name="images",
            original_index_info=original_epub.images,
            new_index_info=new_epub.images,
        )
        chapters = make_dict(
            name="chapters",
            original_index_info=original_epub.htmls,
            new_index_info=new_epub.htmls,
        )
        fonts = make_dict(
            name="fonts",
            original_index_info=original_epub.fonts,
            new_index_info=new_epub.fonts,
        )
        print_table_from_dicts(title="wow stats", dicts=[total, images, chapters, fonts])


def short_report(run: ProcessingRun) -> None:
    original_epub = run.original_epub
    mb_size = byte_size_to_mb_str(original_epub.path_size) if original_epub else "unknown size"
    path = original_epub.path if original_epub else run.input_path
    ori_path = Path(path).name if path is not None else "unknown input"
    if run.error:
        print_error(f"{mb_size} ERROR {EpubErrorReason(run.error).name} {ori_path!s}")
    if run.skip:
        print_success(f"{mb_size} SKIPPED {EpubSkipReason(run.skip).name} {ori_path!s}")
    if run.success:
        original_epub = require(original_epub)
        new_epub = require(run.new_epub)
        old_size = original_epub.total.compress_size if original_epub.total is not None else None
        new_size = new_epub.total.compress_size if new_epub.total is not None else None
        percent = percent_of(old_size, new_size)
        print_success(f"{mb_size:>09} REDUCED TO {percent} {ori_path!s}")
