from library.epub.resources import Resource
from library.utils_css import cleanup_font_block, cleanup_panda_line


def de_panda_css_resource(res: Resource) -> None:
    old_content = res.content
    if "page_styles" in res.info.filename:
        res.content = cleanup_font_block(old_content)
    else:
        res.content = cleanup_panda_line(old_content)

    if res.content != old_content:
        res.is_modified = True
