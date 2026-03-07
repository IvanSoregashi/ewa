NAMESPACES = {
    "XML": "http://www.w3.org/XML/1998/namespace",
    "EPUB": "http://www.idpf.org/2007/ops",
    "DAISY": "http://www.daisy.org/z3986/2005/ncx/",
    "OPF": "http://www.idpf.org/2007/opf",
    "CONTAINERNS": "urn:oasis:names:tc:opendocument:xmlns:container",
    "DC": "http://purl.org/dc/elements/1.1/",
    "XHTML": "http://www.w3.org/1999/xhtml",
}

# XML Templates

CONTAINER_PATH = "META-INF/container.xml"

CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile media-type="application/oebps-package+xml" full-path="%(folder_name)s/content.opf"/>
  </rootfiles>
</container>
"""

NCX_XML = (
    rb'<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">'
    rb'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" />'
)

NAV_XML = (
    rb'<?xml version="1.0" encoding="utf-8"?>'
    rb"<!DOCTYPE html>"
    rb'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"/>'
)

CHAPTER_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    rb"<!DOCTYPE html>"
    rb'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#">'
    rb"</html>"
)

COVER_XML = rb"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
  <head></head>
  <body>
    <img src="" alt="" style="height:100%; text-align:center" />
  </body>
</html>"""


IMAGE_MEDIA_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/svg+xml"]
