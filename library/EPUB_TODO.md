# EPUB architecture TODO

## Agreed next steps

- [x] Fix Source exception cleanup: a failed ZIP session must close and reset its handle, and subsequent reads must work.
- [x] Fix single-file ZIP extraction: match DirectorySource for existing-directory and exact-filename destinations, preserve timestamps, and avoid duplicated member paths. Add synthetic regression tests.
- [ ] Prototype a package entity associating the OPF resource with its parsed document. Review concrete code before expanding the design.
- [ ] Decide where container discovery and updates belong when introducing the package entity; package versus EPUB ownership is still open.
- [ ] Justify any package facades and a separate EpubManifest through useful editing methods. Avoid wrappers that merely shorten attribute access.
- [ ] Settle resource deletion and collection ownership on one consistent model. Review the implementation before adopting wider ResourceIndex API changes; membership versus is_deleted is currently redundant.
- [ ] Address manifest index consistency and synchronization during add/remove/edit, together with the ownership decision. Decide how filtered collections behave.
- [ ] Retire the current EpubCore while restructuring package handling. Preserve the requirement for a future core abstraction, either as a parallel API or a separate class on the same Source/Resources foundation.

## Design constraints and future work

- [ ] Keep Resource focused on providing bytes; do not restore the previous accumulation of OPF/NCX links and document-, image-, or chapter-specific behavior on Resource.
- [ ] Develop core and chapter support together: disassemble the webnovel EPUB library, deduplicate overlapping chapters, and reassemble EPUBs around their cores.
- [ ] Support assembling and updating EPUBs when new chapters arrive, and creating EPUBs from collections of internet articles.
- [ ] Define how shared chapter assets are retained and reused during disassembly and reassembly. Detailed ownership and deduplication policies remain open.
- [ ] Revisit navigation design separately: spine, NCX, guide/tours, and eventual EPUB 3 NAV support. No combined navigation API or reading-order/TOC class structure has been accepted yet.

The core/content distinction is application-defined, not a partition imposed by the EPUB specification. A NAV document may belong to the core even when it appears in the spine.

## Explicitly deferred

- Source path APIs, Path/ZipPath/backend types, and escaping path lifetimes remain unchanged for now; they may serve uses beyond EPUB.
- Shared-instance concurrency is not being added. The concern is multiple workers sharing one EPUB/Source instance, not workers each processing their own instance.
- Broader changes to resource identity, statistics, streaming, and generic book models require separate review; they are not part of the Source fixes.

## Already accepted

- [x] Resolve local manifest hrefs relative to the OPF location. The current package_path argument fixes lookup correctness; its architectural replacement will be evaluated with the package prototype.
