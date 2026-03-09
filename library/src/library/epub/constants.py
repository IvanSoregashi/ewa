# Namespaces
XML_NS = "http://www.w3.org/XML/1998/namespace"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XHTML_NS = "http://www.w3.org/1999/xhtml"

EPUB_NS = "http://www.idpf.org/2007/ops"
OPF_NS = "http://www.idpf.org/2007/opf"

DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

OPF_NSMAP = {
    "opf": OPF_NS,
    "dc": DC_NS,
    "xsi": XSI_NS,
    "xml": XML_NS,
    "": OPF_NS,
}

NCX_NSMAP = {
    "": NCX_NS,
    "xml": XML_NS,
}

NAV_NSMAP = {
    "": XHTML_NS,
    "epub": EPUB_NS,
    "xml": XML_NS,
}

NAMESPACES = {
    "XML": XML_NS,
    "EPUB": EPUB_NS,
    "DAISY": NCX_NS,
    "OPF": OPF_NS,
    "CONTAINERNS": CONTAINER_NS,
    "DC": DC_NS,
    "XHTML": XHTML_NS,
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
