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
