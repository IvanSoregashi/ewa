# EPUB architecture specification

## Scope and status

This document records EPUB design contracts for the reusable library and its workflow plugin.
Implementation order and completion status live in [EPUB_TODO.md](EPUB_TODO.md);
contributor instructions live in [AGENTS.md](../AGENTS.md).

The inventory/package foundation, per-book context, and automatic lifecycle outcomes are implemented.
Simple operations and eligibility checks now accept the context.
The processing-run schema is next; the recorder and full recipe migration remain pending.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Source | Provide original bytes and manage access to their backing storage. |
| Resource / ResourceIndex | Represent editable resources; own inventory membership and current paths. |
| EpubPackage / XML models | Coordinate package resources and declarations; parse and edit package XML. |
| Library editing functions | Supply reusable HTML, image, and resource primitives. |
| Plugin checks and operations | Apply configured eligibility rules and workflow transformations through uniform class interfaces. |
| ProcessingContext | Hold one book's working state and accumulated evidence for one recipe call. |
| Recipe | Order steps, export, validate output, and explicitly complete success. |
| Parent process | Persist returned outcomes and unsaved analytics. Workers own no database sessions or connections. |

The library does not import plugin policy, workflow protocols, or persisted outcome codes.
Workflow `recipe_*` modules and verification contracts belong to the plugin.

## Inventory and package contracts

### Resources and sources

- Resource retains original source information independently of renamed output paths.
- ResourceIndex owns membership. Rename re-keys the index and rejects collisions; deletion removes membership, without an `is_deleted` flag.
- ResourceSelection is an immutable membership snapshot containing editable resources. Removed resources can still be held/read; export uses current index membership.
- Keep Resource focused on bytes and resource identity. Do not accumulate OPF/NCX links or chapter/image-specific behavior on it.
- A failed ZIP source session closes and resets its handle so later reads work. Single-file extraction follows the directory-source destination semantics, preserves timestamps, and does not duplicate member paths.
- SourceProtocol accepts archive member names (`str`) and `ZipInfo`; concrete sources additionally accept their own path types. Resource stream factories return context managers yielding binary streams.

### Package discovery and editing

- EpubPackage binds OPF/container resources to parsed XML models. It discovers the package and can create a missing container when exactly one OPF exists; invalid existing containers are not silently replaced.
- Manifest owns declaration lookup with combined literal attribute criteria, declaration changes, and validation. Package coordinates inventory and resolved paths; there is no separate EpubManifest index.
- PackageDocument IDs are obtained by walking models without XML serialization. Metadata reference lookup includes cover metadata and transitive refinements.
- Relocation updates the OPF resource path, local hrefs, and container reference together.
- Export serializes loaded OPF/container documents directly. There are no serialized snapshots, dirty tracking, or byte-format preservation requirements. Once parsed, edit the document rather than independently replacing its resource bytes.
- XMLDocumentModel requires pydantic-xml's lxml backend and validates returned elements; the standard-library XML backend is unsupported.
- EpubCore is retired. Use `epub.package`; NCXDocument remains usable directly while broader navigation design is deferred.

### Paths and deletion

- Relocation accepts normalized archive-relative file paths and rejects absolute/escaping paths and file/directory collisions.
- Local URLs use strict UTF-8 percent decoding, preserve query/fragment suffixes, and reject encoded separators and malformed escapes. Remote URLs pass through. This is not a full WHATWG URL implementation.
- Resource removal rejects OPF dependents by default. Explicit reference cleanup covers spine, guide, fallback/media-overlay, spine toc, cover metadata, and dependent refinements through existing section methods.
- Cleanup does not inspect NCX/NAV/HTML/CSS references. Whole-publication deletion/link policy remains open.

## Processing contracts

### State and ownership

One context belongs to one book and one recipe call, created inside its worker.
Operations run sequentially. The context holds the live EPUB, original book information,
a shared old-path-to-new-path replacement mapping and one analytics list.
An empty replacement mapping means no work; no separate “not run” state is needed.

Most operations produce no analytics. Those that do append unsaved SQLModel table instances,
with models defined near their operation. Records contain data, not live resources.
There is no database session, engine, arbitrary shared-state dictionary, or operation-specific result slot on the context.

### Checks and operations

