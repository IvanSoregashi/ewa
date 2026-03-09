from enum import StrEnum

class XMLNamespace(StrEnum):
    XML = "http://www.w3.org/XML/1998/namespace"
    XSI = "http://www.w3.org/2001/XMLSchema-instance"
    XHTML = "http://www.w3.org/1999/xhtml"
    EPUB = "http://www.idpf.org/2007/ops"
    OPF = "http://www.idpf.org/2007/opf"
    DC = "http://purl.org/dc/elements/1.1/"
    NCX = "http://www.daisy.org/z3986/2005/ncx/"
    CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"

class NamespacePrefix(StrEnum):
    XML = "xml"
    XSI = "xsi"
    XHTML = "xhtml"
    EPUB = "epub"
    OPF = "opf"
    DC = "dc"
    NCX = "ncx"
    CONTAINER = "container"

OPF_NSMAP = {
    NamespacePrefix.OPF: XMLNamespace.OPF,
    NamespacePrefix.DC: XMLNamespace.DC,
    NamespacePrefix.XSI: XMLNamespace.XSI,
    NamespacePrefix.XML: XMLNamespace.XML,
    "": XMLNamespace.OPF,
}

NCX_NSMAP = {
    "": XMLNamespace.NCX,
    NamespacePrefix.XML: XMLNamespace.XML,
}

NAV_NSMAP = {
    "": XMLNamespace.XHTML,
    NamespacePrefix.EPUB: XMLNamespace.EPUB,
    NamespacePrefix.XML: XMLNamespace.XML,
}

NAMESPACES = {
    "XML": XMLNamespace.XML,
    "EPUB": XMLNamespace.EPUB,
    "DAISY": XMLNamespace.NCX,
    "OPF": XMLNamespace.OPF,
    "CONTAINERNS": XMLNamespace.CONTAINER,
    "DC": XMLNamespace.DC,
    "XHTML": XMLNamespace.XHTML,
}
