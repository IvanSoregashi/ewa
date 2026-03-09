import sys
from pathlib import Path
from lxml import etree

# Add src to path so we can import library
sys.path.append(str(Path(__file__).parent.parent / "src"))

from library.xml.utils import etree_from_bytes
from library.epub.xml_models.opf_model import PackageDocument as PydanticPackageDocument

def main():
    samples_dir = Path(__file__).parent.parent / "tests" / "samples" / "opf"
    for opf_path in samples_dir.glob("*.opf"):
        if ".formatted.opf" in opf_path.name:
            continue
        
        print(f"Generating formatted versions for {opf_path.name}...")
        original_bytes = opf_path.read_bytes()
        
        # 1. Custom/Raw formatted (lxml pretty print)
        try:
            tree = etree_from_bytes(original_bytes)
            custom_formatted = etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding="utf-8")
            opf_path.with_suffix(".custom.formatted.opf").write_bytes(custom_formatted)
        except Exception as e:
            print(f"  Failed Custom format for {opf_path.name}: {e}")

        # 2. Pydantic formatted (Pydantic model roundtrip)
        try:
            doc = PydanticPackageDocument.from_xml_bytes(original_bytes)
            pydantic_formatted = doc.to_xml_bytes(pretty_print=True)
            opf_path.with_suffix(".pydantic.formatted.opf").write_bytes(pydantic_formatted)
        except Exception as e:
            print(f"  Failed Pydantic format for {opf_path.name}: {e}")

if __name__ == "__main__":
    main()
