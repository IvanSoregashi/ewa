from library.epub.resources import Resource
from library.utils_css import cleanup_font_block, cleanup_panda_line


def de_panda_css_resource(resource: Resource) -> None:
    old_content = resource.content
    if "page_styles" in resource.info.filename:
        resource.content = cleanup_font_block(old_content)
    else:
        resource.content = cleanup_panda_line(old_content)
