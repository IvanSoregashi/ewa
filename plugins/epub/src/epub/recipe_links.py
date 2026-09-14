"""Diagnostic coverage of existing URL-attribute and CSS url() parsers."""

import logging
from collections import Counter
from pathlib import PurePosixPath

from lxml import etree, html

from library.epub.epub import EPUB
from library.epub.package_urls import local_target
from library.utils_css import parse_css_urls

logger = logging.getLogger(__name__)
LINKS = etree.XPath(
    "//@*[local-name()='href' or local-name()='src' or local-name()='poster' "
    "or local-name()='data' or local-name()='full-path']"
)
MARKUP = {".opf", ".ncx", ".xml", ".xhtml", ".html", ".htm", ".svg", ".smil"}


def log_links(epub: EPUB) -> dict[str, int]:
    """Parse stored resource bytes and log local URL resolution without rewriting.

    Coverage: markup href/src/poster/data/full-path attributes, CSS url(), and
    inline styles. Check target files, not fragment IDs or remote availability.
    Does not validate spine IDREFs, srcset, CSS @import strings, or script URLs.
    Flush pending package model edits first to include them in this inspection.
    Base overrides are reported unsupported rather than resolved incorrectly.
    """
    counts = Counter(documents=0, local=0, external=0, missing=0, invalid=0, errors=0, recovered=0, unsupported=0)
    with epub.keep_open():
        for resource in epub.resources:
            suffix = PurePosixPath(resource.filename).suffix.lower()
            if suffix not in MARKUP and suffix != ".css":
                continue
            counts["documents"] += 1
            try:
                if suffix == ".css":
                    links = [(resource.filename, url) for url in parse_css_urls(resource.content)]
                else:
                    try:
                        tree = etree.fromstring(
                            resource.content, etree.XMLParser(resolve_entities=False, no_network=True)
                        )
                    except etree.XMLSyntaxError:
                        if suffix not in {".html", ".htm", ".xhtml"}:
                            raise
                        tree = html.document_fromstring(resource.content)
                        counts["recovered"] += 1
                        logger.warning("%s: strict XML failed; inspecting recovered HTML", resource.filename)
                    if tree.xpath(
                        "//@xml:base | //*[local-name()='base']/@href",
                        namespaces={"xml": "http://www.w3.org/XML/1998/namespace"},
                    ):
                        counts["unsupported"] += 1
                        logger.warning("%s: base override unsupported; skipping document", resource.filename)
                        continue
                    links = [
                        (
                            ""
                            if resource.filename == "META-INF/container.xml" and url.attrname == "full-path"
                            else resource.filename,
                            str(url),
                        )
                        for url in LINKS(tree)
                    ]
                    for style in tree.xpath("//@style | //*[local-name()='style']/text()"):
                        links.extend((resource.filename, url) for url in parse_css_urls(str(style).encode("utf-8")))
            except Exception as error:
                counts["errors"] += 1
                logger.warning("%s: cannot parse links: %s", resource.filename, error)
                continue

            for base, url in links:
                try:
                    target = local_target(base, url)
                except ValueError as error:
                    counts["invalid"] += 1
                    logger.warning("%s: invalid URL %r: %s", resource.filename, url, error)
                    continue
                if target is None:
                    counts["external"] += 1
                    logger.debug("%s: external URL %r (not fetched)", resource.filename, url)
                else:
                    path, _ = target
                    target_resource = epub.resources.by_path(path)
                    if target_resource is None or target_resource.is_deleted or target_resource.info.is_dir():
                        counts["missing"] += 1
                        logger.warning("%s: %r -> missing file %r", resource.filename, url, path)
                    else:
                        counts["local"] += 1
                        logger.debug("%s: %r -> %r OK (fragment not checked)", resource.filename, url, path)
    clean = counts["documents"] > 0 and not any(
        counts[k] for k in ("missing", "invalid", "errors", "recovered", "unsupported")
    )
    logger.info(
        "%s link check: %s; %s. Scope: URL attributes and CSS url(); fragments, scripts, srcset and CSS @import strings not validated.",
        epub,
        "all inspected local URLs resolved" if clean else "incomplete or issues found",
        dict(counts),
    )
    return dict(counts)
