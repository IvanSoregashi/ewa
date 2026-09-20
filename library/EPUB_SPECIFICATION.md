# EPUB architecture specification

## Scope and status

This document records EPUB design contracts for the reusable library and its workflow plugin.
Implementation order and completion status live in [EPUB_TODO.md](EPUB_TODO.md);
contributor instructions live in [AGENTS.md](../AGENTS.md).

The inventory/package foundation, per-book context, and automatic lifecycle outcomes are implemented.
Simple operations and eligibility checks now accept the context.
Workers return ProcessingRun directly, with typed metadata and unsaved image analytics;
the parent recorder persists those same objects. Windows spawn and transactional persistence are tested.
A separate Panda candidate uses the context for checks, transformations, export, and output validation.
Callers retain the legacy recipe until side-by-side comparison is complete; real books will be provided later.

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

OptimizeImages appends image records and publishes only successful path changes.
Image decode/optimization errors remain per-image evidence; inventory rename collisions
stop the book without overwriting the existing resource. ReplaceLinks consumes the mapping
in HTML and then OPF, clearing it only after both succeed. It stores paths unmatched in HTML
in context.unmatched_links; it does not decide whether to skip. NoUnmatchedLinks is a separate
late verification, placed before export by recipes that reject unmatched paths. The report
describes the last nonempty replacement pass; an empty pass leaves it available for verification.

EpubInfo, ImageInfo, and IndexInfo remain dataclasses. EpubInfo.from_path reads only
filesystem information. ImageInfo uses `size=None` for unreadable dimensions;
`bytes_per_pixel` returns None for unknown or zero-area dimensions, including older snapshots.
Density thresholds belong to the optimizer and retain their existing byte-based values.

Most operations produce no analytics. Those that do append unsaved SQLModel table instances,
with models defined near their operation and `run_id=context.run_id`. Records contain data, not live resources.
There is no database session, engine, or arbitrary shared-state dictionary on the context.

### Checks and operations

- Checks implement `verify(context) -> str | None`: None passes; a string is the failure message. Operations implement `perform(context) -> None`. The context's `verify(check)` and `perform(operation)` methods return the context for chaining. Low-level library functions need not become classes.
- Checks are gates before or after transformations. A failed verification immediately stops processing and produces a skip using the check's configured default `skip_reason` and fresh failure details.
- Conditional transformations, including choosing to do nothing, belong inside operations. Checks do not choose operations or offer warn/repair policies.
- Check instances retain configuration and skip_reason, not per-book state. Callers test `is not None` so even an empty failure message stops processing.
- Output validation is separate from eligibility: invalid exported output produces an error, not a skip.

### Context lifetime and outcomes

- Enter an empty `ProcessingContext`, then call `context.open_epub(path)` inside the block. It constructs the EPUB, keeps its source open, and captures original information before editing. Cleanup is registered before metadata reading; each context opens only one book.
- `context.verify(check)` consumes the immediate result and aborts the block on failure through a private control-flow exception. The skip outcome retains its reason and details; passed checks are not accumulated in a findings list.
- Ordinary processing failures automatically produce an error outcome with diagnostics, using context.error_reason (UNKNOWN by default). The recipe sets INCORRECT_RESULT immediately before reading exported metadata. Source cleanup and missing completion still use UNKNOWN. Earlier analytics survive; failure does not roll back in-memory edits.
- Construction, opening, and metadata failures become error outcomes without an outer handler. The outcome retains `input_path`; `original_epub` is `None` if information capture failed. No fallback file reads or invented metadata are needed. Interrupts such as KeyboardInterrupt still propagate.
- `context.succeed(new_info)` marks verified output; `context.result` is finalized after source cleanup. Later failures override success. Normal exit without completion produces an UNKNOWN error. Use a fresh context for each book and enter it once per recipe call; this is a convention, without a re-entry guard or reset machinery.
- Return ProcessingRun with book information, diagnostics, and unsaved analytics. Exclude the context, live EPUB/source/resources, and working replacement mapping.
- Reports display unavailable statistics and percentages with a zero denominator as `N/A`; they do not invent zero-valued statistics.

### Panda recipes and comparison

