from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from library.utils_xhtml import cleanup_calibre_formatting, cleanup_calibre_formatting_lxml


SAMPLES_DIR = Path(__file__).parent / "samples" / "chapters"
CHAPTER_FILES = sorted(SAMPLES_DIR.glob("*.html"))


@pytest.fixture(params=CHAPTER_FILES, ids=lambda f: f.name)
def chapter_html(request):
    return request.param.read_text(encoding="utf-8")


def get_text_words(html: str) -> set:
    soup = BeautifulSoup(html, "html.parser")
    if soup.body:
        return set(soup.body.get_text().strip().split())
    return set()


def get_text_normalized(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.body:
        text = soup.body.get_text()
        return " ".join(text.split())
    return ""


def get_structure_comparison(html1: str, html2: str) -> tuple[bool, list]:
    soup1 = BeautifulSoup(html1, "html.parser")
    soup2 = BeautifulSoup(html2, "html.parser")

    if not soup1.body or not soup2.body:
        return soup1.body is soup2.body, []

    def extract_structure(element, depth=0):
        result = []
        for child in element.children:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    result.append(("text", depth, text[:50]))
            elif child.name:
                tag = child.name.lower()
                if tag in ("p", "br"):
                    continue
                attrs = tuple(sorted((k, v) for k, v in child.attrs.items() if k != "class"))
                result.append((tag, depth, attrs))
                result.extend(extract_structure(child, depth + 1))
        return result

    struct1 = extract_structure(soup1.body)
    struct2 = extract_structure(soup2.body)

    if struct1 == struct2:
        return True, []

    diff = []
    max_len = max(len(struct1), len(struct2))
    for i in range(max_len):
        s1 = struct1[i] if i < len(struct1) else None
        s2 = struct2[i] if i < len(struct2) else None
        if s1 != s2:
            diff.append(f"Pos {i}: {s1} vs {s2}")
    return False, diff[:10]


def has_empty_calibre_tags(soup: BeautifulSoup) -> bool:
    if not soup.body:
        return False
    for p in soup.body.find_all("p"):
        classes = p.get("class", [])
        if any("calibre" in c for c in classes):
            text = p.get_text().strip()
            if not text or text == "\xa0":
                return True
    return False


def has_naked_text(soup: BeautifulSoup) -> bool:
    if not soup.body:
        return False
    for child in soup.body.children:
        if child.name is None:
            text = child.strip() if isinstance(child, str) else ""
            if text and not _is_whitespace_only(text):
                return True
    return False


def _is_whitespace_only(text: str) -> bool:
    return not text or text.isspace()


def is_valid_html(html: str) -> bool:
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.body is not None
    except Exception:
        return False


def get_text_normalized(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.body:
        text = soup.body.get_text()
        return " ".join(text.split())
    return ""


class TestCleanupCalibreFormattingLxml:
    def test_lxml_matches_bs4(self, chapter_html):
        soup = BeautifulSoup(chapter_html, "html.parser")
        bs4_result = cleanup_calibre_formatting(soup)

        lxml_result = cleanup_calibre_formatting_lxml(chapter_html.encode("utf-8"))

        bs4_text = get_text_normalized(str(bs4_result))
        lxml_text = get_text_normalized(lxml_result.decode("utf-8"))

        assert bs4_text == lxml_text, f"Text mismatch"

    def test_lxml_structure_matches_bs4(self, chapter_html):
        soup = BeautifulSoup(chapter_html, "html.parser")
        bs4_result = cleanup_calibre_formatting(soup)

        lxml_result = cleanup_calibre_formatting_lxml(chapter_html.encode("utf-8"))

        equal, diff = get_structure_comparison(str(bs4_result), lxml_result.decode("utf-8"))
        assert equal, f"Structure mismatch: {diff}"

    def test_lxml_text_preserved(self, chapter_html):
        result = cleanup_calibre_formatting_lxml(chapter_html.encode("utf-8"))
        result_soup = BeautifulSoup(result, "html.parser")
        old_text = get_text_normalized(chapter_html)
        new_text = get_text_normalized(str(result_soup))
        assert old_text == new_text, "Text content changed after cleanup"

    def test_lxml_no_empty_calibre_tags(self, chapter_html):
        result = cleanup_calibre_formatting_lxml(chapter_html.encode("utf-8"))
        result_soup = BeautifulSoup(result, "html.parser")
        assert not has_empty_calibre_tags(result_soup), "Empty calibre tags still present"

    def test_lxml_valid_html_output(self, chapter_html):
        result = cleanup_calibre_formatting_lxml(chapter_html.encode("utf-8"))
        assert is_valid_html(result.decode("utf-8")), "Output is not valid HTML"


class TestCleanupCalibreFormatting:
    def test_text_preserved(self, chapter_html):
        old_text = get_text_normalized(chapter_html)
        soup = BeautifulSoup(chapter_html, "html.parser")
        result = cleanup_calibre_formatting(soup)
        new_text = get_text_normalized(str(result))
        assert old_text == new_text, "Text content changed after cleanup"

    def test_no_empty_calibre_tags(self, chapter_html):
        soup = BeautifulSoup(chapter_html, "html.parser")
        result = cleanup_calibre_formatting(soup)
        result_soup = BeautifulSoup(str(result), "html.parser")
        assert not has_empty_calibre_tags(result_soup), "Empty calibre tags still present"

    def test_no_naked_text(self, chapter_html):
        soup = BeautifulSoup(chapter_html, "html.parser")
        result = cleanup_calibre_formatting(soup)
        result_soup = BeautifulSoup(str(result), "html.parser")
        assert not has_naked_text(result_soup), "Naked text still present in body"

    def test_valid_html_output(self, chapter_html):
        soup = BeautifulSoup(chapter_html, "html.parser")
        result = cleanup_calibre_formatting(soup)
        assert is_valid_html(str(result)), "Output is not valid HTML"

    def test_pretty_printed(self, chapter_html):
        soup = BeautifulSoup(chapter_html, "html.parser")
        result = cleanup_calibre_formatting(soup)
        result_str = str(result)
        assert "\n" in result_str, "Output is not pretty printed"
