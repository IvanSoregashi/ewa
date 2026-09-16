# EPUB architecture TODO

## Agreed next steps

- [x] Fix Source exception cleanup: a failed ZIP session must close and reset its handle, and subsequent reads must work.
- [x] Fix single-file ZIP extraction: match DirectorySource for existing-directory and exact-filename destinations, preserve timestamps, and avoid duplicated member paths. Add synthetic regression tests.
- [x] Prototype a package entity associating the OPF resource with its parsed document. EpubPackage exposes document, local href resolution and flush; EPUB export flushes document edits. Review before expanding the design.
- [x] Put discovery in EpubPackage.from_resources. Keep the container resource and its XML model on the package; package.relocate updates the OPF hrefs, resource index, and container reference together.
- [x] Make ResourceIndex.rename(resource, new_filename) rename and re-key together, rejecting collisions. Preserve original source ZipInfo separately from current output metadata so reads survive renames.
- [x] When a unique OPF exists without META-INF/container.xml, create a standard container document and resource, add it to the inventory, and bind it to the package. Verify relocation and export/reopen; replace the current missing-container rejection test.
- [x] Define and test valid archive destination paths and URL handling for relocation (normalization, encoded paths, queries, and fragments) before treating it as general EPUB reference rewriting.
- [x] Justify any package facades and a separate EpubManifest through useful editing methods. Avoid wrappers that merely shorten attribute access.
- [x] Settle resource deletion and collection ownership on one consistent model. Review the implementation before adopting wider ResourceIndex API changes; membership versus is_deleted is currently redundant.
- [x] Address manifest index consistency and synchronization during add/remove/edit, together with the ownership decision. Decide how filtered collections behave.
- [ ] Retire the current EpubCore while restructuring package handling. Preserve the requirement for a future core abstraction, either as a parallel API or a separate class on the same Source/Resources foundation.

## Design constraints and future work

- [ ] Keep Resource focused on providing bytes; do not restore the previous accumulation of OPF/NCX links and document-, image-, or chapter-specific behavior on Resource.
- [ ] Develop core and chapter support together: disassemble the webnovel EPUB library, deduplicate overlapping chapters, and reassemble EPUBs around their cores.
- [ ] Support assembling and updating EPUBs when new chapters arrive, and creating EPUBs from collections of internet articles.
- [ ] Define how shared chapter assets are retained and reused during disassembly and reassembly. Detailed ownership and deduplication policies remain open.
- [ ] Revisit navigation design separately: spine, NCX, guide/tours, and eventual EPUB 3 NAV support. No combined navigation API or reading-order/TOC class structure has been accepted yet.

The core/content distinction is application-defined, not a partition imposed by the EPUB specification. A NAV document may belong to the core even when it appears in the spine.

Use `uv run ruff format` on changed Python files. The repository has pre-existing Ruff/ty findings; assess checks against the affected scope.

## Explicitly deferred

- Source path APIs, Path/ZipPath/backend types, and escaping path lifetimes remain unchanged for now; they may serve uses beyond EPUB.
- Shared-instance concurrency is not being added. The concern is multiple workers sharing one EPUB/Source instance, not workers each processing their own instance.
- Broader changes to resource identity, statistics, streaming, and generic book models require separate review; they are not part of the Source fixes.

## Already accepted

- [x] Resolve local manifest hrefs relative to the OPF location. The package prototype replaces the copied package_path argument with an EpubPackage reference.

## Package prototype choices awaiting review

- EpubPackage.from_resources discovers the OPF/container; the constructor also accepts already-selected resources. The relocation recipe delegates to package.relocate. Discovery creates a standard container for a unique OPF when the container is absent; existing invalid containers are not silently replaced.
- EpubCore temporarily forwards package access for existing callers; its NCX and manifest behavior is otherwise retained until the next design step.
- Export serializes loaded OPF and container documents directly, without snapshots or formatting-preservation flags. Unopened documents are left alone. Once parsed, edit the document rather than independently replacing its resource bytes.
- No extra metadata/spine facades or new deletion semantics have been introduced.

Relocation accepts normalized archive-relative file paths; it rejects absolute/escaping paths and file/directory collisions. Local URL paths use strict UTF-8 percent decoding, preserve query/fragment suffixes, and reject encoded separators or malformed escapes. Remote URLs pass through. This is the supported local-path contract, not a full WHATWG URL implementation.

## Package ownership implementation

- EpubManifest is removed. The package reads the XML manifest directly and coordinates add_resource/remove_resource; no second manifest index is cached.
- ResourceIndex owns membership; ResourceSelection is an immutable membership snapshot with editable resources. Removed objects can still be held/read, but export uses the owner's current inventory. There is no is_deleted flag.
- remove_resource rejects OPF dependents unless remove_references=True. Cleanup covers spine, guide, fallback/media-overlay, spine toc, cover metadata and dependent refinements. Content and NCX/NAV links are not inspected or rewritten.
- [ ] Define book-level deletion/link policy for XHTML, CSS, NCX and NAV before claiming whole-publication safe removal.