`ProcessingContext.outcome()` remains a manual outcome builder used by the lifecycle methods.
It copies the analytics list while sharing record objects and book information;
those shared objects must no longer be edited after handoff.

Single/batch callers filter paths outside the input directory and paths with existing destinations
before dispatch. These paths produce no outcome or analytics; the single caller returns None.
Both worker recipes assume paths have passed this filter. The persisted skip codes remain for history.

_fully_process_encrypted_panda retains the legacy processing order and is the caller default.
_fully_process_encrypted_panda_with_context is a separate candidate; verify_epub remains for the legacy path.
The candidate completes HTML/OPF updates together before unmatched-link verification and translation,
and validates output before closing the input context. The legacy recipe validates after closing it.

Synthetic comparisons check outcomes, metadata, image evidence (excluding generated UUIDs), and
exported resource contents. Known differences: an optimized image absent from HTML and the manifest
produces UNMATCHED_LINKS in the legacy recipe but UNKNOWN in the candidate; cleanup diagnostics also
differ. Both implementations remain available while those differences and user-provided book copies are evaluated.
Windows spawn tests now cover detached outcomes and unsaved image records for success, skip, error,
and setup failure, followed by parent-side persistence into a temporary database.

## Persistence and compatibility

- Only the parent persists results. Analytics attach to success, skip, and error processing runs, including evidence produced before a failure.
- Preserve existing numeric reason codes and analytics history. SQLModel `create_all` is not an existing-schema migration.
- Each context creates a UUID before opening the book; it becomes `ProcessingRun.id`. Operation records use it as a scalar foreign key. A fresh attempt gets a new ID even for the same path; workers need no database-generated IDs or ORM relationships.
- ProcessingRun is both the outcome and the persisted row. Its `analytics` property is a per-instance, unmapped transport list: it survives worker serialization, but queried runs start with an empty list. Query operation tables by `run_id` for saved evidence. The context copies its list at handoff; records and metadata must then remain unchanged.
- `original_epub`/`new_epub` hold EpubInfo; image records hold ImageInfo. A shared TypedJSON column adapter stores ordinary JSON and validates/reconstructs these dataclasses on database reads, including nested types, paths, enums, and unknown values. There are no duplicate snapshot models. Replace a whole snapshot when an update is necessary; nested edits are not tracked by SQLAlchemy.
- ImageOptimizationRecord is the only image analytics entity. Its small `from_result()` bridge accepts the reusable library optimizer's ImageOptimizationResult, which remains independent of plugin/database schemas.
- Import operation model modules before creating their records; imports only register schemas. The recorder creates tables for the concrete models in the batch, enables SQLite foreign keys, flushes runs before analytics, and commits all rows in one transaction. Returned objects remain readable after the session closes.
- New writes use `epub_processing_runs` and `epub_image_optimizations`. Historical tables remain untouched, without automatic backfill or dual writes; old integer IDs are never reinterpreted as run UUIDs. Historical reporting must query those old tables explicitly. The legacy writer, outcome conversions, and table-wrapper classes are removed.
- Persistence errors propagate without clearing the input batch. There are no automatic retries or upserts. Stable primary keys reject duplicate transient records; after an uncertain commit, inspect the database using the original run/record IDs before retrying. Do not generate new IDs merely to bypass a duplicate.
- Current recipe scaffolding deletes destination output on success and leaves original movement disabled. Changing this requires an explicit decision before real-book validation.
- `max_workers=None` still takes the synchronous branch despite its CPU-count docstring; this remains a scheduled defect.

## Deferred scope and open decisions

- Core/chapter work: disassembly, chapter deduplication, shared assets, reassembly, incremental chapters, and books assembled from internet articles.
- The core/content distinction is application-defined, not an EPUB partition. A NAV document may belong to the core even when present in the spine.
- Navigation: spine, NCX, guide/tours, and EPUB 3 NAV; no combined TableOfContents design has been accepted.
- Book-level deletion/link policy across XHTML, CSS, NCX, and NAV.
- Source path/backend APIs and path lifetimes remain unchanged; broader resource identity, statistics, streaming, and generic book models need separate review.
- Concurrent operations sharing one EPUB/Source instance are out of scope; separate workers may each own their own instance.
- No automatic dependency graphs, extension registries, generic runner framework, or rollback machinery without a concrete need.
