# Plans:

## Read epub info

```python
epub = EPUB("1.epub")
epub.validate()  # bool, confirms mimetype, before first action, not during initialization.
epub.package_document.metadata
epub.package_document.metadata.title
epub.package_document.metadata.author
epub.metadata  # proxy to epub.package.metadata
epub.metadata.add()
epub.metadata.add_dc()
epub.metadata.add_item()
epub.package_document.manifest
epub.package_document.spine

```