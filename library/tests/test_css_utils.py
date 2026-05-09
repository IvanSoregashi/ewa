from library.epub.utils_css import parse_css_urls, replace_css_url, _delete_css_block

css_bytes = b"""@page {
    margin-bottom: 5pt;
    margin-top: 5pt
    }
@font-face {
    font-family: "OriginalFont";
    panose-1: 2 2 6 3 5 4 5 2 3 4;
    src: url(fonts/OriginalFont.ttf)
    }
"""

css_bytes_quotes = b"""@page {
    margin-bottom: 5pt;
    margin-top: 5pt
    }
@font-face {
    font-family: "OriginalFont";
    panose-1: 2 2 6 3 5 4 5 2 3 4;
    src: url("fonts/OriginalFont.ttf")
    }
"""

css2_bytes = b"""@page {
    margin-bottom: 5pt;
    margin-top: 5pt
    }
@font-face {
    font-family: "OriginalFont";
    panose-1: 2 2 6 3 5 4 5 2 3 4;
    src: url(fonts/OriginalFont.ttf)
    }
@font-face {
    font-family: "OriginalFont";
    panose-1: 2 2 6 3 5 4 5 2 3 4;
    src: url(/home/user/ReplacedFont.ttf)
    }
"""


css_bytes_replaced = b"""@page {
    margin-bottom: 5pt;
    margin-top: 5pt
    }
@font-face {
    font-family: "OriginalFont";
    panose-1: 2 2 6 3 5 4 5 2 3 4;
    src: url(/home/user/ReplacedFont.ttf)
    }
"""

css_bytes_replaced_quotes = b"""@page {
    margin-bottom: 5pt;
    margin-top: 5pt
    }
@font-face {
    font-family: "OriginalFont";
    panose-1: 2 2 6 3 5 4 5 2 3 4;
    src: url("/home/user/ReplacedFont.ttf")
    }
"""

css_bytes_deleted = b"""@page {
    margin-bottom: 5pt;
    margin-top: 5pt
    }
"""


def test_get_urls():
    assert list(parse_css_urls(css_bytes)) == ["fonts/OriginalFont.ttf"]
    assert list(parse_css_urls(css_bytes_quotes)) == ["fonts/OriginalFont.ttf"]
    assert list(parse_css_urls(css2_bytes)) == ["fonts/OriginalFont.ttf", "/home/user/ReplacedFont.ttf"]
    assert list(parse_css_urls(css_bytes_replaced)) == ["/home/user/ReplacedFont.ttf"]


def test_replace_url():
    assert replace_css_url(css_bytes, "fonts/OriginalFont.ttf", "/home/user/ReplacedFont.ttf") == css_bytes_replaced
    assert (
        replace_css_url(css_bytes_quotes, "fonts/OriginalFont.ttf", "/home/user/ReplacedFont.ttf")
        == css_bytes_replaced_quotes
    )
    assert replace_css_url(css2_bytes, "/user/ReplacedFont", "OriginalFont.ttf") == css2_bytes


def test_delete_block_by_url():
    assert _delete_css_block(css2_bytes, "fonts/OriginalFont.ttf") == css_bytes_replaced
    assert _delete_css_block(css2_bytes, "/home/user/ReplacedFont.ttf") == css_bytes
    assert (
        _delete_css_block(_delete_css_block(css2_bytes, "fonts/OriginalFont.ttf"), "/home/user/ReplacedFont.ttf")
        == css_bytes_deleted
    )
    assert _delete_css_block(css_bytes_quotes, "fonts/OriginalFont.ttf") == css_bytes_deleted
    assert _delete_css_block(css_bytes_replaced_quotes, "/home/user/ReplacedFont.ttf") == css_bytes_deleted