- Checks implement `verify(context) -> VerificationResult`; operations implement `perform(context) -> None`. The context's `verify(check)` and `perform(operation)` methods return the context for chaining. Low-level library functions need not become classes.
- Checks are eligibility gates. A failed verification immediately stops processing and produces a skip using the check's configured default `skip_reason` and fresh failure details.
- Conditional transformations, including choosing to do nothing, belong inside operations. Checks do not choose operations or offer warn/repair policies.
- VerificationResult is an immutable `(passed, details)` dataclass, fresh for each call. Check instances retain configuration, not per-book state.
- Output validation is separate from eligibility: invalid exported output produces an error, not a skip.

### Context lifetime and outcomes

- Enter an empty `ProcessingContext`, then call `context.open_epub(path)` inside the block. It constructs the EPUB, keeps its source open, and captures original information before editing. Cleanup is registered before metadata reading; each context opens only one book.
- `context.verify(check)` consumes the immediate result and aborts the block on failure through a private control-flow exception. The skip outcome retains its reason and details; passed checks are not accumulated in a findings list.
- Ordinary processing failures automatically produce an error outcome with diagnostics. Earlier analytics survive. Failure does not roll back in-memory edits.
- Construction, opening, and metadata failures become error outcomes without an outer handler. The outcome retains `input_path`; `original_epub` is `None` if information capture failed. No fallback file reads or invented metadata are needed. Interrupts such as KeyboardInterrupt still propagate.
- `context.succeed(new_info)` marks verified output; `context.result` is finalized after source cleanup. Later failures override success. Normal exit without completion produces an UNKNOWN error. Use a fresh context for each book and enter it once per recipe call; this is a convention, without a re-entry guard or reset machinery.
- Return EpubOperationResult with book information, diagnostics, and analytics. Exclude the context, live EPUB/source/resources, and working replacement mapping.
- Reports display unavailable statistics and percentages with a zero denominator as `N/A`; they do not invent zero-valued statistics.

### Current prototype and migration compatibility

`ProcessingContext.outcome()` remains a manual outcome builder used by the lifecycle methods.
It copies the analytics list while sharing record objects and book information;
those shared objects must no longer be edited after handoff.

Translation, resource removal, CSS cleanup, and eligibility checks use the context contracts.
The Panda recipe temporarily calls `verify_epub(epub)` on its OPFPath and SerenePanda checks;
its full migration is step 8. ReplaceLinks remains on its legacy interface until the shared
replacement mapping is integrated in step 7. EpubOperationResult retains `image_results`
for the legacy recipe. The legacy recorder does not yet persist details or the new analytics list.
It also assumes original book information exists; persistence of setup failures awaits the run schema.
Local pickle tests do not establish actual Windows process-pool transport.

## Persistence and compatibility

- Only the parent persists results. Analytics must eventually attach to success, skip, and error processing runs, including evidence produced before a failure.
- Preserve existing numeric reason codes and analytics history. SQLModel `create_all` is not an existing-schema migration.
- Run schema, ID versus object-relationship association, import/schema registration, and existing-data migration remain undecided.
- The parent recorder will accept mixed mapped instances in one session/transaction per batch and retain failed-write buffers. Retry and duplicate handling require an explicit design before enabling retries.
- Current image tables reference successful EPUBs. Their replacement/association is deferred until the run schema is established.
- Current recipe scaffolding deletes destination output on success and leaves original movement disabled. Changing this requires an explicit decision before real-book validation.
- Current batch code clears buffers after persistence failure, and `max_workers=None` takes the synchronous branch despite its docstring. These are scheduled defects, not accepted target behavior.

## Deferred scope and open decisions

- Core/chapter work: disassembly, chapter deduplication, shared assets, reassembly, incremental chapters, and books assembled from internet articles.
- The core/content distinction is application-defined, not an EPUB partition. A NAV document may belong to the core even when present in the spine.
- Navigation: spine, NCX, guide/tours, and EPUB 3 NAV; no combined TableOfContents design has been accepted.
- Book-level deletion/link policy across XHTML, CSS, NCX, and NAV.
- Source path/backend APIs and path lifetimes remain unchanged; broader resource identity, statistics, streaming, and generic book models need separate review.
- Concurrent operations sharing one EPUB/Source instance are out of scope; separate workers may each own their own instance.
- No automatic dependency graphs, extension registries, generic runner framework, or rollback machinery without a concrete need.
