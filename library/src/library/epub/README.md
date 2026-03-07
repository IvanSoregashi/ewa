# Plans:

## Read epub info
```python
epub = EPUB("1.epub")
epub.validate()  # bool, confirms mimetype, before first action, not during initialization.
epub.package.metadata
epub.package.metadata.title
epub.package.metadata.author
epub.metadata # proxy to epub.package.metadata
epub.metadata.add()
epub.metadata.add_dc()
epub.metadata.add_item()
epub.package.manifest
epub.package.spine

```