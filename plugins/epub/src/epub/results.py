"""Epub optimization result: the dataclass returned by the conversion pipeline
and persisted by the analytics recipes."""

from dataclasses import dataclass, field

from ewa.cli.print_table import print_table_from_dicts
from ewa.ui import print_success
from library.analytics import OperationResult
from library.asserts import require
from library.epub.epub import EpubInfo
from library.epub.errors import EpubSkipReason, EpubErrorReason
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
class EpubOptimizationResult(OperationResult):
    original_epub: EpubInfo
    new_epub: EpubInfo | None = None
    image_results: list[ImageOptimizationResult] = field(default_factory=list)

    def report(self):
        original_epub = self.original_epub

        report = f"{str(original_epub.path)!s} {byte_size_to_mb_str(original_epub.path_size)}"
        if self.success:
            report += "\nOPERATION RESULT: SUCCESS"
        if self.skip:
            report += f"\nOPERATION RESULT: SKIP {EpubSkipReason(self.skip).name}"
        if self.error:
            report += f"\nOPERATION RESULT: ERROR {EpubErrorReason(self.error).name}"

        print_success(report)

        if self.success:
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
                original_index_info=self.original_epub.total,
                new_index_info=new_epub.total,
            )
            images = make_dict(
                name="images",
                original_index_info=self.original_epub.images,
                new_index_info=new_epub.images,
            )
            chapters = make_dict(
                name="chapters",
                original_index_info=self.original_epub.htmls,
                new_index_info=new_epub.htmls,
            )
            fonts = make_dict(
                name="fonts",
                original_index_info=self.original_epub.fonts,
                new_index_info=new_epub.fonts,
            )
            print_table_from_dicts(title="wow stats", dicts=[total, images, chapters, fonts])
