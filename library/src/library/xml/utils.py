import re
import logging
from pathlib import Path
from typing import Literal, overload, Any
from collections import Counter
from lxml import etree

logger = logging.getLogger(__name__)


@overload
def prettify(document: bytes, encoding: Literal["unicode"]) -> str: ...


@overload
def prettify(document: bytes) -> bytes: ...


def prettify(document: bytes, encoding: Literal["unicode"] | None = None) -> bytes | str:
    logger.debug("prettify util is called.")
    tree = etree_from_bytes(document)
    return etree.tostring(tree, pretty_print=True, encoding=encoding)


def fix_invalid_ampersands(content: str) -> str:
    """Fixes raw ampersands that are not part of a valid XML entity."""
    logger.warning("Invalid ampersands in xml")
    return re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#x?|#)", "&amp;", content)


def fix_opf_namespace(content: str) -> str:
    """Add opf namespace to the package tag"""
    logger.warning("Lacking OPF namespace definition in xml")
    return re.sub(r"(<package[^>]+)>", r'\1 xmlns:opf="http://www.idpf.org/2007/opf">', content, count=1)


def etree_from_bytes(xml_bytes: bytes) -> etree._Element:
    parser = etree.XMLParser(remove_blank_text=True, remove_comments=True)
    for _ in range(3):
        try:
            return etree.fromstring(xml_bytes, parser)
        except etree.XMLSyntaxError as e:
            error_msg = str(e)
            try:
                text = xml_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = xml_bytes.decode("latin-1")

            text = fix_invalid_ampersands(text) if "xmlParseEntityRef: " in error_msg else text
            text = fix_opf_namespace(text) if "Namespace prefix opf" in error_msg else text
            xml_bytes = text.encode("utf-8")
    return etree.fromstring(xml_bytes, parser)


def get_facts(
    content: bytes,
    unordered_tags: set[str] | None = None,
    ignore_xmlns: bool = False,
) -> Counter:
    """
    Extracts semantic facts from XML bytes for comparison.
    Used for roundtrip verification.
    """
    if unordered_tags is None:
        unordered_tags = set()
    try:
        root = etree_from_bytes(xml_bytes=content)
    except Exception as e:
        logger.error(f"get_facts parsing failed with error: {e}")
        return Counter()

    facts = []

    def walk(elem, path):
        q = etree.QName(elem)
        tag = f"{{{q.namespace}}}{q.localname}" if q.namespace else q.localname
        current_path = f"{path}/{tag}"

        for k, v in elem.attrib.items():
            aq = etree.QName(k)
            full_k = f"{{{aq.namespace}}}{aq.localname}" if aq.namespace else aq.localname
            if ignore_xmlns and (aq.localname == "xmlns" or k.startswith("xmlns:")):
                continue
            facts.append(f"{current_path} @{full_k}={v}")

        text = (elem.text or "").strip()
        if text:
            facts.append(f"{current_path} TEXT={text}")

        local_name = q.localname
        is_unordered = local_name in unordered_tags

        for i, child in enumerate(elem):
            idx = f"[{i}]" if not is_unordered else ""
            walk(child, f"{current_path}{idx}")

    walk(root, "")
    facts_counter = Counter(facts)
    return facts_counter


def compare_roundtrip(
    model_cls: Any,  # Can be Pydantic XML model or Antigravity model
    path: str,
    show_diff: bool = True,
    unordered_tags: set[str] | None = None,
    ignore_xmlns: bool | None = None,
) -> bool:
    if unordered_tags is None:
        unordered_tags = getattr(model_cls, "__unordered_tags__", set())

    # pydantic_xml requires to_xml_bytes, antigravity requires to_xml
    # we'll detect or pass method name if needed, but let's try to standardize
    if ignore_xmlns is None:
        ignore_xmlns = getattr(model_cls, "__ignore_xmlns__", False)

    original_bytes = Path(path).read_bytes()

    try:
        original_facts = get_facts(original_bytes, unordered_tags, ignore_xmlns=ignore_xmlns)

        # Detect if it's pydantic-xml or antigravity
        # Antigravity models usually have from_xml and to_xml
        # Pydantic models also have from_xml, but we added to_xml_bytes in base.py

        exported_bytes = model_cls.from_xml_bytes(original_bytes).to_xml_bytes()

        exported_facts = get_facts(exported_bytes, unordered_tags, ignore_xmlns=ignore_xmlns)

        if original_facts == exported_facts:
            return True

        if show_diff:
            print(f"\n--- SEMANTIC DEVIATIONS for {path} ---")
            lost = original_facts - exported_facts
            added = exported_facts - original_facts
            if lost:
                print("LOST INFO:")
                for fact, count in sorted(lost.items()):
                    print(f"  - {fact}" + (f" ({count}x)" if count > 1 else ""))
            if added:
                print("ADDED INFO:")
                for fact, count in sorted(added.items()):
                    print(f"  + {fact}" + (f" ({count}x)" if count > 1 else ""))
            print("-----------------------")
        return False
    except Exception as e:
        if show_diff:
            print(f"Error comparing {path}: {e}")
        return False
