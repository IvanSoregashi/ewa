from zipfile import ZipFile
from pathlib import PurePosixPath
from lxml import etree

# ---------------------------
# Public entry point
# ---------------------------


def parse_epub_xml(zipfile: ZipFile) -> dict | None:
    if not confirm_mimetype(zipfile):
        return None

    opf_path = parse_container_xml(zipfile)
    if not opf_path:
        return None

    opf_data = parse_content_opf(zipfile, opf_path)

    if opf_data.get("ncx_path"):
        parse_toc_ncx(zipfile, opf_data)

    return {
        "metadata": opf_data["metadata"],
        "data": opf_data["data"],
    }


# ---------------------------
# Required EPUB files
# ---------------------------


def confirm_mimetype(zipfile: ZipFile) -> bool:
    try:
        with zipfile.open("mimetype") as f:
            return f.read().decode("ascii").strip() == "application/epub+zip"
    except KeyError:
        return False


def parse_container_xml(zipfile: ZipFile) -> str | None:
    try:
        xml = zipfile.read("META-INF/container.xml")
    except KeyError:
        return None

    root = etree.fromstring(xml)
    result = root.xpath("//c:rootfile/@full-path", namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"})
    return result[0] if result else None


# ---------------------------
# OPF parsing
# ---------------------------


def parse_content_opf(zipfile: ZipFile, opf_path: str) -> dict:
    xml = zipfile.read(opf_path)
    root = etree.fromstring(xml)

    ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
    base_path = PurePosixPath(opf_path).parent

    # ---- metadata ----
    metadata: dict[str, str | list[str]] = {}

    for elem in root.xpath("//dc:*", namespaces=ns):
        tag = etree.QName(elem).localname
        metadata.setdefault(tag, []).append(elem.text)

    metadata = {k: v[0] if len(v) == 1 else v for k, v in metadata.items()}

    # ---- manifest ----
    manifest = {}
    data = {}
    ncx_path = None

    for item in root.xpath("//opf:manifest/opf:item", namespaces=ns):
        item_id = item.get("id")
        href = str(base_path / item.get("href"))
        media_type = item.get("media-type")

        manifest[item_id] = {"href": href, "media_type": media_type}
        data[href] = {"item_id": item_id, "media_type": media_type}

        if media_type == "application/x-dtbncx+xml":
            ncx_path = href

    # ---- spine ----
    spine = [item.get("idref") for item in root.xpath("//opf:spine/opf:itemref", namespaces=ns)]

    return {
        "metadata": metadata,
        "manifest": manifest,
        "data": data,
        "spine": spine,
        "ncx_path": ncx_path,
    }


# ---------------------------
# NCX TOC (EPUB 2)
# ---------------------------


def parse_toc_ncx(zipfile: ZipFile, opf_data: dict):
    ncx_path = opf_data["ncx_path"]
    data = opf_data["data"]
    try:
        xml = zipfile.read(ncx_path)
    except KeyError:
        return

    root = etree.fromstring(xml)
    ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}

    for navpoint in root.xpath("//ncx:navPoint", namespaces=ns):
        label = navpoint.xpath(".//ncx:text/text()", namespaces=ns)
        src = navpoint.xpath(".//ncx:content/@src", namespaces=ns)

        if src and src[0] in data:
            data[src[0]]["chapter"] = label[0] if label else None


# ---------------------------
# CHAPTER
# ---------------------------

