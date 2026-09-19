"""Epub optimization result: the dataclass returned by the conversion pipeline
and persisted by the analytics recipes."""

from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import SQLModel

from ewa.cli.print_table import print_table_from_dicts
from ewa.ui import print_success, print_error
from library.analytics import OperationResult
from library.asserts import require
from library.epub.epub import EpubInfo
from epub.errors import EpubSkipReason, EpubErrorReason
from library.epub.resources import IndexInfo
from library.image.models import ImageOptimizationResult


def byte_size_to_mb_str(size: int) -> str:
    return f"{size / 1024 / 1024:.2f} MB"


def format_sizes(info: IndexInfo) -> str:
    string = byte_size_to_mb_str(info.compress_size)
    if info.compress_size != info.total_size:
        string += f" ({byte_size_to_mb_str(info.total_size)})"
    return string


def percent_of(size_of: int, size_to: int) -> str:
    return f"{round(size_to / size_of * 100):>03}%"


@dataclass(kw_only=True)
class EpubOperationResult(OperationResult):
    """Book outcome without live resources, shared by legacy and context recipes.

    details describes the final outcome. analytics contains unsaved table instances for
    parent-side persistence. The legacy recorder still handles image_results;
    it does not yet persist the new analytics list.
    Setup failures retain input_path with original_epub=None; no metadata is invented.
    """

    original_epub: EpubInfo | None = None
    input_path: Path | None = None
    details: str = ""
    new_epub: EpubInfo | None = None
    image_results: list[ImageOptimizationResult] = field(default_factory=list)
    analytics: list[SQLModel] = field(default_factory=list)

    def report(self):
        original_epub = self.original_epub

        path = original_epub.path if original_epub else self.input_path
        size = byte_size_to_mb_str(original_epub.path_size) if original_epub else "unknown size"
        report = f"{path if path is not None else 'unknown input'} {size}"
        if self.success:
            report += "\nOPERATION RESULT: SUCCESS"
        if self.skip:
            report += f"\nOPERATION RESULT: SKIP {EpubSkipReason(self.skip).name}"
        if self.error:
            report += f"\nOPERATION RESULT: ERROR {EpubErrorReason(self.error).name}"

        if self.details:
            report += f"\n{self.details}"
        print_success(report)

        if self.success:
            original_epub = require(original_epub)
            new_epub = require(self.new_epub)
            o_size = original_epub.total.compress_size
            n_size = new_epub.total.compress_size
            size_reduction = o_size - n_size

            def make_dict(
                name: str,
                original_index_info: IndexInfo,
                new_index_info: IndexInfo,
            ) -> dict:
                count = str(original_index_info.count)
                if new_index_info.count != original_index_info.count:
                    count += f" -> {new_index_info.count}"

                local_size_reduction = original_index_info.compress_size - new_index_info.compress_size

                return {
                    "name": name,
                    "count": count,
                    "original_size": format_sizes(original_index_info),
                    "new_size": format_sizes(new_index_info),
                    "reduction (%)": percent_of(original_index_info.compress_size, new_index_info.compress_size),
                    "reduction (MB)": byte_size_to_mb_str(local_size_reduction),
                    "% of total": f"{percent_of(o_size, original_index_info.compress_size)} -> {percent_of(n_size, new_index_info.compress_size)}",
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

    def short_report(self):
        original_epub = self.original_epub
        mb_size = byte_size_to_mb_str(original_epub.path_size) if original_epub else "unknown size"
        path = original_epub.path if original_epub else self.input_path
        ori_path = Path(path).name if path is not None else "unknown input"
        if self.error:
            print_error(f"{mb_size} ERROR {EpubErrorReason(self.error).name} {ori_path!s}")
        if self.skip:
            print_success(f"{mb_size} SKIPPED {EpubSkipReason(self.skip).name} {ori_path!s}")
        if self.success:
            original_epub = require(original_epub)
            new_epub = require(self.new_epub)
            percent = percent_of(original_epub.total.compress_size, new_epub.total.compress_size)
            print_success(f"{mb_size:>09} REDUCED TO {percent} {ori_path!s}")
