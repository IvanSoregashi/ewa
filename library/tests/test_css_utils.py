from library.utils_css import cleanup_font_block, cleanup_panda_line

css_stylesheet_bytes = b""".calibre {
    display: block;
    font-family: "SerenePanda", serif;
    font-size: 1em;
    padding-left: 0;
    padding-right: 0;
    text-align: left;
    word-break: keep-all;
    margin: 0 5pt
    }
.calibre1 {
    display: block;
    font-size: 2em;
    font-weight: bold;
    line-height: 1.2;
    text-align: center;
    word-break: keep-all;
    margin: 0.67em 0
    }
.calibre2 {
    display: block;
    height: 1em;
    margin: 0;
    border: currentColor none 0
    }
.calibre3 {
    display: block;
    height: 0;
    margin: 0;
    border: currentColor none 0
    }
.calibre4 {
    font-style: italic
    }
.calibre5 {
    font-weight: bold
    }
.calibre6 {
    text-decoration: underline
    }
.calibre7 {
    display: block;
    height: auto;
    max-height: 100%;
    max-width: 100%;
    width: auto;
    margin: 0 auto;
    padding: 0
    }
.calibre8 {
    display: block;
    font-family: "SerenePanda";
    font-size: 1em;
    text-align: center;
    margin: 0 5pt;
    padding: 0
    }
.calibre9 {
    display: block
    }
.calibre10 {
  display: block;
  font-family: "SerenePanda" !important;
  font-size: 1em;
  text-align: center;
  margin: 0 5pt;
  padding: 0
  }
"""

expected_css_stylesheet_bytes = b""".calibre {
    display: block;
    font-family: serif;
    font-size: 1em;
    padding-left: 0;
    padding-right: 0;
    text-align: left;
    word-break: keep-all;
    margin: 0 5pt
    }
.calibre1 {
    display: block;
    font-size: 2em;
    font-weight: bold;
    line-height: 1.2;
    text-align: center;
    word-break: keep-all;
    margin: 0.67em 0
    }
.calibre2 {
    display: block;
    height: 1em;
    margin: 0;
    border: currentColor none 0
    }
.calibre3 {
    display: block;
    height: 0;
    margin: 0;
    border: currentColor none 0
    }
.calibre4 {
    font-style: italic
    }
.calibre5 {
    font-weight: bold
    }
.calibre6 {
    text-decoration: underline
    }
.calibre7 {
    display: block;
    height: auto;
    max-height: 100%;
    max-width: 100%;
    width: auto;
    margin: 0 auto;
    padding: 0
    }
.calibre8 {
    display: block;
    font-family: serif;
    font-size: 1em;
    text-align: center;
    margin: 0 5pt;
    padding: 0
    }
.calibre9 {
    display: block
    }
.calibre10 {
  display: block;
  font-family: serif !important;
  font-size: 1em;
  text-align: center;
  margin: 0 5pt;
  padding: 0
  }
"""

css_page_style_bytes = b"""@page {
  margin-bottom: 5pt;
  margin-top: 5pt;
}
@font-face {
  font-family: "SerenePanda";
  src: url(serenepanda.ttf);
  font-style: normal;
  font-weight: normal;
  text-rendering: optimizeLegibility;
}
"""


expected_css_page_style_bytes = b"""@page {
  margin-bottom: 5pt;
  margin-top: 5pt;
}

"""


def test_replace_lines():
    assert cleanup_panda_line(css_stylesheet_bytes) == expected_css_stylesheet_bytes


def test_cleanup_panda_block():
    assert cleanup_font_block(css_page_style_bytes) == expected_css_page_style_bytes
