from pathlib import Path

import pytest

from epub.results import EpubOperationResult, percent_of
from library.epub.epub import EpubInfo
from library.epub.resources import IndexInfo


@pytest.mark.parametrize(
    "original, current, expected",
    [(100, 50, "050%"), (100, 0, "000%"), (0, 0, "N/A"), (0, 50, "N/A"), (None, 50, "N/A"), (50, None, "N/A")],
)
def test_percent_of_handles_unknown_and_zero_baselines(original, current, expected):
    assert percent_of(original, current).strip() == expected


@pytest.mark.parametrize("total", [None, IndexInfo(0, 0, 0), IndexInfo(2, 100, 50)])
def test_success_reports_allow_missing_categories_and_unchanged_sizes(total, capsys):
    original = EpubInfo(path=Path("input.epub"), path_size=100, total=total)
    output = EpubInfo(path=Path("output.epub"), path_size=100, total=total)
    result = EpubOperationResult(success=True, original_epub=original, new_epub=output)
    result.report()
    result.short_report()
    report = capsys.readouterr().out
    assert "SUCCESS" in report
    assert "N/A" in report


def test_report_preserves_available_statistics(monkeypatch):
    rows = []
    monkeypatch.setattr("epub.results.print_table_from_dicts", lambda title, dicts: rows.extend(dicts))
    original = EpubInfo(path=Path("input.epub"), path_size=100, total=IndexInfo(2, 200, 100))
    output = EpubInfo(path=Path("output.epub"), path_size=50, total=IndexInfo(1, 100, 50))
    result = EpubOperationResult(success=True, original_epub=original, new_epub=output)
    result.report()
    assert rows[0]["count"] == "2 -> 1"
    assert rows[0]["reduction (%)"].strip() == "050%"
    assert rows[1]["original_size"] == "N/A"
